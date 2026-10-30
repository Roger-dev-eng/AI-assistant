"""Crash-surviving lifecycle diagnostics; never record commands or credentials."""

import atexit
import faulthandler
import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

_fd = None
_fault_fd = None
_started = time.monotonic()
_lock = threading.RLock()
_FIELDS = {"code", "stage", "available", "worker", "dialog", "exiting", "frozen",
           "python", "platform", "error_type", "tray", "delivered"}


def mark(event, **details):
    """Write only explicitly allowed metadata, flushing before the next Qt operation."""
    if _fd is None:
        return
    record = {
        "time": datetime.now(UTC).isoformat(), "pid": os.getpid(),
        "parent_pid": os.getppid(), "thread": threading.get_ident(),
        "elapsed": round(time.monotonic() - _started, 6), "event": event,
        **{key: value for key, value in details.items() if key in _FIELDS},
    }
    try:
        payload = (json.dumps(record, ensure_ascii=True) + "\n").encode("utf-8")
        with _lock:
            os.write(_fd, payload)
            os.fsync(_fd)
    except (OSError, ValueError, TypeError):
        pass  # Diagnostics must never prevent startup or shutdown.


def configure():
    """Keep raw descriptors alive through interpreter/Qt destruction until process exit."""
    global _fd, _fault_fd
    if _fd is not None:
        return
    base = Path(os.environ.get("ASSISTANT_DATA_DIR") or
                str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AssistantDesktop"))
    directory = Path(os.environ.get("ASSISTANT_LOG_DIR") or str(base / "logs"))
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Retain recent sessions; Windows leaves files open by another process untouched.
        old = sorted(directory.glob("runtime-*.jsonl"), key=lambda path: path.stat().st_mtime)
        for path in old[:-20]:
            try:
                if time.time() - path.stat().st_mtime > 7 * 86400:
                    path.unlink(missing_ok=True)
                    path.with_name(path.name.replace("runtime-", "fault-")).with_suffix(".log").unlink(
                        missing_ok=True)
            except OSError:
                pass
        name = f"{os.getpid()}-{time.time_ns()}"
        _fd = os.open(directory / f"runtime-{name}.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        _fault_fd = os.open(directory / f"fault-{name}.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        faulthandler.enable(file=_fault_fd, all_threads=True)
    except (OSError, RuntimeError):
        return
    mark("process.start", python=sys.version.split()[0], frozen=bool(getattr(sys, "frozen", False)))
    atexit.register(mark, "python.atexit")
    original = sys.excepthook

    def exception_hook(kind, value, traceback):
        mark("python.unhandled_exception", error_type=kind.__name__)
        faulthandler.dump_traceback(file=_fault_fd, all_threads=True)
        original(kind, value, traceback)

    sys.excepthook = exception_hook
