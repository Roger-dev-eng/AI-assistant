import json
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import pytest

from assistant.core.action_executor import ActionExecutor
from assistant.core.intent_router import Action, IntentRouter
from assistant.core.orchestrator import Orchestrator
from assistant.security.urls import public_https_url, verify_public_resolution
from assistant.tools.browser import BrowserTools, clean_result, search_request_allowed, search_url
from assistant.tools.windows import WindowsTools


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/secret",
        "javascript:alert(1)",
        "http://example.com",
        "https://localhost/x",
        "https://127.0.0.1/",
        "https://10.0.0.1",
        "https://169.254.169.254/latest/meta-data",
        "https://example.local",
        "https://foo.internal",
        "https://user:pass@example.com",
        "https://example.com:8443",
        "https://example.com\\@127.0.0.1",
        "https://example.com\n/x",
        "https://[::1]",
        "https://example.com:bad",
    ],
)
def test_reject_unsafe_result_urls(url):
    with pytest.raises(ValueError):
        public_https_url(url)


def test_resolved_private_address_is_rejected():
    with patch(
        "assistant.security.urls.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("10.0.0.1", 443))],
    ):
        with pytest.raises(ValueError, match="non-public"):
            verify_public_resolution("https://example.com/article")


@pytest.mark.parametrize(
    "url,resource,allowed",
    [
        ("https://www.google.com/search?q=python", "document", True),
        ("https://www.youtube.com/youtubei/v1/search", "fetch", True),
        ("https://i.ytimg.com/image.jpg", "image", False),
        ("https://www.google.com.evil.test", "document", False),
        ("https://localhost/admin", "document", False),
        ("file:///C:/secret", "document", False),
        ("https://example.com", "document", False),
    ],
)
def test_isolated_search_request_policy(url, resource, allowed):
    assert search_request_allowed(url, resource) is allowed


def test_google_redirect_and_youtube_video_cleaning():
    assert clean_result(
        {"title": " Python  docs ", "url": "/url?q=https%3A%2F%2Fdocs.python.org%2F3%2F"}, "google"
    ) == {"title": "Python docs", "url": "https://docs.python.org/3/"}
    assert (
        clean_result({"title": "Tutorial", "url": "/watch?v=abcdefghijk&tracking=1"}, "youtube")[
            "url"
        ]
        == "https://www.youtube.com/watch?v=abcdefghijk"
    )
    with pytest.raises(ValueError):
        clean_result(
            {"title": "Injected", "url": "https://evil.example/watch?v=abcdefghijk"}, "youtube"
        )


def test_result_cache_is_bounded_deduplicated_and_invalidated():
    browser = BrowserTools()
    data = json.loads(
        browser.store_results(
            [{"title": f"Result {i}", "url": f"https://example.com/{i}"} for i in range(9)] * 2,
            "google",
        )
    )
    assert len(data["untrusted_search_results"]) == 5
    old_id = data["untrusted_search_results"][0]["result_id"]
    browser.store_results([{"title": "New", "url": "https://example.com/new"}], "google")
    with pytest.raises(ValueError, match="expired"):
        browser.describe_result(old_id)


def test_external_result_requires_confirmation_with_real_destination():
    backend = WindowsTools()
    backend.browser.store_results(
        [{"title": "Python docs", "url": "https://docs.python.org/3/"}], "google"
    )
    identifier = next(iter(backend.browser.results))
    confirm = Mock(return_value=False)
    with patch("assistant.tools.browser.webbrowser.open") as opener:
        executor = ActionExecutor(backend, confirm)
        assert (
            executor.execute(Action("open_search_result", {"result_id": identifier}))
            == "Action denied by user."
        )
        opener.assert_not_called()
    assert "https://docs.python.org/3/" in confirm.call_args.args[0]
    executor.begin_task()
    assert not backend.browser.results
    assert backend.browser.cancelled is executor.cancelled


def test_open_result_uses_stored_url_and_checks_cancellation():
    browser = BrowserTools()
    browser.store_results([{"title": "Docs", "url": "https://docs.python.org/3/"}], "google")
    identifier = next(iter(browser.results))
    with (
        patch("assistant.tools.browser.verify_public_resolution") as verify,
        patch("assistant.tools.browser.webbrowser.open", return_value=True) as opener,
    ):
        browser.open_search_result(identifier)
        verify.assert_called_once_with("https://docs.python.org/3/")
        opener.assert_called_once_with("https://docs.python.org/3/")
        browser.cancelled.set()
        with pytest.raises(InterruptedError):
            browser.open_search_result(identifier)
        assert opener.call_count == 1


