from threading import Event
from unittest.mock import Mock, patch

import pytest

from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.storage.activity import ActivityStore
from assistant.tools.navigation import NavigationSession
from assistant.tools.windows import WindowsTools


class FakePage:
    def __init__(self, url="about:blank", closed=False):
        self.url, self.closed = url, closed
        self.visits = []

    def is_closed(self):
        return self.closed

    def evaluate(self, expression):
        assert expression == "() => location.href"
        if self.closed:
            raise RuntimeError("closed")
        return self.url

    def goto(self, url, **kwargs):
        self.url = url
        self.visits.append(url)

    def bring_to_front(self):
        pass

    def locator(self, selector):
        return Mock()


def session_with_page(url):
    session = NavigationSession(Mock())
    session.browser = Mock()
    session.browser.is_connected.return_value = True
    session.context = Mock()
    page = FakePage(url)
    session.pages["tab"] = page
    return session, page, session.state("tab", page)


def test_search_reuses_verified_tab_and_sqlite_context_across_backend_instances(tmp_path):
    store = ActivityStore(tmp_path / "usage.sqlite3")
    session, page, state = session_with_page("https://www.youtube.com")
    store.remember_navigation(state)
    broker = Mock()
    broker.call.side_effect = lambda method, *args: getattr(session, method)(*args)
    with (
        patch("assistant.tools.navigation.navigation_broker", return_value=broker),
        patch("assistant.tools.navigation.verify_public_resolution"),
    ):
        backend = WindowsTools()
        backend.bind_activity(ActivityStore(store.path))
        backend.search_current_site("Python")
        backend = WindowsTools()
        backend.bind_activity(ActivityStore(store.path))
        backend.search_current_site("SQLite")
    session.context.new_page.assert_not_called()
    assert len(page.visits) == 2
    assert "search_query=SQLite" in page.url
    assert store.navigation()["tab_id"] == "tab"
    assert store.navigation()["query"] == "SQLite"


@pytest.mark.parametrize("stale", ["closed", "changed_site", "previous_run"])
def test_stale_reference_opens_new_tab_without_hijacking_changed_page(stale):
    session, page, saved = session_with_page("https://www.youtube.com")
    if stale == "closed":
        page.closed = True
    elif stale == "changed_site":
        page.url = "https://github.com"
    else:
        saved["run_id"] = "previous-app-session"
    fresh = FakePage()
    session.context.new_page.return_value = fresh
    with patch("assistant.tools.navigation.verify_public_resolution"):
        result = session.navigate("https://www.youtube.com", saved, Event())
    assert result["tab_id"] != saved["tab_id"]
    assert page.visits == []
    assert fresh.visits == ["https://www.youtube.com"]


def test_result_changed_after_confirmation_is_not_opened():
    session, page, saved = session_with_page("https://www.youtube.com/results?search_query=Python")
    rows = [[{"title": "One", "url": "/watch?v=kJQP7kiw5Fk"}],
            [{"title": "Other", "url": "/watch?v=dQw4w9WgXcQ"}]]
    with patch("assistant.tools.navigation.extract_search_results", side_effect=rows):
        selected = session.describe_position(saved, 1, Event())
        assert "kJQP7kiw5Fk" in selected["url"]
        with pytest.raises(RuntimeError, match="mudaram"):
            session.open_position(saved, 1, Event())
    assert page.visits == []


def test_confirmed_result_opens_in_the_same_search_tab():
    session, page, saved = session_with_page("https://www.youtube.com/results?search_query=Python")
    with (
        patch("assistant.tools.navigation.extract_search_results",
              return_value=[{"title": "Python", "url": "/watch?v=kJQP7kiw5Fk"}]),
        patch("assistant.tools.navigation.verify_public_resolution"),
    ):
        session.describe_position(saved, 1, Event())
        state = session.open_position(saved, 1, Event())
    assert state["tab_id"] == "tab"
    assert page.visits == ["https://www.youtube.com/watch?v=kJQP7kiw5Fk"]
    session.context.new_page.assert_not_called()


def test_missing_context_does_not_launch_browser_or_choose_arbitrary_results():
    session = NavigationSession(Mock())
    with pytest.raises(RuntimeError, match="pesquisa anterior"):
        session.describe_position(None, 1, Event())
    session.playwright.chromium.launch.assert_not_called()


def test_open_chrome_then_search_and_change_site_reuse_same_tab():
    session, page, _ = session_with_page("https://www.google.com")
    with patch("assistant.tools.navigation.verify_public_resolution"):
        session.open_browser("C:/Chrome/chrome.exe", Event())
        first = session.navigate_active("https://www.google.com/search?q=github", Event())
        second = session.navigate_active("https://github.com", Event())
    assert first["tab_id"] == second["tab_id"] == "tab"
    session.context.new_page.assert_not_called()
    assert page.visits == ["https://www.google.com/search?q=github", "https://github.com"]


def test_closed_chrome_tab_is_replaced_and_blank_tab_is_reused():
    session, page, _ = session_with_page("https://www.google.com")
    page.closed = True
    fresh = FakePage()
    session.context.new_page.return_value = fresh
    session.open_browser("C:/Chrome/chrome.exe", Event())
    with patch("assistant.tools.navigation.verify_public_resolution"):
        session.navigate_active("https://github.com", Event())
    session.context.new_page.assert_called_once()
    assert fresh.visits == ["https://github.com"]
    assert page.visits == []


def test_navigation_does_not_replace_whatsapp_conversation():
    session, page, _ = session_with_page("https://web.whatsapp.com")
    session.whatsapp_page = page
    fresh = FakePage()
    session.context.new_page.return_value = fresh
    with patch("assistant.tools.navigation.verify_public_resolution"):
        session.navigate_active("https://github.com", Event())
    session.context.new_page.assert_called_once()
    assert page.visits == []
    assert fresh.visits == ["https://github.com"]


def test_correlated_command_chain_with_real_chromium_and_offline_pages(tmp_path):
    from playwright.sync_api import sync_playwright

    html = '<html><a id="video-title" href="/watch?v=kJQP7kiw5Fk">Python tutorial</a></html>'
    store = ActivityStore(tmp_path / "usage.sqlite3")
    provider, confirm = Mock(), Mock(return_value=True)
    with sync_playwright() as playwright:
        session = NavigationSession(playwright)
        session.browser = playwright.chromium.launch(headless=True)
        session.context = session.browser.new_context()
        session.context.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        broker = Mock()
        broker.call.side_effect = lambda method, *args: getattr(session, method)(*args)
        try:
            with (
                patch("assistant.tools.navigation.navigation_broker", return_value=broker),
                patch("assistant.tools.navigation.verify_public_resolution"),
            ):
                for text in ("abre o YouTube", "pesquisa Python", "abre o primeiro vídeo"):
                    backend = WindowsTools()
                    executor = ActionExecutor(backend, confirm, activity=ActivityStore(store.path))
                    Orchestrator(executor, provider).run(text)
            assert len(session.context.pages) == 1
            assert session.context.pages[0].url == "https://www.youtube.com/watch?v=kJQP7kiw5Fk"
            confirm.assert_called_once()
            assert "Python tutorial" in confirm.call_args.args[0]
            provider.converse.assert_not_called()
            assert store.navigation()["url"] == session.context.pages[0].url
        finally:
            session.close()
