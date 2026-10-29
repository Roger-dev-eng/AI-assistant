import time


def check_cancelled(cancelled):
    if cancelled.is_set():
        raise InterruptedError("Áudio interrompido / Audio interrupted.")


def record_microphone(cancelled, finished, seconds=10, on_recording=lambda: None):
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

    def callback(data, frames, timing, status):
        nonlocal captured
        if status:
            errors.append(str(status))
        count = min(len(data), maximum - captured)
        if count > 0:
            chunks.append(data[:count, 0].copy())
            captured += count

    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32", callback=callback):
            on_recording()
            deadline = time.monotonic() + seconds
            while (
                time.monotonic() < deadline
                and captured < maximum
                and not finished.is_set()
                and not errors
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
    if not chunks:
        raise RuntimeError("Nenhum áudio capturado.")
    audio = np.concatenate(chunks)
    if len(audio) < 1600 or float(np.max(np.abs(audio))) < 0.001:
        raise RuntimeError("Áudio muito curto ou silencioso. Tente novamente.")
    return audio
