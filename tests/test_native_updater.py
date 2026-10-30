import json
import os
import subprocess
import sys
import time

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


def test_locked_image_is_rejected_before_installing(native_updater, tmp_path):
    import ctypes
    from ctypes import wintypes
    from pathlib import Path

    data = manifest(tmp_path)
    target = Path(data["executable"])
    target.write_bytes(b"not executable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(target), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        result, status = invoke(native_updater, tmp_path, data)
        assert result.returncode == 1
        assert "ainda está em uso" in status["message"]
        assert not (tmp_path / "install.log").exists()
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.parametrize("install_code,verification", [
    (0, "valid"), (5, "valid"), (0, "wrong_version"), (0, "wrong_hash"),
])
def test_update_waits_for_exit_and_restarts_only_on_success(
    native_updater, tmp_path, install_code, verification,
):
    import hashlib
    from pathlib import Path

    data = manifest(tmp_path)
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    target = Path(data["executable"])
    stop_file = tmp_path / "close-request"
    restart_file = tmp_path / "restart-count"
    installed_file = tmp_path / "installed-marker"
    replacement = tmp_path / "replacement.exe"

    def compile_program(name, body, output):
        source = tmp_path / (name + ".cs")
        source.write_text('class Program { static int Main(string[] args) { ' + body + ' } }',
                          "utf-8")
        subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64",
                        "/out:" + str(output), str(source)], check=True)

    # All paths and executables are confined to this test's temporary directory.
    def quote(path):
        return json.dumps(str(path))
    compile_program("OldApp", 'if (args.Length > 0) { System.IO.File.AppendAllText(' +
                    quote(restart_file) + ', "old\\n"); return 0; } '
                    'while (!System.IO.File.Exists(' + quote(stop_file) +
                    ')) System.Threading.Thread.Sleep(20); return 0;', target)
    compile_program("NewApp", 'System.IO.File.AppendAllText(' + quote(restart_file) +
                    ', "start\\n"); return 0;', replacement)
    manifest_source = tmp_path / "new-manifest.json"
    installed_manifest = target.parent / "application-manifest.json"
    manifest_source.write_text(json.dumps({
        "version": "0.0.0" if verification == "wrong_version" else "0.3.2",
        "files": {"AssistantDesktop.exe": (
            "0" * 64 if verification == "wrong_hash"
            else hashlib.sha256(replacement.read_bytes()).hexdigest()
        )},
    }), "utf-8")
    obsolete = target.parent / "obsolete.dll"
    obsolete.write_bytes(b"old bundled library")
    modified = target.parent / "modified.dll"
    modified.write_bytes(b"user modified this file")
    database = target.parent / "history.sqlite3"
    database.write_bytes(b"sensitive history")
    outside = tmp_path / "outside.dll"
    outside.write_bytes(b"outside installation")
    installed_manifest.write_text(json.dumps({"version": "0.3.1", "files": {
        "obsolete.dll": hashlib.sha256(obsolete.read_bytes()).hexdigest(),
        "modified.dll": hashlib.sha256(b"original library").hexdigest(),
        "history.sqlite3": hashlib.sha256(database.read_bytes()).hexdigest(),
        "../outside.dll": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }}), "utf-8")
    installer_body = (
        'System.IO.File.Copy(' + quote(replacement) + ', ' + quote(target) +
        ', true); System.IO.File.Copy(' + quote(manifest_source) + ', ' + quote(installed_manifest) +
        ', true); System.IO.File.WriteAllText(' + quote(installed_file) +
        ', "installed"); return 0;' if install_code == 0 else 'return 5;'
    )
    compile_program("Installer", installer_body, Path(data["installer"]))
    data["sha256"] = hashlib.sha256(Path(data["installer"]).read_bytes()).hexdigest()
    child = subprocess.Popen([str(target)], creationflags=subprocess.CREATE_NO_WINDOW)
    helper = None
    try:
        data["process"] = child.pid
        parameters = tmp_path / "apply.json"
        parameters.write_text(json.dumps(data), "utf-8")
        helper = subprocess.Popen([str(native_updater), str(parameters)],
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 8
        while not Path(data["ready"]).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert Path(data["ready"]).exists()
        assert child.poll() is None
        assert not installed_file.exists()
        stop_file.write_text("close", "utf-8")
        child.wait(timeout=5)
        result = helper.wait(timeout=20)
        status = json.loads(Path(data["status"]).read_text("utf-8"))
        if install_code == 0 and verification == "valid":
            assert result == 0, status
            deadline = time.monotonic() + 5
            while not restart_file.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert target.read_bytes() == replacement.read_bytes()
            assert restart_file.read_text().splitlines() == ["start"]
            assert status["success"] is True
            assert status["installed_version"] == "0.3.2"
            assert not obsolete.exists()
        else:
            assert result == 1, status
            assert status["success"] is False
            assert ("código 5" if install_code == 5 else "versão") in status["message"]
            assert obsolete.exists(), "Cleanup ran before installation was verified"
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                assert not restart_file.exists(), "The failed update restarted the old application"
                time.sleep(0.02)
        assert database.read_bytes() == b"sensitive history"
        assert modified.read_bytes() == b"user modified this file"
        assert outside.read_bytes() == b"outside installation"
        assert not (tmp_path / "active-update.json").exists()
    finally:
        stop_file.write_text("close", "utf-8")
        child.wait(timeout=5)
        if helper is not None and helper.poll() is None:
            helper.terminate()  # Only the updater created for this isolated CI test.
            helper.wait(timeout=5)
