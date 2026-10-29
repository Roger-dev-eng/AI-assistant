"""Build on Windows/Python 3.12; models and user credentials are never included."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt" or sys.version_info[:2] != (3, 12):
        raise SystemExit("Build with Python 3.12 on Windows.")
    root = Path(__file__).resolve().parents[1]
    cache = Path(os.environ["LOCALAPPDATA"]) / "ms-playwright"
    browsers = [
        path
        for path in cache.iterdir()
        if path.is_dir()
        and path.name.startswith(("chromium_headless_shell-", "ffmpeg-", "winldd-"))
    ]
    if not any(path.name.startswith("chromium_headless_shell-") for path in browsers):
        raise SystemExit("Install Chromium first: python -m playwright install chromium")
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "AssistantDesktop",
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build"),
        "--specpath",
        str(root / "build"),
        "--collect-data",
        "assistant",
        "--hidden-import",
        "PySide6.QtWidgets",
    ]
    for package in (
        "playwright",
        "piper",
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
        "tokenizers",
        "sounddevice",
        "_sounddevice_data",
        "pywinauto",
        "pycaw",
        "comtypes",
    ):
        args += ["--collect-all", package]
    for distribution in (
        "assistant-desktop",
        "piper-tts",
        "faster-whisper",
        "onnxruntime",
        "ctranslate2",
        "sounddevice",
        "PySide6",
        "playwright",
    ):
        args += ["--copy-metadata", distribution]
    for path in browsers:
        args += ["--add-data", f"{path}:browsers/{path.name}"]
    args += [str(root / "scripts" / "desktop_entry.py")]
    subprocess.run(args, cwd=root, check=True)
    # Qt on Windows uses the operating system ICU. An unrelated ICU found on PATH
    # (e.g. from Poppler) has incompatible symbol names and must not shadow it.
    for name in ("icuuc.dll", "icuin.dll", "icudt.dll"):
        (root / "dist" / "AssistantDesktop" / "_internal" / name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
