import hashlib
import io
import json
import os
from dataclasses import replace
from threading import Event
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest

from assistant.updates import (
    API_URL,
    RELEASES_URL,
    check_update,
    download_update,
    ensure_no_other_instances,
    safe_url,
    start_install,
)


def publication(payload=b"installer"):
    return {
        "tag_name": "v0.3.0", "draft": False, "prerelease": False,
        "assets": [{
            "name": "AssistantDesktop-0.3.0-Setup.exe",
            "browser_download_url": f"{RELEASES_URL}/download/v0.3.0/AssistantDesktop-0.3.0-Setup.exe",
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }],
    }


def available(data):
    def opener(url):
        assert url == API_URL
        return io.BytesIO(json.dumps(data).encode())
    return check_update("0.2.1", opener)


def test_only_newer_stable_releases_are_offered():
    data = publication()
    release = available(data)
    assert release.version == "0.3.0"
    assert check_update("0.3.0", lambda _: io.BytesIO(json.dumps(data).encode())) is None
    data["prerelease"] = True
    assert available(data) is None


@pytest.mark.parametrize("field,value", [
    ("browser_download_url", "https://evil.example/setup.exe"),
    ("browser_download_url", "http://github.com/setup.exe"),
    ("digest", None), ("digest", "sha256:1234"), ("size", -1), ("size", True),
])
def test_invalid_release_cannot_become_an_installer(field, value):
    data = publication()
    data["assets"][0][field] = value
    with pytest.raises((ValueError, TypeError)):
        available(data)


@pytest.mark.parametrize("url", [
    "http://github.com/a", "https://evil.example/a", "https://github.com.evil.example/a",
    "https://user:secret@github.com/a", "https://github.com:8080/a",
])
def test_redirects_cannot_leave_trusted_https_hosts(url):
    with pytest.raises(ValueError):
        safe_url(url)


def test_verified_download_is_promoted_only_after_checksum_matches(tmp_path):
    payload = b"installer"
    release = available(publication(payload))
    path = download_update(release, tmp_path, Event(), opener=lambda _: io.BytesIO(payload))
    assert path.read_bytes() == payload
    assert not list(tmp_path.glob("*.part"))


def test_corruption_preserves_previous_verified_file(tmp_path):
    release = available(publication())
    target = tmp_path / release.name
    target.write_bytes(b"previous")
    with pytest.raises(ValueError, match="SHA-256"):
        download_update(release, tmp_path, Event(), opener=lambda _: io.BytesIO(b"corrupted"))
    assert target.read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.part"))


def test_cancelled_download_never_exposes_an_executable(tmp_path):
    release = available(publication())
    cancelled = Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        download_update(release, tmp_path, cancelled, opener=lambda _: io.BytesIO(b"installer"))
    assert not list(tmp_path.iterdir())


def test_forged_selection_is_rejected_before_network(tmp_path):
    release = replace(available(publication()), name="../other.exe")
    with pytest.raises(ValueError):
        download_update(release, tmp_path, Event(), opener=lambda _: pytest.fail("network"))


def test_no_releases_is_handled_without_error():
    def opener(url):
        raise HTTPError(url, 404, "Not Found", {}, None)
    assert check_update("0.3.0", opener) is None


def test_second_copy_blocks_update_before_installer_launch(tmp_path):
    target = tmp_path / "AssistantDesktop.exe"
    same_copy = Mock(info={"pid": os.getpid() + 1, "name": target.name, "exe": str(target)})
    with patch("psutil.process_iter", return_value=[same_copy]):
        with pytest.raises(RuntimeError, match="outra cópia"):
            ensure_no_other_instances(target)


def test_current_process_and_other_installations_do_not_block_update(tmp_path):
    target = tmp_path / "AssistantDesktop.exe"
    copies = [
        Mock(info={"pid": os.getpid(), "name": target.name, "exe": str(target)}),
        Mock(info={"pid": os.getpid() + 1, "name": target.name,
                   "exe": str(tmp_path / "other" / target.name)}),
    ]
    with patch("psutil.process_iter", return_value=copies):
        ensure_no_other_instances(target)


def test_installer_is_rechecked_before_launch_and_helper_receives_data(tmp_path, monkeypatch):
    release = available(publication())
    installer = tmp_path / release.name
    installer.write_bytes(b"installer")
    executable = tmp_path / "installed" / "AssistantDesktop.exe"
    helper_source = tmp_path / "native-source.exe"
    helper_source.write_bytes(b"native-helper")
    monkeypatch.setenv("SystemRoot", "C:/Windows")
    process = Mock()
    process.poll.return_value = None

    def launch(args, **kwargs):
        from pathlib import Path
        parameters = json.loads(Path(args[-1]).read_text("utf-8"))
        assert parameters["executable"] == str(executable)
        assert parameters["sha256"] == release.sha256
        Path(parameters["ready"]).write_text("ready")
        assert "-ExecutionPolicy" not in args
        assert args[0].endswith(".exe")
        assert not any("powershell" in str(arg).lower() for arg in args)
        return process

    with (
        patch("assistant.updates.installed_executable", return_value=executable),
        patch("assistant.updates.updater_executable", return_value=helper_source),
        patch("assistant.updates.subprocess.Popen", side_effect=launch) as spawn,
    ):
        start_install(release, installer, tmp_path)
        spawn.assert_called_once()
        installer.write_bytes(b"corrupted")
        with pytest.raises(ValueError, match="mudou"):
            start_install(release, installer, tmp_path)
        spawn.assert_called_once()


