import importlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock

from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.tools.windows import WindowsTools


def write_diagnostics(path, settings):
    checks = {}
    for name in (
        "boto3",
        "PySide6.QtWidgets",
        "playwright.sync_api",
        "faster_whisper",
        "piper",
        "sounddevice",
        "pywinauto",
        "pycaw.pycaw",
        "aws_sdk_bedrock_runtime",
        "smithy_http.aio.crt",
        "awscrt",
    ):
        try:
            importlib.import_module(name)
            checks[name] = "ok"
        except Exception as exc:
            checks[name] = str(exc)
    provider = Mock()
    if getattr(sys, "frozen", False):
        from assistant.updates import updater_executable

        checks["native_updater"] = "ok" if updater_executable().is_file() else "missing"
    result = Orchestrator(
        ActionExecutor(WindowsTools(), lambda _: False, dry_run=True), provider
    ).run("Open Chrome and search Python on YouTube")
    report = {
        "python": sys.version,
        "frozen": bool(getattr(sys, "frozen", False)),
        "imports": checks,
        "offline_simulation": result,
        "cloud_calls": provider.converse.call_count,
        "voice_models_configured": bool(settings.whisper_model_path),
    }
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    return (
        0 if all(value == "ok" for value in checks.values()) and not provider.converse.called else 1
    )
