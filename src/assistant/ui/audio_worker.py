from threading import Event

from PySide6.QtCore import QThread, Signal

from assistant.audio.recording import check_cancelled, record_microphone
from assistant.audio.speech_to_text import SpeechToText
from assistant.audio.text_to_speech import TextToSpeech, play_wav


class AudioWorker(QThread):
    transcript_ready = Signal(str, str)
    failed = Signal(str)
    phase = Signal(str)

    def __init__(self, settings, mode="record", text="", language="pt", parent=None):
        super().__init__(parent)
        self.settings = settings
        self.mode = mode
        self.text = text
        self.language = language
        self.cancelled = Event()
        self.recording_finished = Event()

    def run(self):
        try:
            if self.mode == "record":
                self.phase.emit("Preparando transcrição local… microfone desligado.")
                stt = SpeechToText(self.settings.whisper_model_path)
                stt.prepare(self.cancelled)
                audio = record_microphone(
                    self.cancelled,
                    self.recording_finished,
                    self.settings.recording_seconds,
                    on_recording=lambda: self.phase.emit(
                        "Microfone ativo · clique Concluir gravação ou Interromper."
                    ),
                )
                self.phase.emit("Transcrevendo localmente… microfone desligado.")
                result = stt.transcribe(audio, self.language, self.cancelled)
                check_cancelled(self.cancelled)
                self.transcript_ready.emit(result.text, result.language)
            elif self.mode == "speak":
                self.phase.emit("Preparando resposta falada… microfone desligado.")
                tts = TextToSpeech(self.settings.piper_voice_pt, self.settings.piper_voice_en)
                data = tts.synthesize(self.text, self.language, self.cancelled)
                self.phase.emit("Reproduzindo resposta… microfone desligado.")
                play_wav(data, self.cancelled)
            else:
                raise ValueError("Unknown audio operation.")
        except InterruptedError:
            self.phase.emit("Áudio interrompido · microfone desligado.")
        except Exception as exc:
            self.failed.emit(str(exc))
