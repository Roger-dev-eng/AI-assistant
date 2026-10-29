import argparse
from dataclasses import replace

from dotenv import load_dotenv

from assistant.ai.bedrock_provider import BedrockProvider
from assistant.cloud.usage_tracker import UsageTracker
from assistant.config import Settings, data_path
from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.security.confirmation import terminal_confirm
from assistant.tools.windows import WindowsTools


def main():
    parser = argparse.ArgumentParser(description="Assistente Windows / Windows assistant")
    parser.add_argument("command", nargs="*", help="Command; omit for interactive mode")
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate tools (cloud may incur cost)"
    )
    parser.add_argument("--offline", action="store_true", help="Disable cloud regardless of .env")
    parser.add_argument("--gui", action="store_true", help="Open the optional PySide6 desktop UI")
    args = parser.parse_args()
    load_dotenv()
    settings = Settings.from_env()
    if args.offline:
        settings = replace(settings, cloud_enabled=False)
    if args.gui:
        if args.command:
            parser.error("--gui does not accept a terminal command")
        try:
            from assistant.ui.app import run_desktop
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("PySide6"):
                parser.error('Install the desktop extra: python -m pip install -e ".[desktop]"')
            raise
        return run_desktop(settings, args.dry_run, args.offline)
    tracker = UsageTracker(data_path())
    executor = ActionExecutor(WindowsTools(), terminal_confirm, args.dry_run)
    assistant = Orchestrator(executor, BedrockProvider(settings, tracker), settings.max_tool_rounds)

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
        tracker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
