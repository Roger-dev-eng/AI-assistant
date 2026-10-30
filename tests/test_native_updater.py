import json
import os
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


def test_other_running_copy_prevents_install_without_terminating_it(native_updater, tmp_path):
    from pathlib import Path

    data = manifest(tmp_path)
    source = tmp_path / "FakeApp.cs"
    source.write_text(
        'class FakeApp { static void Main() { System.Threading.Thread.Sleep(60000); } }',
        "utf-8",
    )
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64",
                    "/out:" + data["executable"], str(source)], check=True)
    child = subprocess.Popen([data["executable"]], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        result, status = invoke(native_updater, tmp_path, data)
        assert result.returncode == 1
        assert "Outra cópia" in status["message"]
        assert child.poll() is None
        assert not (tmp_path / "install.log").exists()
        assert not (tmp_path / "active-update.json").exists()
    finally:
        child.terminate()  # Only the isolated test process created above.
        child.wait(timeout=5)
