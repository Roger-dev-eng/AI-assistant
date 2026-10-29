from dataclasses import replace
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from assistant.audio.speech_to_text import NoSpeechRecognized, Transcript
from assistant.audio.wake_word import (
    OVERLAP_FRAMES,
    WINDOW_FRAMES,
    MicrophoneWindows,
    command_after_wake,
    listen_for_command,
)
from assistant.config import Settings


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Assistente, abre o Chrome", "abre o Chrome"),
        ("assistant: open Notepad", "open Notepad"),
        ("  ASSISTENTE! volume 50", "volume 50"),
        ("Assistente.", ""),
        ("Assistant", ""),
        ("assistantship open Chrome", None),
        ("meu assistente abre Chrome", None),
        ("abra o Chrome", None),
        ("", None),
    ],
)
def test_wake_prefix_requires_a_complete_word_at_start(text, expected):
    assert command_after_wake(text) == expected


class FakeMicrophone:
    def __init__(self, windows):
        self.windows = iter(windows)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def read(self, finished=None):
        if finished is not None and finished.is_set():
            return None
        try:
            return next(self.windows)
        except StopIteration as exc:
            raise TimeoutError("Listening timed out") from exc


def run_listener(stt, microphone, cancelled=None, seconds=3, finished=None):
    factory = Mock(return_value=microphone)
    result = listen_for_command(
        stt,
        "auto",
        cancelled or Event(),
        finished or Event(),
        replace(Settings(), recording_seconds=seconds),
        Mock(),
        factory,
    )
    return result


def test_non_wake_speech_is_ignored_and_microphone_closes_before_review():
    np = pytest.importorskip("numpy")
    microphone = FakeMicrophone([np.ones(WINDOW_FRAMES), np.ones(WINDOW_FRAMES)])
    stt = Mock()

    def transcribe(audio, language, cancelled):
        if stt.transcribe.call_count == 1:
            return Transcript("Meu assistente está aqui", "pt")
        if stt.transcribe.call_count == 2:
            return Transcript("Assistant open Chrome", "en")
        assert microphone.closed
        return Transcript("Assistant open Chrome", "en")

    stt.transcribe.side_effect = transcribe
    assert run_listener(stt, microphone) == Transcript("open Chrome", "en")
    assert microphone.closed


def test_overlapping_windows_do_not_duplicate_audio_in_command():
    np = pytest.importorskip("numpy")
    microphone = FakeMicrophone([np.ones(WINDOW_FRAMES) * i for i in [1, 2, 3]])
    stt = Mock()
    stt.transcribe.side_effect = [
        Transcript("Assistente", "pt"),
        Transcript("Assistente abra o Chrome", "pt"),
    ]
    assert run_listener(stt, microphone, seconds=6).text == "abra o Chrome"
    audio = stt.transcribe.call_args.args[0]
    assert len(audio) == 6 * 16000
    assert np.all(audio[:WINDOW_FRAMES] == 1)
    assert np.all(audio[WINDOW_FRAMES : WINDOW_FRAMES * 2 - OVERLAP_FRAMES] == 2)


def test_silence_and_no_speech_are_ignored_without_executing_anything():
    np = pytest.importorskip("numpy")
    microphone = FakeMicrophone([np.zeros(WINDOW_FRAMES), np.ones(WINDOW_FRAMES)])
    stt = Mock()
    stt.transcribe.side_effect = NoSpeechRecognized("No speech")
    with pytest.raises(TimeoutError):
        run_listener(stt, microphone)
    stt.transcribe.assert_called_once()
    assert microphone.closed


def test_cancellation_during_inference_discards_activation():
    np = pytest.importorskip("numpy")
    microphone = FakeMicrophone([np.ones(WINDOW_FRAMES)])
    stt, cancelled = Mock(), Event()

    def transcribe(*args):
        cancelled.set()
        return Transcript("Assistente abra Chrome", "pt")

    stt.transcribe.side_effect = transcribe
    with pytest.raises(InterruptedError):
        run_listener(stt, microphone, cancelled)
    assert microphone.closed


def test_activation_without_a_confirmed_command_is_rejected():
    np = pytest.importorskip("numpy")
    microphone = FakeMicrophone([np.ones(WINDOW_FRAMES)])
    stt = Mock()
    stt.transcribe.side_effect = [Transcript("Assistente", "pt"), Transcript("Assistente", "pt")]
    with pytest.raises(RuntimeError, match="comando completo"):
        run_listener(stt, microphone)
    assert microphone.closed


def test_manual_finish_preserves_audio_still_buffered():
    np = pytest.importorskip("numpy")
    microphone = FakeMicrophone([np.ones(WINDOW_FRAMES)])
    microphone.finish_pending = Mock(return_value=np.ones(1000))
    stt = Mock()
    stt.transcribe.side_effect = [
        Transcript("Assistente", "pt"),
        Transcript("Assistente abra Chrome", "pt"),
    ]
    finished = Event()
    finished.set()
    result = run_listener(stt, microphone, seconds=10, finished=finished)
    assert result.text == "abra Chrome"
    assert len(stt.transcribe.call_args.args[0]) == WINDOW_FRAMES + 1000


def test_microphone_queue_is_bounded_and_overrun_stops_capture():
    np = pytest.importorskip("numpy")

    class CallbackStop(Exception):
        pass

    stream = MagicMock()
    device = SimpleNamespace(InputStream=Mock(return_value=stream), CallbackStop=CallbackStop)
    with patch.dict("sys.modules", {"sounddevice": device}):
        microphone = MicrophoneWindows(Event(), 120, Mock())
        with microphone:
            callback = device.InputStream.call_args.kwargs["callback"]
            callback(np.ones((WINDOW_FRAMES, 1)), WINDOW_FRAMES, None, False)
            callback(np.ones((WINDOW_FRAMES, 1)), WINDOW_FRAMES, None, False)
            with pytest.raises(CallbackStop):
                callback(np.ones((WINDOW_FRAMES, 1)), WINDOW_FRAMES, None, False)
            assert microphone.windows.qsize() == 2
            with pytest.raises(RuntimeError, match="não acompanhou"):
                microphone.read()
    stream.stop.assert_called_once()
    stream.close.assert_called_once()


@pytest.mark.parametrize("seconds", [0, 14, 601])
def test_listener_timeout_is_bounded(seconds):
    with pytest.raises(ValueError):
        Settings(wake_listen_seconds=seconds)
