"""Fetch the pinned Apache-2.0 Portuguese keyword model during development/build only."""

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

MODEL_NAME = "vosk-model-small-pt-0.3"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_SHA256 = "6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7"


def prepare_model():
    root = Path(__file__).resolve().parents[1]
    models = root / "models"
    model = models / MODEL_NAME
    marker = model / ".archive-sha256"
    if marker.is_file() and marker.read_text("ascii").strip() == MODEL_SHA256:
        return model
    models.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wake-download-", dir=models) as temporary:
        archive = Path(temporary) / "model.zip"
        with urlopen(MODEL_URL, timeout=60) as response, archive.open("wb") as output:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise RuntimeError("Keyword model archive exceeded its size limit.")
                output.write(chunk)
        with archive.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != MODEL_SHA256:
                raise RuntimeError("Keyword model SHA256 mismatch; build cancelled.")
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                target = (models / member.filename).resolve()
                if not target.is_relative_to(model.resolve()):
                    raise RuntimeError("Invalid keyword model archive path.")
            source.extractall(models)
    shutil.copyfile(root / "packaging" / "VOSK-LICENSE.txt", model / "LICENSE")
    marker.write_text(MODEL_SHA256, encoding="ascii")
    return model


if __name__ == "__main__":
    print(prepare_model())
