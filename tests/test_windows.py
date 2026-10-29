from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from assistant.tools.windows import WindowsTools


def test_search_encodes_query_without_interpreting_url():
    backend = WindowsTools()
    with patch("assistant.tools.windows.webbrowser.open", return_value=True) as browser:
        backend.search_web("café & x=1 # hello", "youtube")
    parsed = urlparse(browser.call_args.args[0])
    assert parsed.netloc == "www.youtube.com"
    assert parse_qs(parsed.query) == {"search_query": ["café & x=1 # hello"]}
    assert not parsed.fragment


def test_active_window_uses_foreground_handle():
    desktop = Mock()
    desktop.return_value.window.return_value.window_text.return_value = "Editor"
    modules = {
        "win32gui": SimpleNamespace(GetForegroundWindow=lambda: 123),
        "pywinauto": SimpleNamespace(Desktop=desktop),
    }
    with patch.dict("sys.modules", modules), patch.object(WindowsTools, "_windows"):
        assert WindowsTools().active_app() == "Editor"
    desktop.return_value.window.assert_called_once_with(handle=123)
