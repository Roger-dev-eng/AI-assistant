"""One Playwright owner thread for an explicit, visible, app-controlled browser window."""

import queue
import time
from concurrent.futures import Future
from threading import Lock, Thread
from urllib.parse import urlsplit
from uuid import uuid4

from assistant.security.urls import public_https_url, verify_public_resolution
from assistant.tools.browser import clean_result, extract_search_results


def site_of(url):
    host = (urlsplit(url).hostname or "").lower()
    return next((site for site in ("youtube", "google", "github")
                 if host in {site + ".com", "www." + site + ".com"}), None)


class NavigationSession:
    def __init__(self, playwright):
        self.playwright = playwright
        self.browser = None
        self.context = None
        self.pages = {}
        self.run_id = uuid4().hex
        self.selected = {}
        self.whatsapp_page = None
        self.whatsapp = None

    def ensure_browser(self):
        if self.browser is not None and self.browser.is_connected():
            return
        self.pages.clear()
        self.selected.clear()
        self.run_id = uuid4().hex
        for channel in ("chrome", "msedge"):
            try:
                self.browser = self.playwright.chromium.launch(channel=channel, headless=False, timeout=10000)
                break
            except Exception:
                self.browser = None
        if self.browser is None:
            raise RuntimeError("A navegação correlacionada requer Chrome ou Edge instalado. "
                               "Não foi possível abrir a janela controlada pelo assistente.")
        self.context = self.browser.new_context(accept_downloads=False, locale="pt-BR")
        self.context.set_default_timeout(8000)

        def guard(route):
            try:
                if route.request.resource_type == "document":
                    verify_public_resolution(route.request.url)
                else:
                    # Media URLs may contain long signed queries; validate their
                    # origin without applying the tool argument's 2,000-byte limit.
                    parts = urlsplit(route.request.url)
                    public_https_url(f"{parts.scheme}://{parts.netloc}/")
            except (ValueError, OSError):
                route.abort()
            else:
                route.continue_()

        self.context.route("**/*", guard)
        self.context.on("page", lambda page: page.on("download", lambda item: item.cancel()))

    def find_page(self, saved, site):
        if not saved or saved["run_id"] != self.run_id:
            return None
        page = self.pages.get(saved["tab_id"])
        if page is None or page.is_closed():
            return None
        try:
            live_url = page.evaluate("() => location.href")
        except Exception:
            return None
        if (site_of(live_url) or "external") != site:
            return None
        return page

    def state(self, tab_id, page):
        return {"run_id": self.run_id, "tab_id": tab_id, "url": public_https_url(page.url),
                "site": site_of(page.url) or "external"}

    def navigate(self, url, saved, cancelled, reuse_source=False):
        verify_public_resolution(url)
        self.ensure_browser()
        if cancelled.is_set():
            raise InterruptedError("Navegação interrompida.")
        site = site_of(url) or "external"
        page = self.find_page(saved, saved["site"] if saved and reuse_source else site)
        if not self.browser.is_connected():
            self.ensure_browser()
            page = None
        if page is None:
            try:
                page = self.context.new_page()
            except Exception:
                if self.browser.is_connected():
                    raise
                self.ensure_browser()
                page = self.context.new_page()
            tab_id = uuid4().hex
            self.pages[tab_id] = page
        else:
            tab_id = saved["tab_id"]
        if cancelled.is_set():
            raise InterruptedError("Navegação interrompida.")
        if page.url.rstrip("/") != url.rstrip("/"):
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if cancelled.is_set():
            raise InterruptedError("Navegação interrompida; confira a aba antes de repetir.")
        if (site_of(page.url) or "external") != site:
            raise RuntimeError("A página mudou de site. Não foi possível confirmar a navegação.")
        page.bring_to_front()
        return self.state(tab_id, page)

    def describe_position(self, saved, position, cancelled):
        if isinstance(position, bool) or position not in range(1, 6):
            raise ValueError("Escolha um resultado entre 1 e 5.")
        position = int(position)
        if (not saved or saved["run_id"] != self.run_id or self.browser is None
                or not self.browser.is_connected()):
            raise RuntimeError("A pesquisa anterior não está aberta nesta sessão. Pesquise novamente.")
        self.ensure_browser()
        page = self.find_page(saved, saved["site"] if saved else None)
        expected_path = "/results" if saved and saved["site"] == "youtube" else "/search"
        if page is None or page.url != saved["url"] or urlsplit(page.url).path != expected_path:
            raise RuntimeError("A aba ou a pesquisa anterior não está mais disponível. Faça a pesquisa novamente.")
        if cancelled.is_set():
            raise InterruptedError("Navegação interrompida.")
        selector = "a#video-title, a#video-title-link" if saved["site"] == "youtube" else "a:has(h3)"
        page.locator(selector).first.wait_for(state="attached", timeout=8000)
        found, seen = [], set()
        for item in extract_search_results(page, saved["site"]):
            try:
                item = clean_result(item, saved["site"])
            except ValueError:
                continue
            if item["url"] not in seen:
                found.append(item)
                seen.add(item["url"])
            if len(found) >= 5:
                break
        if not 1 <= position <= len(found):
            raise RuntimeError("O resultado solicitado não está disponível nesta pesquisa.")
        selected = {**found[position - 1], "source_url": page.url, "position": position}
        self.selected[saved["tab_id"]] = selected
        return selected

    def open_position(self, saved, position, cancelled):
        old = self.selected.get(saved["tab_id"]) if saved else None
        current = self.describe_position(saved, position, cancelled)
        if old != current:
            raise RuntimeError("Os resultados mudaram após a confirmação. Peça para abrir novamente.")
        return self.navigate(current["url"], saved, cancelled, reuse_source=True)

    def open_link(self, url, saved, cancelled):
        return self.navigate(url, saved, cancelled, reuse_source=True)

    def whatsapp_window(self, cancelled):
        self.ensure_browser()
        if cancelled.is_set():
            raise InterruptedError("WhatsApp interrompido.")
        page = self.whatsapp_page
        try:
            valid = page is not None and not page.is_closed() and urlsplit(page.evaluate("() => location.href")).hostname == "web.whatsapp.com"
        except Exception:
            valid = False
        if not valid:
            page = self.context.new_page()
            page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=15000)
            self.pages[uuid4().hex] = page
            self.whatsapp_page = page
        page.bring_to_front()
        if urlsplit(page.url).hostname != "web.whatsapp.com":
            raise RuntimeError("A janela do WhatsApp mudou de endereço.")
        return page

    def messaging(self):
        if self.whatsapp is None:
            from assistant.tools.messaging import WhatsAppTools

            self.whatsapp = WhatsAppTools(self.whatsapp_window)
        return self.whatsapp

    def open_whatsapp(self, cancelled):
        self.whatsapp_window(cancelled)
        return "WhatsApp Web aberto na janela do assistente. Conecte pelo QR code se solicitado."

    def prepare_message(self, contact, text, cancelled):
        return self.messaging().prepare(contact, text, cancelled)

    def describe_message(self, identifier, cancelled):
        return self.messaging().describe(identifier, cancelled)

    def send_message(self, identifier, store, cancelled):
        return self.messaging().send(identifier, store, cancelled)

    def close(self):
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception:
            pass


