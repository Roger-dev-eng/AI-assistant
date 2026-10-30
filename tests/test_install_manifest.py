import hashlib
import json

import pytest

from scripts.install_manifest import create_install_manifest


def test_payload_manifest_hashes_and_conditional_installer_entries(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "AssistantDesktop.exe").write_bytes(b"application")
    library = payload / "_internal" / "runtime.dll"
    library.parent.mkdir()
    library.write_bytes(b"unchanged library")
    include = tmp_path / "files.iss"
    manifest = json.loads(create_install_manifest(payload, "0.3.10", include).read_text("utf-8"))
    assert manifest["version"] == "0.3.10"
    assert manifest["files"]["_internal/runtime.dll"] == hashlib.sha256(library.read_bytes()).hexdigest()
    text = include.read_text("utf-8")
    assert "NeedsUpdate(ExpandConstant('{app}\\_internal\\runtime.dll')" in text
    assert "application-manifest.json" in text
    assert "recursesubdirs" not in text


@pytest.mark.parametrize("name", [
    "usage.sqlite3", "history.db", "history.sqlite3-wal", "settings.json", ".env",
    ".env.local", "credentials",
])
def test_payload_cannot_package_user_data(tmp_path, name):
    (tmp_path / "AssistantDesktop.exe").write_bytes(b"application")
    (tmp_path / name).write_bytes(b"sensitive")
    with pytest.raises(ValueError, match="User data"):
        create_install_manifest(tmp_path, "0.3.10", tmp_path.parent / "files.iss")