def test_list_results_routes_locally_without_changing_normal_searches():
    assert IntentRouter().route("liste resultados de Café no Google")[0] == Action(
        "read_search_results", {"query": "Café", "engine": "google"}
    )
    assert (
        IntentRouter().route("list results for Python on YouTube")[0].name == "read_search_results"
    )
    assert IntentRouter().route("pesquise Python no Google")[0].name == "search_web"
    assert "q=caf%C3%A9" in search_url("café", "google")


def test_model_can_select_only_a_stored_result_after_reading():
    backend = WindowsTools()
    provider = Mock()

    def model_reply(messages):
        if len(messages) == 1:
            call = {
                "toolUseId": "read",
                "name": "read_search_results",
                "input": {"query": "Python docs", "engine": "google"},
            }
        elif len(messages) == 3:
            data = json.loads(messages[-1]["content"][0]["toolResult"]["content"][0]["text"])
            identifier = data["untrusted_search_results"][0]["result_id"]
            call = {
                "toolUseId": "open",
                "name": "open_search_result",
                "input": {"result_id": identifier},
            }
        else:
            return {"role": "assistant", "content": [{"text": "Documentação aberta."}]}
        return {"role": "assistant", "content": [{"toolUse": call}]}

    provider.converse.side_effect = model_reply
    confirm = Mock(return_value=True)
    with (
        patch.object(
            backend.browser,
            "read_search_results",
            side_effect=lambda *args, **kw: backend.browser.store_results(
                [{"title": "Python docs", "url": "https://docs.python.org/3/"}], "google"
            ),
        ),
        patch("assistant.tools.browser.verify_public_resolution"),
        patch("assistant.tools.browser.webbrowser.open", return_value=True) as opener,
    ):
        assistant = Orchestrator(ActionExecutor(backend, confirm), provider)
        assert (
            assistant.run("Encontre a documentação do Python e abra o resultado mais relevante")
            == "Documentação aberta."
        )
        opener.assert_called_once_with("https://docs.python.org/3/")
        confirm.assert_called_once()


@pytest.fixture
def playwright_api():
    return pytest.importorskip("playwright.sync_api")


def test_browser_closes_when_search_cancelled(playwright_api):
    with patch("playwright.sync_api.sync_playwright") as start:
        runtime = start.return_value.__enter__.return_value
        browser = runtime.chromium.launch.return_value
        page = browser.new_context.return_value.new_page.return_value
        tools = BrowserTools()
        tools.cancelled = Event()
        page.goto.side_effect = lambda *args, **kwargs: tools.cancelled.set()
        with pytest.raises(InterruptedError):
            tools.read_search_results("Python", "google")
        browser.close.assert_called_once()


def test_timeout_does_not_bypass_challenge_or_leave_browser_open(playwright_api):
    with patch("playwright.sync_api.sync_playwright") as start:
        runtime = start.return_value.__enter__.return_value
        browser = runtime.chromium.launch.return_value
        page = browser.new_context.return_value.new_page.return_value
        page.goto.side_effect = playwright_api.TimeoutError("challenge")
        with pytest.raises(RuntimeError, match="No bypass"):
            BrowserTools().read_search_results("Python", "google")
        browser.close.assert_called_once()


@pytest.mark.parametrize(
    "engine,html",
    [
        (
            "google",
            '<a href="https://docs.python.org/3/"><h3>Python documentation</h3></a>'
            '<a href="file:///C:/secret"><h3>Bad link</h3></a>',
        ),
        ("youtube", '<a id="video-title" href="/watch?v=abcdefghijk">Python tutorial</a>'),
    ],
)
def test_real_chromium_search_with_offline_fixture(playwright_api, monkeypatch, engine, html):
    # Run production navigation/extraction in Chromium, with every request fulfilled locally.
    with playwright_api.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Chromium is not installed")
    original = playwright_api.BrowserContext.route

    def offline_route(context, pattern, handler):
        def fulfill(route):
            route.fulfill(status=200, content_type="text/html", body=html)

        return original(context, pattern, fulfill)

    monkeypatch.setattr(playwright_api.BrowserContext, "route", offline_route)
    result = json.loads(BrowserTools().read_search_results("Python", engine))
    assert len(result["untrusted_search_results"]) == 1
    assert result["untrusted_search_results"][0]["title"].startswith("Python")
