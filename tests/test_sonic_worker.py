from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("PySide6")

from assistant.ai.sonic_provider import SonicProvider, SonicResult
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


def test_timeout_after_action_has_reason_and_confirmed_action(tmp_path):
    np = pytest.importorskip("numpy")

    class TimeoutAfterAction(SonicProvider):
        def run(self, pcm):
            self.tools_requested = True
            self.actions_completed.append("Abertura de chrome concluída.")
            self.stage = "Ação processada; aguardando resposta do Nova 2 Sonic"
            raise TimeoutError()

    worker = SonicWorker(
        replace(Settings(), cloud_enabled=True), tmp_path / "usage.sqlite3",
        provider_factory=TimeoutAfterAction, backend_factory=Mock,
    )
    errors = []
    worker.failed.connect(errors.append)
    with patch("assistant.ui.sonic_worker.record_microphone",
               return_value=np.ones(1600, dtype="float32") * 0.1):
        worker.run()
    assert len(errors) == 1
    assert "tempo limite" in errors[0]
    assert "Abertura de chrome concluída" in errors[0]
    assert "antes de repetir" in errors[0]


def test_sonic_audio_is_played_automatically(tmp_path):
    np = pytest.importorskip("numpy")
    provider = Mock()
    provider.run.return_value = SonicResult("Olá", "Olá!", b"\x01\x00" * 24)
    worker = SonicWorker(
        replace(Settings(), cloud_enabled=True, voice_enabled=False), tmp_path / "usage.sqlite3",
        provider_factory=Mock(return_value=provider), backend_factory=Mock,
    )
    errors = []
    worker.failed.connect(errors.append)
    with (
        patch("assistant.ui.sonic_worker.record_microphone",
              return_value=np.ones(1600, dtype="float32") * 0.1),
        patch("assistant.ui.sonic_worker.play_wav") as play,
    ):
        worker.run()
    assert not errors
    play.assert_called_once()
    assert play.call_args.args[0].startswith(b"RIFF")
