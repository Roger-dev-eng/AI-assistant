from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QThread, Signal

from assistant.ai.bedrock_provider import BedrockProvider
from assistant.cloud.usage_tracker import UsageTracker
from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.storage.memory import ConversationMemory
from assistant.tools.windows import WindowsTools, automation_context


@dataclass
class ConfirmationRequest:
    description: str
    answered: Event = field(default_factory=Event)
    accepted: bool = False

    def answer(self, accepted):
        if not self.answered.is_set():
            self.accepted = bool(accepted)
            self.answered.set()


class TaskWorker(QThread):
    """Run one task. SQLite and COM objects live only in this worker thread."""

    result = Signal(str)
    failed = Signal(str)
    confirmation_requested = Signal(object)
    usage_updated = Signal(int, float)

    def __init__(
        self,
        text,
        settings,
        database_path,
        dry_run=False,
        parent=None,
        backend_factory=WindowsTools,
        provider_factory=BedrockProvider,
    ):
        super().__init__(parent)
        self.text = text
        self.settings = settings
        self.database_path = database_path
        self.dry_run = dry_run
        self.cancelled = Event()
        self.backend_factory = backend_factory
        self.provider_factory = provider_factory

    def confirm(self, description):
        if self.cancelled.is_set():
            raise InterruptedError("Tarefa interrompida / Task interrupted.")
        request = ConfirmationRequest(description)
        self.confirmation_requested.emit(request)
        while not request.answered.wait(0.05):
            if self.cancelled.is_set():
                raise InterruptedError("Tarefa interrompida / Task interrupted.")
        if self.cancelled.is_set():
            raise InterruptedError("Tarefa interrompida / Task interrupted.")
        return request.accepted

    def run(self):
        tracker = None
        memory = None
        try:
            tracker = UsageTracker(self.database_path)
            if self.settings.memory_enabled:
                memory = ConversationMemory(
                    self.database_path,
                    self.settings.memory_retention_days,
                    self.settings.memory_max_turns,
                )
            with automation_context():
                executor = ActionExecutor(
                    self.backend_factory(), self.confirm, self.dry_run, self.cancelled
                )
                provider = self.provider_factory(self.settings, tracker)
                assistant = Orchestrator(executor, provider, self.settings.max_tool_rounds, memory)
                output = assistant.run(self.text)
                if self.cancelled.is_set():
                    raise InterruptedError("Tarefa interrompida / Task interrupted.")
                self.result.emit(output)
        except InterruptedError:
            self.result.emit("Tarefa interrompida / Task interrupted.")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if memory is not None:
                memory.close()
            if tracker is not None:
                try:
                    count, cost = tracker.summary()
                    self.usage_updated.emit(count, cost)
                finally:
                    tracker.close()
