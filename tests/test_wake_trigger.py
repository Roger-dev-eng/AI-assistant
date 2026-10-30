import json
from threading import Event
from unittest.mock import Mock

import pytest

from assistant.audio.wake_trigger import keyword_detected, make_recognizer, wait_for_keyword


def result(text, confidence=0.95):
    return json.dumps({"text": text, "result": [{"word": text, "conf": confidence}]})


@pytest.mark.parametrize("text,confidence,expected", [
    ("assistente", 0.95, True), ("assistente", 0.4, False),
    ("[unk]", 1, False), ("abrir chrome", 1, False), ("", 1, False),
])
def test_only_confident_keyword_activates(text, confidence, expected):
    assert keyword_detected(result(text, confidence)) is expected


class FakeStream:
    def __init__(self, blocks=2, **kwargs):
        self.callback = kwargs["callback"]
        self.blocks = blocks
        self.closed = False

    def __enter__(self):
        for _ in range(self.blocks):
            self.callback(b"\0\0" * 1600, 1600, None, False)
        return self

    def __exit__(self, *args):
        self.closed = True


def test_wait_ignores_other_words_and_closes_microphone_on_activation():
    recognizer = Mock()
    recognizer.AcceptWaveform.return_value = True
    recognizer.Result.side_effect = [result("[unk]"), result("assistente")]
    streams = []

    def stream_factory(**kwargs):
        streams.append(FakeStream(**kwargs))
        return streams[-1]

    phases = []
    wait_for_keyword(Event(), phases.append, lambda: recognizer, stream_factory)
    assert recognizer.AcceptWaveform.call_count == 2
    assert streams[0].closed
    assert "sem conexão AWS" in phases[0]


def test_cancel_stops_an_idle_listener_without_waiting_for_speech():
    cancelled = Event()
    stream = None

    def stream_factory(**kwargs):
        nonlocal stream
        stream = FakeStream(blocks=0, **kwargs)
        return stream

    with pytest.raises(InterruptedError):
        wait_for_keyword(cancelled, lambda _: cancelled.set(), Mock, stream_factory)
    assert stream.closed


def test_cancel_before_start_does_not_load_model_or_open_microphone():
    cancelled = Event()
    cancelled.set()
    factory = Mock()
    with pytest.raises(InterruptedError):
        wait_for_keyword(cancelled, Mock(), factory, factory)
    factory.assert_not_called()


def test_queue_overflow_fails_instead_of_triggering_on_incomplete_audio():
    recognizer = Mock()
    with pytest.raises(RuntimeError, match="perdeu áudio"):
        wait_for_keyword(
            Event(), Mock(), lambda: recognizer,
            lambda **kwargs: FakeStream(blocks=33, **kwargs),
        )
    recognizer.AcceptWaveform.assert_not_called()


def test_missing_model_fails_without_runtime_download(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSISTANT_WAKE_MODEL_PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="modelo de ativação"):
        make_recognizer()
