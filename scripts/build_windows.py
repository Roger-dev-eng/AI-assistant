"""Build on Windows/Python 3.12; only the fixed keyword model is bundled."""

import os
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from build_updater import build_updater
from install_manifest import create_install_manifest
from prepare_wake_model import prepare_model


def main():
    if os.name != "nt" or sys.version_info[:2] != (3, 12):
        raise SystemExit("Build with Python 3.12 on Windows.")
    root = Path(__file__).resolve().parents[1]
    updater = build_updater()
    wake_model = prepare_model()
    app_version = version("assistant-desktop")
    runtime_hook = root / "build" / "version_hook.py"
    runtime_hook.parent.mkdir(parents=True, exist_ok=True)
    runtime_hook.write_text(f"import sys\nsys._assistant_build_version = {app_version!r}\n", "utf-8")
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
        "--add-binary",
        f"{updater}:assistant",
        "--add-data",
        f"{wake_model}:wake-model",
        "--hidden-import",
        "PySide6.QtWidgets",
        "--runtime-hook",
        str(runtime_hook),
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
        "vosk",
        "docx",
        "lxml",
        "pywinauto",
        "pycaw",
        "comtypes",
        "aws_sdk_bedrock_runtime",
        "aws_sdk_signers",
        "awscrt",
        "smithy_core",
        "smithy_aws_core",
        "smithy_aws_event_stream",
        "smithy_http",
        "smithy_json",
    ):
        args += ["--collect-all", package]
    for distribution in (
        "assistant-desktop",
        "python-docx",
        "lxml",
        "piper-tts",
        "faster-whisper",
        "onnxruntime",
        "ctranslate2",
        "sounddevice",
        "vosk",
        "PySide6",
        "playwright",
        "aws-sdk-bedrock-runtime",
        "smithy-aws-core",
        "smithy-core",
        "smithy-http",
        "awscrt",
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
    payload = root / "dist" / "AssistantDesktop"
    for source, relative in (
        ("README.md", "README.md"), ("LICENSE", "LICENSE"),
        ("packaging/THIRD_PARTY.md", "THIRD_PARTY.md"),
        ("docs/VOICE_AWS.md", "docs/VOICE_AWS.md"),
        ("docs/aws-sonic-policy.example.json", "docs/aws-sonic-policy.example.json"),
    ):
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
    create_install_manifest(payload, app_version, root / "build" / "install-files.iss")


if __name__ == "__main__":
    main()
