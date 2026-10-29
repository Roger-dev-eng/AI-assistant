import argparse
from dataclasses import replace

from dotenv import load_dotenv

from assistant.ai.bedrock_provider import BedrockProvider
from assistant.ai.model_selector import select_model
from assistant.cloud.usage_tracker import UsageTracker
from assistant.config import Settings, data_path
from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.security.confirmation import terminal_confirm
from assistant.storage.memory import ConversationMemory
from assistant.tools.windows import WindowsTools


def main():
    parser = argparse.ArgumentParser(description="Assistente Windows / Windows assistant")
    parser.add_argument("command", nargs="*", help="Command; omit for interactive mode")
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate tools (cloud may incur cost)"
    )
    parser.add_argument("--offline", action="store_true", help="Disable cloud regardless of .env")
    parser.add_argument("--gui", action="store_true", help="Open the optional PySide6 desktop UI")
    parser.add_argument("--tray", action="store_true", help="Start the desktop window in the tray")
    parser.add_argument("--setup", action="store_true", help="Open initial desktop configuration")
    parser.add_argument(
        "--secondary", action="store_true", help="Use the configured alternate model"
    )
    parser.add_argument(
        "--forget", action="store_true", help="Delete saved conversation, preserving usage"
    )
    parser.add_argument(
        "--diagnostics", metavar="FILE", help="Write offline diagnostics JSON and exit"
    )
    args = parser.parse_args()
    load_dotenv()
    settings = Settings.from_env()
    if args.offline:
        settings = replace(settings, cloud_enabled=False)
    if args.diagnostics:
        from assistant.diagnostics import write_diagnostics

        return write_diagnostics(args.diagnostics, settings)
    if args.forget:
        path = data_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        memory = ConversationMemory(path)
        memory.clear()
        memory.close()
        return 0
    if args.gui:
        if args.command:
            parser.error("--gui does not accept a terminal command")
        try:
            from assistant.ui.app import run_desktop
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("PySide6"):
                parser.error('Install the desktop extra: python -m pip install -e ".[desktop]"')
            raise
        return run_desktop(settings, args.dry_run, args.offline, args.tray, args.setup)
    settings = select_model(settings, args.secondary)
    tracker = UsageTracker(data_path())
    executor = ActionExecutor(WindowsTools(), terminal_confirm, args.dry_run)
    memory = (
        ConversationMemory(data_path(), settings.memory_retention_days, settings.memory_max_turns)
        if settings.memory_enabled
        else None
    )
    assistant = Orchestrator(
        executor, BedrockProvider(settings, tracker), settings.max_tool_rounds, memory
    )

    def run(text):
        executor.cancelled.clear()
        try:
            print(assistant.run(text))
            return 0
        except KeyboardInterrupt:
            executor.cancelled.set()
            print("\nTarefa interrompida / Task interrupted.")
            return 130
        except Exception as exc:
            print(f"Erro / Error: {exc}")
            return 1

    try:
        if args.command:
            return run(" ".join(args.command))
        print("Assistente — sair/exit para encerrar; Ctrl+C interrompe a tarefa.")
        while True:
            try:
                text = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"sair", "exit", "quit"}:
                break
            if text.lower() in {"/usage", "/consumo"}:
                count, cost = tracker.summary()
                print(f"{count} cloud request(s); estimated USD {cost:.6f} (all time).")
                continue
            run(text)
    finally:
        if memory is not None:
            memory.close()
        tracker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
