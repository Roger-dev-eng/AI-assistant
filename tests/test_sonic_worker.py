from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("PySide6")

from assistant.ai.sonic_provider import SonicResult
from assistant.config import Settings
from assistant.ui.sonic_worker import SonicWorker


@pytest.mark.parametrize("wake", [False, True])
def test_sonic_worker_captures_and_dispatches_audio(tmp_path, wake):
    np = pytest.importorskip("numpy")
    provider = Mock()
    provider.run.return_value = SonicResult("Olá", "Olá!", b"")
    factory = Mock(return_value=provider)
    worker = SonicWorker(
        replace(Settings(), cloud_enabled=True), tmp_path / "usage.sqlite3",
        wake=wake, provider_factory=factory, backend_factory=Mock,
    )
    errors, results = [], []
    worker.failed.connect(errors.append)
    worker.result.connect(results.append)
    capture = "listen_for_command" if wake else "record_microphone"
    with patch(f"assistant.ui.sonic_worker.{capture}",
               return_value=np.ones(1600, dtype="float32") * 0.1) as recorder:
        worker.run()
    assert not errors
    assert results == ["Olá!"]
    args = recorder.call_args.args
    assert args[3 if wake else 1] is worker.recording_finished
    assert not worker.recording_finished.is_set()
    provider.run.assert_called_once()
    assert len(provider.run.call_args.args[0]) == 3200
