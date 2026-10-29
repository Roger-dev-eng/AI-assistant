from dataclasses import dataclass
from pathlib import Path

from assistant.audio.recording import check_cancelled


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str


class SpeechToText:
    def __init__(self, model_path):
        self.path = Path(model_path).expanduser() if model_path else None
        self.model = None

    def prepare(self, cancelled):
        check_cancelled(cancelled)
        required = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
        if self.path is None or not all((self.path / name).is_file() for name in required):
            raise RuntimeError(
                "Configure WHISPER_MODEL_PATH com uma pasta local completa do faster-whisper."
            )
        if self.model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    'Instale voz com Python 3.12: pip install -e ".[voice]"'
                ) from exc
            self.model = WhisperModel(
                str(self.path.resolve()), device="cpu", compute_type="int8", local_files_only=True
            )
        check_cancelled(cancelled)

    def transcribe(self, audio, language, cancelled):
        if language not in {"auto", "pt", "en"}:
            raise ValueError("Unsupported transcription language.")
        self.prepare(cancelled)
        segments, info = self.model.transcribe(
            audio,
            language=None if language == "auto" else language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        words = []
        for segment in segments:
            check_cancelled(cancelled)
            words.append(segment.text.strip())
            if len(" ".join(words)) > 12000:
                raise RuntimeError("Transcrição excedeu o limite de um comando.")
        check_cancelled(cancelled)
        text = " ".join(words).strip()
        if not text:
            raise RuntimeError("Nenhuma fala reconhecida. Grave novamente.")
        if info.language not in {"pt", "en"}:
            raise RuntimeError(
                "Idioma não reconhecido como português ou inglês; selecione o idioma."
            )
        return Transcript(text, info.language)