class NavigationBroker:
    def __init__(self):
        self.requests = queue.Queue(maxsize=16)
        self.thread = Thread(target=self.run, name="assistant-browser", daemon=True)
        self.thread.start()

    def run(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            session = NavigationSession(playwright)
            try:
                while True:
                    try:
                        request = self.requests.get(timeout=0.05)
                    except queue.Empty:
                        # Sync Playwright must pump events while idle, otherwise routed
                        # page/video requests would stall between voice commands.
                        for tab_id, page in list(session.pages.items()):
                            if page.is_closed():
                                session.pages.pop(tab_id, None)
                                session.selected.pop(tab_id, None)
                                continue
                            if not page.is_closed():
                                try:
                                    page.wait_for_timeout(50)
                                except Exception:
                                    pass
                                break
                        continue
                    if request is None:
                        return
                    method, args, future = request
                    try:
                        future.set_result(getattr(session, method)(*args))
                    except Exception as exc:
                        future.set_exception(exc)
            finally:
                session.close()

    def call(self, method, *args):
        future = Future()
        self.requests.put_nowait((method, args, future))
        deadline = time.monotonic() + 45
        while True:
            try:
                return future.result(timeout=0.1)
            except TimeoutError as exc:
                if future.done():
                    raise
                if not self.thread.is_alive():
                    raise RuntimeError("Não foi possível iniciar o controle do navegador.") from exc
                if time.monotonic() >= deadline:
                    args[-1].set()
                    raise RuntimeError("O navegador não respondeu a tempo. Confira a aba antes de repetir.") from exc

    def close(self):
        try:
            self.requests.put_nowait(None)
        except queue.Full:
            return
        self.thread.join(timeout=20)


_lock = Lock()
_broker = None


def navigation_broker():
    global _broker
    with _lock:
        if _broker is None or not _broker.thread.is_alive():
            _broker = NavigationBroker()
        return _broker


def shutdown_navigation():
    global _broker
    with _lock:
        broker, _broker = _broker, None
    if broker is not None:
        broker.close()
