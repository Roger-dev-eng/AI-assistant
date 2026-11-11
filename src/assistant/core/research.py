"""Research jobs have their own context and lifecycle, independent of a Sonic voice session."""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from importlib.resources import files
from threading import Event, Lock

from assistant.ai.bedrock_provider import BedrockProvider
from assistant.cloud.usage_tracker import UsageTracker
from assistant.core.intent_router import research_clarification
from assistant.storage.tasks import TaskStore
from assistant.tools.browser import BrowserTools
from assistant.tools.documents import create_document
from assistant.tools.public_pages import read_article


def run_research(identifier, store, settings, cancelled, browser=None, reader=read_article,
                 writer=create_document, provider_factory=BedrockProvider):
    tracker, provider = None, None
    deadline = time.monotonic() + 180

    def checkpoint():
        if cancelled.is_set():
            raise InterruptedError("Pesquisa cancelada; arquivos existentes foram preservados.")
        if time.monotonic() > deadline:
            raise TimeoutError("A tarefa atingiu o limite de três minutos.")

    try:
        task = store.get(identifier)
        checkpoint()
        if clarification := research_clarification(task["topic"]):
            raise ValueError(clarification)
        if not settings.cloud_enabled:
            raise RuntimeError("Habilite AWS para redigir o relatório; nenhuma chamada foi realizada.")
        store.update(identifier, "searching")
        browser = browser or BrowserTools()
        browser.cancelled = cancelled
        results = json.loads(browser.read_search_results(task["topic"], "google"))["untrusted_search_results"]
        sources, failures = [], []
        for item in results[:5]:
            checkpoint()
            store.update(identifier, "reading")
            try:
                article = reader(item["url"], cancelled)
                if any(source["url"] == article["url"] or source["text"] == article["text"] for source in sources):
                    continue
                sources.append({"title": item["title"], **article})
            except InterruptedError:
                raise
            except Exception as exc:
                failures.append(type(exc).__name__)
            store.update(identifier, "reading", sources=sources)
            if len(sources) == 3:
                break
        if not sources:
            raise RuntimeError("Não foi possível ler fontes públicas suficientes. "
                               "Login, CAPTCHA, PDF ou páginas só com JavaScript não foram contornados.")
        checkpoint()
        store.update(identifier, "writing")
        request_settings = replace(settings, max_input_bytes=64000,
                                   max_output_tokens=1200 * task["pages"] + 400)
        tracker = UsageTracker(store.path)
        provider = provider_factory(request_settings, tracker, tool_names=())
        provider.system = files("assistant.ai").joinpath("skills/research-report/SKILL.md").read_text("utf-8")
        message = provider.converse([{"role": "user", "content": [{"text": json.dumps({
            "topic": task["topic"], "title": task["title"], "approximate_pages": task["pages"],
            "maximum_words": 280 * task["pages"],
            "sources": [{"number": index, **source} for index, source in enumerate(sources, 1)],
        }, ensure_ascii=False)}]}])
        checkpoint()
        if any("toolUse" in block for block in message["content"]):
            raise RuntimeError("O modelo não retornou o texto solicitado. Nenhum documento foi criado.")
        if provider.last_stop_reason == "max_tokens":
            raise RuntimeError("O relatório foi cortado pelo limite do modelo; nenhum arquivo incompleto foi salvo.")
        text = "\n\n".join(block["text"] for block in message["content"] if "text" in block).strip()
        if text == "EVIDENCIA_INSUFICIENTE":
            raise RuntimeError("As fontes encontradas não sustentam o relatório para o recorte solicitado.")
        citations = re.findall(r"\[(\d+)\]", text)
        valid_citations = {str(number) for number in range(1, len(sources) + 1)}
        if not citations or any(number not in valid_citations for number in citations):
            raise RuntimeError("O relatório não apresentou citações válidas para as fontes consultadas.")
        if not text or len(text.split()) > 350 * task["pages"]:
            raise RuntimeError("O modelo não respeitou o tamanho solicitado. Nenhum texto foi truncado silenciosamente.")
        store.update(identifier, "creating_document")
        checkpoint()
        path = writer(task["title"], text, sources)
        # Creation is committed: a late cancellation must not hide the file that exists.
        store.update(identifier, "completed", output_path=path,
                     message="Documento criado. Paginação aproximada, não renderizada. " +
                     (f"{len(failures)} fonte(s) não puderam ser lidas." if failures else ""))
    except InterruptedError as exc:
        store.update(identifier, "cancelled", message=str(exc))
    except Exception as exc:
        store.update(identifier, "failed", message=str(exc))
    finally:
        try:
            if provider is not None and provider.client is not None:
                provider.client.close()
        finally:
            if tracker is not None:
                tracker.close()


class ResearchManager:
    def __init__(self, path):
        self.store = TaskStore(path)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="assistant-research")
        self.jobs = {}
        self.restarts = {}
        self.lock = Lock()

    def submit(self, settings, topic, title, pages):
        if clarification := research_clarification(topic):
            raise ValueError(clarification)
        if not settings.cloud_enabled:
            raise RuntimeError("A redação do relatório requer AWS habilitada.")
        with self.lock:
            self.jobs = {key: value for key, value in self.jobs.items() if not value[1].done()}
            if len(self.jobs) >= 3:
                raise RuntimeError("Já há três pesquisas na fila. Aguarde ou cancele uma delas.")
            identifier = self.store.create(topic, title, pages)
            cancelled = Event()
            future = self.pool.submit(run_research, identifier, self.store, settings, cancelled)
            self.jobs[identifier] = (cancelled, future)
        return identifier

    def resume(self, settings, identifier):
        task = self.store.get(identifier)
        with self.lock:
            if task["id"] in self.restarts:
                raise ValueError(f"Já existe uma nova tentativa dessa pesquisa: {self.restarts[task['id']]}. Consulte essa referência.")
            running = self.jobs.get(task["id"])
            if running and not running[1].done():
                raise ValueError("Essa pesquisa ainda está em execução. Consulte seu estado.")
        if task["status"] == "completed" or task["output_path"]:
            raise ValueError("Essa pesquisa já tem um documento. Consulte o arquivo existente antes de pedir outra pesquisa.")
        new_id = self.submit(settings, task["topic"], task["title"], task["pages"])
        with self.lock:
            self.restarts[task["id"]] = new_id
        return new_id

    def cancel(self, identifier):
        with self.lock:
            if identifier not in self.jobs or self.jobs[identifier][1].done():
                raise ValueError("Essa tarefa não está executando nesta sessão.")
            cancelled, future = self.jobs[identifier]
            cancelled.set()
            if future.cancel():
                self.store.update(identifier, "cancelled", message="Cancelada antes de iniciar.")
            else:
                self.store.update(identifier, "cancelling", message="Cancelamento solicitado; aguardando etapa segura.")

    def close(self):
        with self.lock:
            for identifier, (cancelled, future) in self.jobs.items():
                if not future.done():
                    cancelled.set()
                    self.store.update(identifier, "cancelled", message="Aplicativo encerrado; não houve retomada automática.")
        self.pool.shutdown(wait=True, cancel_futures=True)


_managers = {}
_lock = Lock()


def research_manager(path):
    key = str(path)
    with _lock:
        if key not in _managers:
            _managers[key] = ResearchManager(path)
        return _managers[key]


def shutdown_research():
    with _lock:
        managers = list(_managers.values())
        _managers.clear()
    for manager in managers:
        manager.close()
