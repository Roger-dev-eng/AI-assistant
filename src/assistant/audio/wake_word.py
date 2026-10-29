import queue
import re
import time

from assistant.audio.recording import check_cancelled
from assistant.audio.speech_to_text import NoSpeechRecognized, Transcript

SAMPLE_RATE = 16000
WINDOW_FRAMES = SAMPLE_RATE * 3
OVERLAP_FRAMES = SAMPLE_RATE * 3 // 4
WAKE_PREFIX = re.compile(r"^\s*(?:assistente|assistant)(?=$|[\s,.:;!?])[,.:;!?\s]*", re.IGNORECASE)


def command_after_wake(text):
    match = WAKE_PREFIX.match(text)
    return text[match.end() :].strip() if match else None


class MicrophoneWindows:
    """Bounded overlapping audio windows. Fail on overflow rather than losing command audio."""

    def __init__(self, cancelled, seconds, on_active):
        self.cancelled = cancelled
        self.seconds = seconds
        self.on_active = on_active
        self.windows = queue.Queue(maxsize=2)
        self.error = None
        self.stream = None

    def __enter__(self):
        check_cancelled(self.cancelled)
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError('Instale voz com Python 3.12: pip install -e ".[voice]"') from exc
        self.pending = np.empty(0, dtype="float32")
        self.deadline = time.monotonic() + self.seconds

        def callback(data, frames, timing, status):
            if status:
                self.error = "A escuta perdeu áudio. Interrompa e tente novamente."
            if time.monotonic() >= self.deadline:
                self.error = "Tempo de escuta encerrado. Ative a escuta novamente para continuar."
            if self.cancelled.is_set() or self.error:
                raise sd.CallbackStop
            self.pending = np.concatenate((self.pending, data[:, 0]))
            while len(self.pending) >= WINDOW_FRAMES:
                try:
                    self.windows.put_nowait(self.pending[:WINDOW_FRAMES].copy())
                except queue.Full:
                    self.error = "A transcrição não acompanhou o microfone. Use Gravar comando ou um modelo menor."
                    raise sd.CallbackStop
                self.pending = self.pending[WINDOW_FRAMES - OVERLAP_FRAMES :]

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=1600,
                callback=callback,
            )
            self.stream.start()
        except Exception as exc:
            if self.stream is not None:
                self.stream.close()
            raise RuntimeError(
                "Não foi possível iniciar a escuta. Confira o microfone e a permissão do Windows."
            ) from exc
        try:
            self.on_active()
        except Exception:
            self.stop_stream()
            raise
        return self

    def read(self, finished=None):
        while True:
            check_cancelled(self.cancelled)
            if self.error:
                raise RuntimeError(self.error)
            if time.monotonic() >= self.deadline:
                raise TimeoutError(
                    "Tempo de escuta encerrado. Ative a escuta novamente para continuar."
                )
            if finished is not None and finished.is_set():
                return None
            try:
                return self.windows.get(timeout=0.05)
            except queue.Empty:
                pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_stream()
        self.pending = None
        while not self.windows.empty():
            self.windows.get_nowait()

    def stop_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None

    def finish_pending(self):
        import numpy as np

        self.stop_stream()
        check_cancelled(self.cancelled)
        if self.error:
            raise RuntimeError(self.error)
        tails = []
        while not self.windows.empty():
            tails.append(self.windows.get_nowait()[OVERLAP_FRAMES:])
        tails.append(self.pending[OVERLAP_FRAMES:].copy())
        return np.concatenate(tails)


def listen_for_command(
    stt, language, cancelled, finished, settings, phase, stream_factory=MicrophoneWindows
):
    stt.prepare(cancelled)
    import numpy as np

    with stream_factory(
        cancelled,
        settings.wake_listen_seconds,
        lambda: phase("Microfone ativo · aguardando Assistente ou Assistant…"),
    ) as microphone:
        while True:
            check_cancelled(cancelled)
            window = microphone.read()
            # Skip silent windows without running inference.
            if float(np.max(np.abs(window))) < 0.001:
                continue
            try:
                candidate = stt.transcribe(window, language, cancelled)
            except NoSpeechRecognized:
                continue
            check_cancelled(cancelled)
            if command_after_wake(candidate.text) is None:
                continue
            phase("Microfone ativo · ativação detectada; diga ou conclua seu comando.")
            chunks, frames = [window], len(window)
            target = max(WINDOW_FRAMES, settings.recording_seconds * SAMPLE_RATE)
            while frames < target:
                tail = microphone.read(finished)
                if tail is None:
                    tail = microphone.finish_pending()[: target - frames]
                    chunks.append(tail)
                    break
                tail = tail[OVERLAP_FRAMES:]
                take = min(len(tail), target - frames)
                chunks.append(tail[:take])
                frames += take
            audio = np.concatenate(chunks)
            break
    # Close the microphone before the final transcription or any UI review.
    if getattr(microphone, "error", None):
        raise RuntimeError(microphone.error)
    phase("Transcrevendo comando localmente… microfone desligado.")
    check_cancelled(cancelled)
    result = stt.transcribe(audio, language, cancelled)
    text = command_after_wake(result.text)
    if not text:
        raise RuntimeError(
            "A ativação não foi confirmada com um comando completo. Tente gravar novamente."
        )
    check_cancelled(cancelled)
    return Transcript(text, result.language)
