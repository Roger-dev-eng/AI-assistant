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
        self.settings = None
        self.database_path = None
        self.desktop = None

    def configure_runtime(self, settings, database_path):
        self.settings, self.database_path = settings, database_path

    def runtime(self):
        if self.settings is None:
            from assistant.config import Settings, data_path

            self.settings, self.database_path = Settings.from_env(), data_path()
        return self.settings

    def desktop_tools(self):
        if not self.runtime().desktop_automation_enabled:
            raise RuntimeError("Ative o controle de interface nas configurações para usar esta ferramenta.")
        if self.desktop is None:
            from assistant.tools.desktop import DesktopTools

            self.desktop = DesktopTools(self.browser.cancelled)
        return self.desktop

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
        if self.desktop is not None:
            self.desktop.controls.clear()

    def read_search_results(self, query, engine):
        return self.browser.read_search_results(query, engine)

    def browser_context(self):
        import json

        from assistant.tools.navigation import navigation_broker

        return json.dumps(navigation_broker().call("browser_context", self.browser.cancelled), ensure_ascii=False)

    def select_browser_tab(self, tab_id):
        from assistant.tools.navigation import navigation_broker

        state = navigation_broker().call("select_tab", tab_id, self.browser.cancelled)
        if self.activity is not None:
            self.activity.remember_navigation(state)
        return f"Página selecionada: {state['url']}"

    def browser_back(self):
        from assistant.tools.navigation import navigation_broker

        state = navigation_broker().call("go_back", self.browser.cancelled)
        if self.activity is not None:
            self.activity.remember_navigation(state)
        return f"Voltou para: {state['url']}"

    def read_current_page(self):
        import json

        from assistant.tools.navigation import navigation_broker
        from assistant.tools.public_pages import read_article

        context = navigation_broker().call("browser_context", self.browser.cancelled)
        matches = [tab for tab in context["tabs"] if tab["tab_id"] == context["active_tab"]]
        if len(matches) != 1:
            raise ValueError("Não há uma página ativa identificada. Informe qual página deseja usar.")
        article = read_article(matches[0]["url"], self.browser.cancelled)
        return json.dumps({"untrusted_source": article, "title": matches[0]["title"],
                           "note": "Trecho público limitado; não usa cookies nem lê áreas autenticadas."}, ensure_ascii=False)

    def list_research_tasks(self):
        import json

        from assistant.storage.tasks import recent_tasks

        self.runtime()
        return json.dumps(recent_tasks(self.database_path), ensure_ascii=False)

    def resume_research_task(self, task_id):
        from assistant.core.research import research_manager

        settings = self.runtime()
        if not settings.research_enabled:
            raise RuntimeError("As tarefas de pesquisa estão desativadas.")
        identifier = research_manager(self.database_path).resume(settings, task_id)
        return f"Nova tentativa explícita iniciada: {identifier}. Não é retomada de áudio; a pesquisa será refeita e pode gerar consumo AWS."

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
        self.runtime()
        from assistant.storage.applications import ApplicationStore

        try:
            registered = ApplicationStore(self.database_path).resolve(app)
        except ValueError:
            registered = None
        if registered is not None:
            path = Path(registered["executable"])
            if not path.is_file() or path.suffix.lower() != ".exe":
                raise RuntimeError("O executável cadastrado não está disponível. Atualize o cadastro.")
            return path
        system = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
        if app in {"notepad", "calculator"}:
            return system / {"notepad": "notepad.exe", "calculator": "calc.exe"}[app]
        if app == "word":
            import winreg

            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
                                            0, winreg.KEY_READ | view) as key:
                            path = Path(os.path.expandvars(winreg.QueryValue(key, None)).strip('"')).resolve()
                        if path.name.lower() == "winword.exe" and path.is_file():
                            return path
                    except OSError:
                        continue
            raise RuntimeError("O Word não foi encontrado. Gerar DOCX não exige Word instalado.")
        if app != "chrome":
            raise ValueError("Aplicativo não cadastrado. Cadastre-o em Configurações > Aplicativos.")
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

    def resolve_application(self, name):
        from assistant.storage.applications import ApplicationStore

        self.runtime()
        try:
            return ApplicationStore(self.database_path).resolve(name)["name"]
        except ValueError:
            return None

    def list_applications(self, query=""):
        import json

        from assistant.storage.applications import ApplicationStore

        self.runtime()
        store = ApplicationStore(self.database_path)
        return json.dumps({"applications": [{key: app[key] for key in ("name", "aliases")}
                                             for app in store.list()],
                           "suggestions": store.suggest(query) if query else []}, ensure_ascii=False)

    def open_app(self, app):
        import subprocess

        if app == "whatsapp" and self.resolve_application(app) is None:
            from assistant.tools.navigation import navigation_broker

            return navigation_broker().call("open_whatsapp", self.browser.cancelled)
        path = self._executable(app)
        if not path.is_file():
            raise RuntimeError(f"Application not found: {app}")
        if path.name.lower() == "chrome.exe":
            from assistant.tools.navigation import navigation_broker

            return navigation_broker().call("open_browser", str(path), self.browser.cancelled)
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
            "word": {"winword.exe"},
        }
        registered = self.resolve_application(app)
        executable = self._executable(registered) if registered is not None else None
        if executable is None and app not in names:
            raise ValueError("Feche a janela do WhatsApp Web diretamente para preservar suas outras abas.")
        count = 0
        for window in Desktop(backend="win32").windows():
            try:
                process_name = psutil.Process(window.process_id()).name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if executable is not None:
                try:
                    matches = Path(psutil.Process(window.process_id()).exe()).resolve() == executable.resolve()
                except (OSError, psutil.Error):
                    continue
            else:
                matches = process_name in names[app]
            if matches:
                # Request normal close; never kill the process or dismiss save prompts.
                window.post_message(0x0010)
                count += 1
        return f"Requested close for {count} window(s); save dialogs may remain."

    def open_site(self, url):
        from assistant.tools.navigation import browser_requested, navigation_broker

        if self.activity is not None or browser_requested():
            state = navigation_broker().call("navigate_active", url, self.browser.cancelled)
            if self.activity is not None:
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

    def inspect_app(self, app):
        self._windows()
        return self.desktop_tools().inspect(app)

    def describe_ui_action(self, control_id, text=None):
        return self.desktop_tools().describe(control_id, text)

    def click_control(self, control_id):
        return self.desktop_tools().click(control_id)

    def fill_control(self, control_id, text):
        return self.desktop_tools().fill(control_id, text)

    def whatsapp_prepare_message(self, contact, text):
        self.desktop_tools()  # Check the configured permission without inspecting any Windows app.
        from assistant.tools.navigation import navigation_broker

        result = navigation_broker().call("prepare_message", contact, text, self.browser.cancelled)
        import json

        return json.dumps(result, ensure_ascii=False)

    def describe_whatsapp_message(self, draft_id):
        self.desktop_tools()
        from assistant.tools.navigation import navigation_broker

        return navigation_broker().call("describe_message", draft_id, self.browser.cancelled)

    def whatsapp_send_message(self, draft_id):
        self.desktop_tools()
        from assistant.storage.tasks import TaskStore
        from assistant.tools.navigation import navigation_broker

        return navigation_broker().call("send_message", draft_id, TaskStore(self.database_path), self.browser.cancelled)

    def create_word_document(self, title, text):
        from assistant.tools.documents import create_document

        self.browser.check_cancelled()
        path = create_document(title, text)
        return f"Documento criado: {path}. Paginação não verificada por renderização."

    def start_research_report(self, topic, title, pages=1):
        settings = self.runtime()
        if not settings.research_enabled:
            raise RuntimeError("As tarefas de pesquisa estão desativadas nas configurações.")
        from assistant.core.research import research_manager

        self.browser.check_cancelled()
        identifier = research_manager(self.database_path).submit(settings, topic, title, pages)
        return f"Pesquisa iniciada: {identifier}. O documento ainda não está pronto. Acompanhe em Tarefas no banco de dados."

    def research_task_status(self, task_id):
        import json

        from assistant.storage.tasks import TaskStore

        self.runtime()
        task = TaskStore(self.database_path).get(task_id)
        task["sources"] = [{"url": source["url"], "title": source["title"]}
                           for source in json.loads(task["sources"])]
        return json.dumps(task, ensure_ascii=False)

    def cancel_research_task(self, task_id):
        from assistant.core.research import research_manager
        from assistant.storage.tasks import TaskStore

        self.runtime()
        task = TaskStore(self.database_path).get(task_id)
        research_manager(self.database_path).cancel(task["id"])
        return "Cancelamento solicitado. Uma chamada AWS já iniciada pode ter consumo; arquivos prontos são preservados."
