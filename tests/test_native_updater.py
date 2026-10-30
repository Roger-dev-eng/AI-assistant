import json
import subprocess
import sys

import pytest

from scripts.build_updater import build_updater

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows updater")


@pytest.fixture(scope="module")
def native_updater(tmp_path_factory):
    return build_updater(tmp_path_factory.mktemp("native-updater") / "AssistantUpdater.exe")


def manifest(tmp_path):
    installer = tmp_path / "AssistantDesktop-0.3.2-Setup.exe"
    installer.write_bytes(b"not an installer")
    target = tmp_path / "installed"
    target.mkdir()
    return {
        "process": 2147483647, "installer": str(installer),
        "executable": str(target / "AssistantDesktop.exe"), "directory": str(target),
        "ready": str(tmp_path / "ready"), "log": str(tmp_path / "install.log"),
        "status": str(tmp_path / "status.json"), "sha256": "0" * 64,
    }


def invoke(updater, tmp_path, data):
    parameters = tmp_path / "apply.json"
    parameters.write_text(json.dumps(data), "utf-8")
    result = subprocess.run([str(updater), str(parameters)], timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    return result, json.loads((tmp_path / "status.json").read_text("utf-8"))


def test_native_helper_starts_and_rejects_corruption_before_installing(native_updater, tmp_path):
    data = manifest(tmp_path)
    result, status = invoke(native_updater, tmp_path, data)
    assert result.returncode == 1
    assert (tmp_path / "ready").read_text() == "ready"
    assert status["success"] is False
    assert "mudou" in status["message"]
    assert not (tmp_path / "install.log").exists()
    assert not (tmp_path / "apply.json").exists()


def test_native_helper_rejects_installer_outside_cache(native_updater, tmp_path):
    data = manifest(tmp_path)
    data["installer"] = str(tmp_path.parent / "AssistantDesktop-0.3.2-Setup.exe")
    result, status = invoke(native_updater, tmp_path, data)
    assert result.returncode == 1
    assert status["success"] is False
    assert not (tmp_path / "ready").exists()
