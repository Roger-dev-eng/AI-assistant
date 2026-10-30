"""CI-only real installer check: unchanged files, stale metadata and user-data preservation."""

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def main():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("This real installer check runs only on an isolated Windows Actions runner.")
    version = os.environ["APP_VERSION"]
    root = Path(__file__).resolve().parents[1]
    installer = root / "dist" / "installer" / f"AssistantDesktop-{version}-Setup.exe"
    sandbox = Path(tempfile.mkdtemp(prefix="installer-check-", dir=os.environ["RUNNER_TEMP"]))
    target = sandbox / "installed"
    reports = Path(os.environ["ASSISTANT_LOG_DIR"])
    reports.mkdir(parents=True, exist_ok=True)

    def install(name):
        log = reports / (name + ".log")
        start = time.monotonic()
        result = subprocess.run([
            str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
            "/NOCLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", f"/DIR={target}", f"/LOG={log}",
        ], timeout=240, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(f"Installer {name} returned {result.returncode}; see {log}.")
        return round(time.monotonic() - start, 3)

    fresh = install("fresh-install")
    executable = target / "AssistantDesktop.exe"
    original_time = executable.stat().st_mtime_ns
    original_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    sentinels = [target / "usage.sqlite3", target / "settings.json", target / ".env",
                 sandbox / "userdata" / "history.sqlite3"]
    unknown = target / "_internal" / "assistant_desktop-0.3.7.dist-info"
    stale = target / "_internal" / "assistant_desktop-0.3.8.dist-info"
    for folder, old_version in ((unknown, "0.3.7"), (stale, "0.3.8")):
        folder.mkdir(exist_ok=True)
        (folder / "METADATA").write_text(f"Name: assistant-desktop\nVersion: {old_version}\n", "utf-8")
    sentinels.append(unknown / "history.sqlite3")
    for path in sentinels:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"CI user-data sentinel: must survive reinstall")
    readme = target / "README.md"
    original_readme = readme.read_bytes()
    readme.write_bytes(b"damaged application documentation")
    repeated = install("content-aware-reinstall")
    assert executable.stat().st_mtime_ns == original_time, "Unchanged executable was rewritten"
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == original_hash
    assert readme.read_bytes() == original_readme, "Changed application file was not repaired"
    assert not stale.exists(), "Obsolete metadata remained"
    assert unknown.is_dir(), "Metadata directory containing unknown user data was removed"
    assert all(path.read_bytes() == b"CI user-data sentinel: must survive reinstall" for path in sentinels)
    report = reports / "installed-version.json"
    result = subprocess.run([str(executable), "--diagnostics", str(report)], timeout=120,
                            check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0
    assert json.loads(report.read_text("utf-8"))["version"] == version
    summary = {"fresh_seconds": fresh, "reinstall_seconds": repeated,
               "user_data_preserved": True, "unchanged_executable_preserved": True,
               "version": version}
    (reports / "installer-timing.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
