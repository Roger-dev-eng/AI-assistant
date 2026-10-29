from threading import Event

from assistant.tools.registry import validate


class ActionExecutor:
    def __init__(self, backend, confirm, dry_run=False, cancelled=None):
        self.backend = backend
        self.confirm = confirm
        self.dry_run = dry_run
        self.cancelled = cancelled or Event()

    def execute(self, action):
        tool = validate(action.name, action.arguments)
        if self.cancelled.is_set():
            raise InterruptedError("Task interrupted.")
        description = f"{action.name} {action.arguments}"
        if self.dry_run:
            return f"SIMULATION: {description}"
        # High volume also requires explicit approval, regardless of the source of the action.
        sensitive = tool.confirmation or (
            action.name == "set_volume" and action.arguments["percent"] > 70
        )
        if sensitive and not self.confirm(description):
            return "Action denied by user."
        if self.cancelled.is_set():
            raise InterruptedError("Task interrupted.")
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
