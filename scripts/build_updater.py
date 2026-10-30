"""Compile the small updater using the .NET Framework included with Windows."""

import os
import subprocess
from pathlib import Path


def build_updater(output=None):
    root = Path(__file__).resolve().parents[1]
    output = Path(output) if output else root / "build/native/AssistantUpdater.exe"
    framework = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319"
    compiler = framework / "csc.exe"
    if not compiler.is_file():
        raise RuntimeError("O compilador .NET Framework do Windows não foi encontrado.")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
        f"/reference:{framework / 'System.Web.Extensions.dll'}", f"/out:{output}",
        str(root / "packaging/AssistantUpdater.cs"),
    ], check=True)
    return output


if __name__ == "__main__":
    print(build_updater())
