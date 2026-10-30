from threading import Event
from uuid import uuid4

from assistant.runtime_log import mark
from assistant.tools.registry import validate


class ActionExecutor:
    def __init__(self, backend, confirm, dry_run=False, cancelled=None, activity=None,
                 settings=None, database_path=None):
        self.backend = backend
        self.confirm = confirm
        self.dry_run = dry_run
        self.cancelled = cancelled or Event()
        self.activity = activity if not dry_run else None
        self.command_text = ""
        self.task_id = uuid4().hex
        self.message_send_attempted = False
        configure = getattr(type(backend), "configure_runtime", None)
        if configure is not None and settings is not None:
            configure(backend, settings, database_path)
        if self.activity is not None:
            bind_activity = getattr(type(backend), "bind_activity", None)
            if bind_activity is not None:
                bind_activity(backend, self.activity)
        bind = getattr(type(backend), "bind_cancellation", None)
        if bind is not None:
            bind(backend, self.cancelled)

    def begin_task(self):
        self.task_id = uuid4().hex
        self.message_send_attempted = False
        reset = getattr(type(self.backend), "reset_task", None)
        if reset is not None:
            reset(self.backend)

    def set_command(self, text):
        self.command_text = text

    def current_search_site(self):
        method = getattr(type(self.backend), "current_search_site", None)
        return method(self.backend) if self.activity is not None and method else None

    def resolve_application(self, name):
        method = getattr(type(self.backend), "resolve_application", None)
        return method(self.backend, name) if method else None

    def execute(self, action):
        try:
            result = self._execute(action)
        except Exception as exc:
            if self.activity is not None:
                self.record(action, "error", type(exc).__name__)
            raise
        if self.activity is not None:
            self.record(action, "denied" if result == "Action denied by user." else "completed", result)
        return result

    def record(self, action, status, result):
        try:
            self.activity.record(self.task_id, self.command_text, action, status, result)
        except Exception:
            mark("activity.write.failed")  # Never turn a completed action into a retryable failure.

    def _execute(self, action):
        tool = validate(action.name, action.arguments)
        if self.cancelled.is_set():
            raise InterruptedError("Task interrupted.")
        description = f"{action.name} {action.arguments}"
        if self.dry_run:
            return f"SIMULATION: {description}"
        if action.name == "open_search_result":
            description = self.backend.describe_result(action.arguments["result_id"])
        elif action.name == "open_correlated_result":
            description = self.backend.describe_correlated_result(action.arguments["position"])
        elif action.name in {"click_control", "fill_control"}:
            description = self.backend.describe_ui_action(action.arguments["control_id"],
                                                          action.arguments.get("text"))
        elif action.name == "whatsapp_send_message":
            if self.message_send_attempted:
                raise RuntimeError("Um envio já foi tentado nesta tarefa. Confira o WhatsApp antes de um novo pedido.")
            description = self.backend.describe_whatsapp_message(action.arguments["draft_id"])
        # High volume also requires explicit approval, regardless of the source of the action.
        sensitive = tool.confirmation or (
            action.name == "set_volume" and action.arguments["percent"] > 70
        )
        if sensitive and not self.confirm(description):
            return "Action denied by user."
        if self.cancelled.is_set():
            raise InterruptedError("Task interrupted.")
        if action.name == "whatsapp_send_message":
            self.message_send_attempted = True
        return getattr(self.backend, tool.name)(**action.arguments)

    def execute_plan(self, actions):
        # Reject the entire plan before the first side effect if any schema is invalid.
        for action in actions:
            validate(action.name, action.arguments)
        results = []
        for action in actions:
            result = self.execute(action)
            results.append(result)
            if result == "Action denied by user.":
                break
        return results
