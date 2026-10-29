import io
import wave
from pathlib import Path

from assistant.audio.recording import check_cancelled


class TextToSpeech:
    def __init__(self, voice_pt, voice_en):
        self.paths = {"pt": voice_pt, "en": voice_en}
        self.voices = {}

    def synthesize(self, text, language, cancelled):
        check_cancelled(cancelled)
        if language not in self.paths or not self.paths[language]:
            raise RuntimeError("Configure PIPER_VOICE_PT/PIPER_VOICE_EN para o idioma escolhido.")
        if not text.strip() or len(text) > 2000:
            raise ValueError("A leitura aceita de 1 a 2000 caracteres; selecione um trecho menor.")
        path = Path(self.paths[language]).expanduser()
        if not path.is_file() or not Path(str(path) + ".json").is_file():
            raise RuntimeError("A voz Piper requer um arquivo .onnx e o .onnx.json correspondente.")
        if language not in self.voices:
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise RuntimeError(
                    'Instale voz com Python 3.12: pip install -e ".[voice]"'
                ) from exc
            self.voices[language] = PiperVoice.load(str(path.resolve()), use_cuda=False)
        check_cancelled(cancelled)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            self.voices[language].synthesize_wav(text, wav)
        check_cancelled(cancelled)
        return buffer.getvalue()


def play_wav(data, cancelled):
    check_cancelled(cancelled)
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError('Instale voz com Python 3.12: pip install -e ".[voice]"') from exc
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError("Expected 16-bit mono Piper audio.")
        rate = wav.getframerate()
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="int16")
    try:
        with sd.OutputStream(samplerate=rate, channels=1, dtype="int16") as stream:
            for offset in range(0, len(pcm), 1024):
                check_cancelled(cancelled)
                stream.write(pcm[offset : offset + 1024].reshape(-1, 1))
    except sd.PortAudioError as exc:
        raise RuntimeError("Não foi possível reproduzir áudio. Confira a saída de som.") from exc
    check_cancelled(cancelled)
