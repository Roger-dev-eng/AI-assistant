"""Offline Portuguese keyword gate. No cloud clients, Whisper or audio persistence."""

import io
import json
import os
import queue
import sys
import wave
from functools import lru_cache
from pathlib import Path
from threading import Event

from assistant.audio.recording import check_cancelled
from assistant.audio.text_to_speech import play_wav
from assistant.runtime_log import mark

MODEL_NAME = "vosk-model-small-pt-0.3"
SAMPLE_RATE = 16000


def model_path():
    override = os.environ.get("ASSISTANT_WAKE_MODEL_PATH")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "wake-model"
    return Path(__file__).resolve().parents[3] / "models" / MODEL_NAME


@lru_cache(maxsize=1)
def load_model(path):
    from vosk import Model, SetLogLevel

    SetLogLevel(-1)
    return Model(str(path))  # Explicit path: Vosk must never download a model at runtime.


def make_recognizer():
    path = model_path()
    if not (path / "final.mdl").is_file():
        raise RuntimeError(
            "O modelo de ativação não foi encontrado. Reinstale a versão completa do aplicativo. "
            "No código-fonte, execute python scripts/prepare_wake_model.py."
        )
    try:
        from vosk import KaldiRecognizer

        model = load_model(str(path.resolve()))
        if model.vosk_model_find_word("assistente") < 0:
            raise ValueError("A palavra de ativação não está no modelo.")
        recognizer = KaldiRecognizer(model, SAMPLE_RATE, '["assistente", "[unk]"]')
        recognizer.SetWords(True)
        return recognizer
    except Exception as exc:
        raise RuntimeError("Não foi possível carregar o detector offline de Assistente.") from exc


def keyword_detected(result):
    data = json.loads(result)
    return data.get("text", "").strip() == "assistente" and any(
        word.get("word") == "assistente" and word.get("conf", 0) >= 0.8
        for word in data.get("result", [])
    )


def wait_for_keyword(cancelled, phase, recognizer_factory=make_recognizer, stream_factory=None):
    check_cancelled(cancelled)
    recognizer = recognizer_factory()
    check_cancelled(cancelled)
    if stream_factory is None:
        import sounddevice as sd

        stream_factory = sd.RawInputStream
    frames = queue.Queue(maxsize=32)
    overflow = Event()

    def receive(data, count, timing, status):
        if status:
            overflow.set()
        if cancelled.is_set() or overflow.is_set():
            return
        try:
            frames.put_nowait(bytes(data))
        except queue.Full:
            overflow.set()

    mark("wake.wait.begin")
    try:
        with stream_factory(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=1600, callback=receive):
            phase("Microfone ativo · aguardando Assistente · sem conexão AWS.")
            while True:
                check_cancelled(cancelled)
                if overflow.is_set():
                    raise RuntimeError("A escuta perdeu áudio. Confira o microfone e reative a escuta.")
                try:
                    data = frames.get(timeout=0.05)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(data) and keyword_detected(recognizer.Result()):
                    mark("wake.detected")
                    return  # Stream closes before the tone and command capture.
    finally:
        mark("wake.wait.end")


def activation_tone(cancelled):
    import numpy as np

    samples = np.arange(int(SAMPLE_RATE * 0.12)) / SAMPLE_RATE
    tone = (np.sin(2 * np.pi * 880 * samples) * np.hanning(len(samples)) * 5000).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(tone.tobytes())
    play_wav(buffer.getvalue(), cancelled)
