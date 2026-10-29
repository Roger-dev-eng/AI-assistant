import os
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode


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
        if not webbrowser.open(url):
            raise RuntimeError("Unable to open the default browser.")
        return f"Opened {url}."

    def search_web(self, query, engine):
        url = (
            "https://www.youtube.com/results?" + urlencode({"search_query": query})
            if engine == "youtube"
            else "https://www.google.com/search?" + urlencode({"q": query})
        )
        return self.open_site(url)

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
