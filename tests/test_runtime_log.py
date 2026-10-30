import json
import os
import subprocess
import sys


def test_lifecycle_logging_is_idempotent_and_excludes_private_fields(tmp_path):
    script = (
        "from assistant.runtime_log import configure, mark\n"
        "configure()\nconfigure()\n"
        "mark('test.stage', code=5, command='private-command', token='private-token')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
        env=dict(os.environ, ASSISTANT_LOG_DIR=str(tmp_path)),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    files = list(tmp_path.glob("runtime-*.jsonl"))
    assert len(files) == 1
    text = files[0].read_text("utf-8")
    records = [json.loads(line) for line in text.splitlines()]
    assert [record["event"] for record in records] == [
        "process.start", "test.stage", "python.atexit",
    ]
    assert records[1]["code"] == 5
    assert all(record["pid"] == records[0]["pid"] for record in records)
    assert "private-command" not in text
    assert "private-token" not in text
    assert len(list(tmp_path.glob("fault-*.log"))) == 1
