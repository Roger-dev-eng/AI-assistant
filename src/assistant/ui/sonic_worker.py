import io
import time
import wave
from threading import Event

from PySide6.QtCore import Signal

from assistant.ai.sonic_provider import SonicProvider
from assistant.audio.recording import check_cancelled, record_microphone
from assistant.audio.speech_to_text import SpeechToText
from assistant.audio.text_to_speech import play_wav
from assistant.audio.wake_word import listen_for_command
from assistant.cloud.usage_tracker import UsageTracker
from assistant.core.action_executor import ActionExecutor
from assistant.storage.memory import ConversationMemory
from assistant.tools.windows import WindowsTools, automation_context
from assistant.ui.worker import TaskWorker


class SonicWorker(TaskWorker):
    phase = Signal(str)
    user_text = Signal(str)

    def __init__(
        self,
        settings,
        database_path,
        dry_run=False,
        language="pt",
        wake=False,
        parent=None,
        provider_factory=SonicProvider,
        backend_factory=WindowsTools,
    ):
        super().__init__(
            "", settings, database_path, dry_run, parent, backend_factory=backend_factory
        )
        self.language, self.wake = language, wake
        self.sonic_factory = provider_factory
        self.recording_finished = Event()

    def run(self):
        tracker, memory = None, None
        try:
            if not self.settings.cloud_enabled:
                raise RuntimeError("Marque Permitir Bedrock (AWS) antes de usar Nova 2 Sonic.")
            if self.wake:
                self.phase.emit("Preparando ativação local… microfone desligado.")
                audio = listen_for_command(
                    SpeechToText(self.settings.whisper_model_path),
                    self.language,
                    self.cancelled,
                    self.recording_finished,
                    self.settings,
                    self.phase.emit,
                    return_audio=True,
                )
            else:
                audio = record_microphone(
                    self.cancelled,
                    self.recording_finished,
                    self.settings.recording_seconds,
                    on_recording=lambda: self.phase.emit(
                        "Microfone ativo · fale; a captura termina após a pausa."
                    ),
                    silence_seconds=self.settings.silence_seconds,
                )
            check_cancelled(self.cancelled)
            self.phase.emit("Microfone desligado · enviando comando ao Nova 2 Sonic (AWS)…")
            import numpy as np

            pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
            tracker = UsageTracker(self.database_path)
            if self.settings.memory_enabled:
                memory = ConversationMemory(
                    self.database_path,
                    self.settings.memory_retention_days,
                    self.settings.memory_max_turns,
                )
            with automation_context():
                executor = ActionExecutor(
                    self.backend_factory(), self.confirm, self.dry_run, self.cancelled
                )
                executor.begin_task()
                self.confirmation_deadline = time.monotonic() + self.settings.sonic_timeout_seconds
                provider = self.sonic_factory(
                    self.settings,
                    tracker,
                    executor,
                    self.cancelled,
                    on_transcript=self.user_text.emit,
                    history=memory.messages() if memory else (),
                )
                response = provider.run(pcm)
            check_cancelled(self.cancelled)
            if response.text:
                self.result.emit(response.text)
            if memory is not None:
                memory.remember(response.transcript, response.text)
            if response.audio:
                self.phase.emit("Reproduzindo Nova 2 Sonic… microfone desligado.")
                output = io.BytesIO()
                with wave.open(output, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(response.audio)
                play_wav(output.getvalue(), self.cancelled)
        except InterruptedError:
            self.result.emit("Interação de voz interrompida.")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if memory is not None:
                memory.close()
            if tracker is not None:
                try:
                    self.usage_updated.emit(*tracker.summary())
                finally:
                    tracker.close()
