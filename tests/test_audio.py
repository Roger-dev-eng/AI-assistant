import io
import wave
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from assistant.audio.recording import record_microphone
from assistant.audio.speech_to_text import SpeechToText
from assistant.audio.text_to_speech import TextToSpeech, play_wav
from assistant.config import Settings


def model_folder(tmp_path):
    for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
        (tmp_path / name).write_text("fixture", encoding="utf-8")
    return str(tmp_path)


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x01\x00" * 4000)
    return buffer.getvalue()


def test_missing_model_fails_before_import_or_download():
    with patch.dict("sys.modules", {"faster_whisper": Mock()}) as modules:
        with pytest.raises(RuntimeError, match="WHISPER_MODEL_PATH"):
            SpeechToText("").prepare(Event())
        modules["faster_whisper"].WhisperModel.assert_not_called()


def test_transcription_uses_only_local_model_and_preserves_language(tmp_path):
    factory = Mock()
    factory.return_value.transcribe.return_value = (
        iter([SimpleNamespace(text=" Abra o Chrome "), SimpleNamespace(text="e pesquise Python")]),
        SimpleNamespace(language="pt"),
    )
    with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
        stt = SpeechToText(model_folder(tmp_path))
        result = stt.transcribe(object(), "auto", Event())
    assert result.text == "Abra o Chrome e pesquise Python"
    assert result.language == "pt"
    assert factory.call_args.kwargs["local_files_only"] is True
    assert factory.call_args.kwargs["compute_type"] == "int8"
    assert factory.return_value.transcribe.call_args.kwargs["language"] is None
    assert factory.return_value.transcribe.call_args.kwargs["vad_filter"] is True


def test_cancel_during_lazy_transcription_discards_partial_text(tmp_path):
    cancelled = Event()

    def segments():
        yield SimpleNamespace(text="Abra")
        cancelled.set()
        yield SimpleNamespace(text="Chrome")

    factory = Mock()
    factory.return_value.transcribe.return_value = (segments(), SimpleNamespace(language="pt"))
    with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
        with pytest.raises(InterruptedError):
            SpeechToText(model_folder(tmp_path)).transcribe(object(), "pt", cancelled)


@pytest.mark.parametrize("segments,language", [([], "pt"), ([SimpleNamespace(text="Hallo")], "de")])
def test_empty_or_unsupported_transcription_is_not_executable(tmp_path, segments, language):
    factory = Mock()
    factory.return_value.transcribe.return_value = (
        iter(segments),
        SimpleNamespace(language=language),
    )
    with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
        with pytest.raises(RuntimeError):
            SpeechToText(model_folder(tmp_path)).transcribe(object(), "auto", Event())


def test_piper_requires_voice_and_metadata(tmp_path):
    with pytest.raises(RuntimeError, match="PIPER_VOICE"):
        TextToSpeech("", "").synthesize("Olá", "pt", Event())
    path = tmp_path / "voice.onnx"
    path.touch()
    with pytest.raises(RuntimeError, match="onnx.json"):
        TextToSpeech(str(path), "").synthesize("Olá", "pt", Event())


def test_piper_synthesizes_in_memory_with_configured_local_voice(tmp_path):
    path = tmp_path / "voice.onnx"
    path.touch()
    (tmp_path / "voice.onnx.json").touch()
    factory = Mock()

    def synthesize(text, wav):
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)

    factory.load.return_value.synthesize_wav.side_effect = synthesize
    with patch.dict("sys.modules", {"piper": SimpleNamespace(PiperVoice=factory)}):
        data = TextToSpeech(str(path), "").synthesize("Olá", "pt", Event())
    assert data.startswith(b"RIFF")
    factory.load.assert_called_once_with(str(path.resolve()), use_cuda=False)
    assert set(tmp_path.iterdir()) == {path, tmp_path / "voice.onnx.json"}


def test_piper_rejects_large_reply_before_loading_model(tmp_path):
    with pytest.raises(ValueError, match="2000"):
        TextToSpeech("voice.onnx", "").synthesize("a" * 2001, "pt", Event())


def test_microphone_stops_and_releases_stream_without_writing_files():
    np = pytest.importorskip("numpy")
    finished, cancelled = Event(), Event()
    stream = MagicMock()

    def create_stream(**kwargs):
        kwargs["callback"](np.ones((1600, 1), dtype="float32") * 0.1, 1600, None, False)
        finished.set()
        return stream

    device = SimpleNamespace(
        InputStream=Mock(side_effect=create_stream), PortAudioError=RuntimeError
    )
    with patch.dict("sys.modules", {"sounddevice": device}):
        samples = record_microphone(cancelled, finished)
    assert samples.shape == (1600,)
    stream.__exit__.assert_called_once()
    assert device.InputStream.call_args.kwargs["samplerate"] == 16000


def test_microphone_cancellation_never_returns_captured_speech():
    np = pytest.importorskip("numpy")
    cancelled = Event()
    stream = MagicMock()

    def create_stream(**kwargs):
        kwargs["callback"](np.ones((1600, 1), dtype="float32"), 1600, None, False)
        cancelled.set()
        return stream

    device = SimpleNamespace(
        InputStream=Mock(side_effect=create_stream), PortAudioError=RuntimeError
    )
    with patch.dict("sys.modules", {"sounddevice": device}):
        with pytest.raises(InterruptedError):
            record_microphone(cancelled, Event())
    stream.__exit__.assert_called_once()


@pytest.mark.parametrize("silent,overflow", [(True, False), (False, True)])
def test_silent_or_incomplete_capture_is_rejected(silent, overflow):
    np = pytest.importorskip("numpy")
    finished = Event()
    stream = MagicMock()

    def create_stream(**kwargs):
        samples = (
            np.zeros((1600, 1), dtype="float32") if silent else np.ones((1600, 1), dtype="float32")
        )
        kwargs["callback"](samples, 1600, None, overflow)
        finished.set()
        return stream

    device = SimpleNamespace(
        InputStream=Mock(side_effect=create_stream), PortAudioError=RuntimeError
    )
    with patch.dict("sys.modules", {"sounddevice": device}):
        with pytest.raises(RuntimeError):
            record_microphone(Event(), finished)
    stream.__exit__.assert_called_once()


def test_audio_playback_checks_cancellation_between_chunks():
    pytest.importorskip("numpy")
    cancelled = Event()
    stream = MagicMock()
    stream.__enter__.return_value.write.side_effect = lambda data: cancelled.set()
    device = SimpleNamespace(OutputStream=Mock(return_value=stream), PortAudioError=RuntimeError)
    with patch.dict("sys.modules", {"sounddevice": device}):
        with pytest.raises(InterruptedError):
            play_wav(wav_bytes(), cancelled)
    assert stream.__enter__.return_value.write.call_count == 1
    stream.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "kwargs", [{"language": "xx"}, {"recording_seconds": 0}, {"recording_seconds": 31}]
)
def test_audio_settings_reject_invalid_values(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)
