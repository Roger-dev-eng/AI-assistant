import os
import webbrowser
from contextlib import contextmanager
from pathlib import Path

from assistant.tools.browser import BrowserTools, search_url


@contextmanager
def automation_context():
    """Balance COM initialization for automation running outside the main thread."""
    pythoncom = None
    if os.name == "nt":
        try:
            import pythoncom
        except ImportError:
            pass  # Non-Windows tools remain usable without the Windows extra.
    if pythoncom is not None:
        pythoncom.CoInitialize()
    try:
        yield
    finally:
        if pythoncom is not None:
            pythoncom.CoUninitialize()


class WindowsTools:
    """Fixed tool implementations. No shell, arbitrary executable paths or generated scripts."""

    def __init__(self):
        self.browser = BrowserTools()
        self.activity = None

    def bind_activity(self, activity):
        self.activity = activity

    def current_search_site(self):
        state = self.activity.navigation() if self.activity else None
        if state and state["site"] in {"google", "youtube"}:
            return state["site"]
        return "google"

    def bind_cancellation(self, cancelled):
        self.browser.cancelled = cancelled

    def reset_task(self):
        self.browser.results.clear()

    def read_search_results(self, query, engine):
        return self.browser.read_search_results(query, engine)

    def describe_result(self, result_id):
        return self.browser.describe_result(result_id)

    def open_search_result(self, result_id):
        if self.activity is not None:
            from assistant.tools.navigation import navigation_broker, site_of

            self.browser.describe_result(result_id)
            self.browser.check_cancelled()
            url = self.browser.results[result_id]["url"]
            saved = self.activity.navigation(site_of(url)) or self.activity.navigation()
            state = navigation_broker().call("open_link", url, saved, self.browser.cancelled)
            self.activity.remember_navigation(state)
            return f"Resultado aberto na aba do assistente: {url}"
        return self.browser.open_search_result(result_id)

    @staticmethod
    def _windows():
        if os.name != "nt":
            raise RuntimeError("This tool requires Windows.")

    def _executable(self, app):
        self._windows()
        system = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
        if app in {"notepad", "calculator"}:
            return system / {"notepad": "notepad.exe", "calculator": "calc.exe"}[app]
        for root in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if root:
                path = Path(root) / "Google/Chrome/Application/chrome.exe"
                if path.is_file():
                    return path
        raise RuntimeError("Chrome was not found in a standard installation directory.")

    def open_app(self, app):
        import subprocess

        path = self._executable(app)
        if not path.is_file():
            raise RuntimeError(f"Application not found: {app}")
        subprocess.Popen([str(path)], shell=False)
        return f"Opened {app}."

    def close_app(self, app):
        self._windows()
        import psutil
        from pywinauto import Desktop

        names = {
            "chrome": {"chrome.exe"},
            "notepad": {"notepad.exe"},
            "calculator": {"calculatorapp.exe", "calculator.exe"},
        }
        count = 0
        for window in Desktop(backend="win32").windows():
            try:
                process_name = psutil.Process(window.process_id()).name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if process_name in names[app]:
                # Request normal close; never kill the process or dismiss save prompts.
                window.post_message(0x0010)
                count += 1
        return f"Requested close for {count} window(s); save dialogs may remain."

    def open_site(self, url):
        if self.activity is not None:
            from assistant.tools.navigation import navigation_broker, site_of

            saved = self.activity.navigation(site_of(url))
            state = navigation_broker().call("navigate", url, saved, self.browser.cancelled)
            self.activity.remember_navigation(state)
            return f"Site aberto na aba do assistente: {url}"
        if not webbrowser.open(url):
            raise RuntimeError("Unable to open the default browser.")
        return f"Opened {url}."

    def search_web(self, query, engine):
        result = self.open_site(search_url(query, engine))
        if self.activity is not None:
            state = self.activity.navigation(engine)
            self.activity.remember_navigation(state, query)
        return result

    def search_current_site(self, query):
        if self.activity is None:
            raise RuntimeError("Ative o histórico de comandos para usar a navegação correlacionada.")
        return self.search_web(query, self.current_search_site())

    def describe_correlated_result(self, position):
        if self.activity is None:
            raise RuntimeError("Ative o histórico de comandos para continuar uma pesquisa.")
        from assistant.tools.navigation import navigation_broker

        saved = self.activity.navigation()
        selected = navigation_broker().call("describe_position", saved, position, self.browser.cancelled)
        return f"Abrir resultado {position}:\n{selected['title']}\n{selected['url']}"

    def open_correlated_result(self, position):
        from assistant.tools.navigation import navigation_broker

        saved = self.activity.navigation() if self.activity else None
        state = navigation_broker().call("open_position", saved, position, self.browser.cancelled)
        self.activity.remember_navigation(state)
        return "Resultado aberto na mesma aba da pesquisa."

    def set_volume(self, percent):
        self._windows()
        from pycaw.pycaw import AudioUtilities

        AudioUtilities.GetSpeakers().EndpointVolume.SetMasterVolumeLevelScalar(percent / 100, None)
        return f"Volume: {percent}%."

    def active_app(self):
        self._windows()
        import win32gui
        from pywinauto import Desktop

        handle = win32gui.GetForegroundWindow()
        if not handle:
            return "No active application window."
        return Desktop(backend="uia").window(handle=handle).window_text()
