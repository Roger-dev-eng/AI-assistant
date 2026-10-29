import json

from assistant.core.intent_router import Action, IntentRouter
from assistant.tools.registry import validate


class Orchestrator:
    def __init__(self, executor, provider, max_rounds=5):
        self.router = IntentRouter()
        self.executor = executor
        self.provider = provider
        self.max_rounds = max_rounds

    def run(self, text):
        self.executor.begin_task()
        if not text.strip():
            return "Digite um comando / Enter a command."
        if len(text.encode("utf-8")) > 12000:
            raise ValueError("Command is too long.")
        local = self.router.route(text)
        if local is not None:
            if len(local) > 10:
                raise ValueError("Too many local actions in one task.")
            outputs = self.executor.execute_plan(local)
            formatted = []
            for action, output in zip(local, outputs):
                if action.name == "read_search_results" and not self.executor.dry_run:
                    results = json.loads(output)["untrusted_search_results"]
                    output = "\n\n".join(
                        f"{index}. {item['title']}\n{item['url']}"
                        for index, item in enumerate(results, 1)
                    )
                    output += "\n\nTítulos e links; as páginas de destino não foram lidas."
                formatted.append(output)
            return "\n".join(formatted)
        messages = [{"role": "user", "content": [{"text": text}]}]
        for _ in range(self.max_rounds):
            if self.executor.cancelled.is_set():
                raise InterruptedError("Task interrupted.")
            message = self.provider.converse(messages)
            if self.executor.cancelled.is_set():
                raise InterruptedError("Task interrupted.")
            calls = [block["toolUse"] for block in message["content"] if "toolUse" in block]
            if not calls:
                return "\n".join(block["text"] for block in message["content"] if "text" in block)
            if len(calls) > 10:
                raise ValueError("Too many tools in one response.")
            # Validate every call, including unknown tools, before any side effects.
            identifiers = set()
            for call in calls:
                identifier = call.get("toolUseId")
                if not isinstance(identifier, str) or not identifier or identifier in identifiers:
                    raise ValueError("Missing or duplicate tool use identifier.")
                identifiers.add(identifier)
                validate(call["name"], call["input"])
            messages.append(message)
            results = []
            for call in calls:
                try:
                    output = self.executor.execute(Action(call["name"], call["input"]))
                    status = "success"
                except InterruptedError:
                    raise
                except Exception as exc:
                    output, status = str(exc), "error"
                results.append(
                    {
                        "toolResult": {
                            "toolUseId": call["toolUseId"],
                            "content": [{"text": output}],
                            "status": status,
                        }
                    }
                )
                if output == "Action denied by user.":
                    return "Ação cancelada pelo usuário / Action cancelled by user."
            messages.append({"role": "user", "content": results})
        return "Limite de etapas atingido / Step limit reached."
