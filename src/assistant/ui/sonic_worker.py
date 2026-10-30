import io
import time
import wave
from threading import Event

from PySide6.QtCore import Signal

from assistant.ai.sonic_provider import SonicProvider
from assistant.audio.recording import check_cancelled, record_microphone
from assistant.audio.text_to_speech import play_wav
from assistant.audio.wake_trigger import activation_tone, wait_for_keyword
from assistant.cloud.usage_tracker import UsageTracker
from assistant.core.action_executor import ActionExecutor
from assistant.runtime_log import mark
from assistant.storage.activity import ActivityStore
from assistant.storage.memory import ConversationMemory
from assistant.tools.windows import WindowsTools, automation_context
from assistant.ui.worker import TaskWorker


class SonicWorker(TaskWorker):
    phase = Signal(str)
    user_text = Signal(str)
    action_done = Signal(str)

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
        self.rearm_wake = False

    def run(self):
        tracker, memory, provider = None, None, None
        try:
            if not self.settings.cloud_enabled:
                raise RuntimeError("Marque Permitir Bedrock (AWS) antes de usar Nova 2 Sonic.")
            if self.wake:
                self.phase.emit("Preparando ativação local… microfone desligado.")
                wait_for_keyword(self.cancelled, self.phase.emit)
                self.rearm_wake = True
                self.phase.emit("Ativação detectada · aguarde o sinal · microfone desligado.")
                activation_tone(self.cancelled)
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
            mark("sonic.command.captured")
            self.phase.emit("Preparando conexão com o Nova 2 Sonic · microfone desligado.")
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
                    self.backend_factory(), self.confirm, self.dry_run, self.cancelled,
                    activity=(ActivityStore(self.database_path, self.settings.command_history_retention_days)
                              if self.settings.command_history_enabled and not self.dry_run else None),
                    settings=self.settings, database_path=self.database_path,
                )
                executor.begin_task()
                self.confirmation_deadline = time.monotonic() + self.settings.sonic_timeout_seconds
                heard = []

                def transcript_received(text):
                    heard.append(text)
                    executor.set_command("\n".join(heard))
                    self.user_text.emit(text)

                provider = self.sonic_factory(
                    self.settings,
                    tracker,
                    executor,
                    self.cancelled,
                    on_transcript=transcript_received,
                    history=memory.messages() if memory else (),
                    on_phase=self.phase.emit,
                    on_action=self.action_done.emit,
                )
                mark("sonic.turn.begin")
                response = provider.run(pcm)
                mark("sonic.turn.end")
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
                mark("sonic.playback.end")
        except InterruptedError:
            report = provider.action_report() if isinstance(provider, SonicProvider) else ""
            self.result.emit("Interação de voz interrompida. " + report)
        except Exception as exc:
            if isinstance(provider, SonicProvider):
                message = provider.failure_message(exc)
            elif isinstance(exc, TimeoutError):
                message = "O tempo limite da interação de voz foi atingido."
            else:
                message = str(exc).strip() or f"Falha de voz ({type(exc).__name__})."
            self.failed.emit(message)
        finally:
            if memory is not None:
                memory.close()
            if tracker is not None:
                try:
                    self.usage_updated.emit(*tracker.summary())
                finally:
                    tracker.close()
