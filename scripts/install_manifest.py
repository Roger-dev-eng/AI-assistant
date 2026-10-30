"""Describe application-owned files and generate content-aware Inno Setup entries."""

import hashlib
import json
from pathlib import Path


def create_install_manifest(directory, version, include):
    directory = Path(directory).resolve()
    files = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path == directory / "application-manifest.json":
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError("Application payload must not contain external links.")
        if (path.name.lower() in {"settings.json", "credentials", "usage.sqlite3"}
                or path.name.lower().startswith(".env")
                or path.suffix.lower().startswith((".db", ".sqlite"))):
            raise ValueError("User data must not be included in the application payload.")
        relative = path.relative_to(directory).as_posix()
        with path.open("rb") as source:
            files[relative] = hashlib.file_digest(source, "sha256").hexdigest()
    if "AssistantDesktop.exe" not in files:
        raise ValueError("Application executable missing from payload.")
    manifest = directory / "application-manifest.json"
    manifest.write_text(json.dumps({"version": version, "files": files}, indent=2), "utf-8")
    files = {**files, "application-manifest.json": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    entries = [f'#define AppExeSHA256 "{files["AssistantDesktop.exe"]}"']
    for relative, digest in files.items():
        path = directory / relative
        parent = Path(relative).parent.as_posix()
        destination = "{app}" + ("\\" + parent.replace("/", "\\") if parent != "." else "")
        absolute = str(path).replace('"', '""').replace("{", "{{")
        filename = ("{app}\\" + relative.replace("/", "\\")).replace("'", "''")
        entries.append(
            f'Source: "{absolute}"; DestDir: "{destination}"; Flags: ignoreversion; '
            f"Check: NeedsUpdate(ExpandConstant('{filename}'), '{digest}')"
        )
    Path(include).write_text("\n".join(entries) + "\n", "utf-8")
    return manifest
