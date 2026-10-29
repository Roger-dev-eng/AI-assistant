import time


class SilenceEndpoint:
    """Energy-based endpoint with minimum speech and trailing silence; no network or model."""

    def __init__(self, seconds=1.75, sample_rate=16000):
        self.limit = int(seconds * sample_rate)
        self.speech_frames = 0
        self.silent_frames = 0
        self.started = False

    def feed(self, audio):
        import numpy as np

        # 20 ms frames prevent mixed speech/silence chunks from masking a pause.
        for offset in range(0, len(audio), 320):
            frame = audio[offset : offset + 320]
            rms = float(np.sqrt(np.mean(frame * frame)))
            if rms >= 0.008:
                self.speech_frames += len(frame)
                self.silent_frames = 0
                self.started = self.speech_frames >= 1600
            elif self.started:
                self.silent_frames += len(frame)
                if self.silent_frames >= self.limit:
                    return True
        return False


def check_cancelled(cancelled):
    if cancelled.is_set():
        raise InterruptedError("Áudio interrompido / Audio interrupted.")


def record_microphone(
    cancelled, finished, seconds=10, on_recording=lambda: None, silence_seconds=None
):
    if not 1 <= seconds <= 30:
        raise ValueError("Recording duration must be between 1 and 30 seconds.")
    check_cancelled(cancelled)
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            'Instale o suporte de voz com Python 3.12: pip install -e ".[voice]"'
        ) from exc
    chunks, errors = [], []
    captured = 0
    maximum = seconds * 16000
    endpoint = SilenceEndpoint(silence_seconds) if silence_seconds is not None else None
    ended = False

    def callback(data, frames, timing, status):
        nonlocal captured, ended
        if ended or cancelled.is_set():
            return
        if status:
            errors.append(str(status))
        count = min(len(data), maximum - captured)
        if count > 0:
            chunks.append(data[:count, 0].copy())
            captured += count
            if endpoint is not None:
                ended = endpoint.feed(data[:count, 0])

    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32", callback=callback):
            on_recording()
            deadline = time.monotonic() + seconds
            while (
                time.monotonic() < deadline
                and captured < maximum
                and not finished.is_set()
                and not errors
                and not ended
            ):
                if cancelled.wait(0.02):
                    break
    except sd.PortAudioError as exc:
        raise RuntimeError(
            "Não foi possível gravar. Confira o microfone e a permissão do Windows."
        ) from exc
    check_cancelled(cancelled)
    if errors:
        raise RuntimeError("A captura perdeu áudio. Grave novamente antes de executar o comando.")
    if endpoint is not None and not ended and not finished.is_set():
        raise RuntimeError(
            "A fala atingiu o limite sem uma pausa. Divida o comando em trechos menores."
        )
    if not chunks:
        raise RuntimeError("Nenhum áudio capturado.")
    audio = np.concatenate(chunks)
    if len(audio) < 1600 or float(np.max(np.abs(audio))) < 0.001:
        raise RuntimeError("Áudio muito curto ou silencioso. Tente novamente.")
    return audio
