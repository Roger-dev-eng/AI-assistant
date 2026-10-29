"""Opt-in updates from this project's public GitHub Releases, with asset integrity checks."""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "Roger-dev-eng/AI-assistant"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_INSTALLER_BYTES = 1_500_000_000
ALLOWED_HOSTS = {
    "api.github.com", "github.com", "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("Versão de atualização inválida.")
    return tuple(map(int, match.groups()))


def current_version():
    return version("assistant-desktop")


def safe_url(value):
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Endereço de atualização não autorizado.")
    return value


class ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return super().redirect_request(request, fp, code, msg, headers, safe_url(newurl))


def open_release_url(url, timeout=30):
    request = Request(safe_url(url), headers={
        "User-Agent": "AssistantDesktop-Updater",
        "Accept": "application/vnd.github+json" if url == API_URL else "application/octet-stream",
    })
    return build_opener(ReleaseRedirects()).open(request, timeout=timeout)


@dataclass(frozen=True)
class Release:
    version: str
    name: str
    url: str
    sha256: str
    size: int


def check_update(installed=None, opener=open_release_url):
    installed = installed or current_version()
    try:
        with opener(API_URL) as response:
            data = response.read(1_000_001)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (403, 429):
            raise RuntimeError("GitHub limitou a consulta. Tente novamente mais tarde.") from exc
        raise
    if len(data) > 1_000_000:
        raise ValueError("Resposta de atualização grande demais.")
    release = json.loads(data)
    if release.get("draft") or release.get("prerelease"):
        return None
    tag = release["tag_name"]
    newest = version_tuple(tag)
    if newest <= version_tuple(installed):
        return None
    number = ".".join(map(str, newest))
    filename = f"AssistantDesktop-{number}-Setup.exe"
    expected_url = f"{RELEASES_URL}/download/{tag}/{filename}"
    assets = [asset for asset in release.get("assets", []) if asset.get("name") == filename]
    if len(assets) != 1:
        raise ValueError("A publicação não contém um instalador único compatível.")
    asset = assets[0]
    digest = asset.get("digest", "")
    if (asset.get("browser_download_url") != expected_url
            or not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest)
            or type(asset.get("size")) is not int
            or not 0 < asset["size"] <= MAX_INSTALLER_BYTES):
        raise ValueError("O instalador publicado não tem metadados de integridade válidos.")
    return Release(number, filename, expected_url, digest[7:].lower(), asset["size"])


def download_update(release, directory, cancelled, progress=lambda _: None,
                    opener=open_release_url):
    # Revalidate the immutable selection before touching disk or network.
    expected = f"{RELEASES_URL}/download/v{release.version}/{release.name}"
    if (release.url != expected or release.name != f"AssistantDesktop-{release.version}-Setup.exe"
            or not re.fullmatch(r"[a-f0-9]{64}", release.sha256)
            or not 0 < release.size <= MAX_INSTALLER_BYTES):
        raise ValueError("Seleção de atualização inválida.")
    version_tuple(release.version)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    staging = directory / f"{uuid.uuid4().hex}.part"
    target = directory / release.name
    count, digest = 0, hashlib.sha256()
    try:
        with opener(release.url) as response, staging.open("xb") as output:
            while True:
                if cancelled.is_set():
                    raise InterruptedError("Download de atualização cancelado.")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > release.size:
                    raise ValueError("Tamanho do instalador excedeu o publicado.")
                digest.update(chunk)
                output.write(chunk)
                progress(count * 100 // release.size)
        if count != release.size or digest.hexdigest() != release.sha256:
            raise ValueError("Falha na verificação SHA-256. O instalador não será executado.")
        if cancelled.is_set():
            raise InterruptedError("Download de atualização cancelado.")
        staging.replace(target)
        return target
    finally:
        staging.unlink(missing_ok=True)


def installed_executable():
    executable = Path(sys.executable).resolve()
    if (os.name != "nt" or not getattr(sys, "frozen", False)
            or executable.name.lower() != "assistantdesktop.exe"
            or not (executable.parent / "unins000.exe").is_file()):
        raise RuntimeError(
            "A atualização automática requer a versão instalada do aplicativo. "
            "Instale esta versão uma vez para receber as próximas atualizações pelo app."
        )
    return executable


def start_install(release, installer, directory):
    executable = installed_executable()
    installer = Path(installer).resolve()
    if installer.name != release.name or installer.stat().st_size != release.size:
        raise ValueError("Instalador de atualização inválido.")
    with installer.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != release.sha256:
            raise ValueError("O instalador mudou após o download.")
    # Static helper runs outside the installed directory and waits for this process.
    # JSON carries paths as data: no shell interpolation and no execution-policy override.
    directory = Path(directory)
    parameters = directory / f"apply-{uuid.uuid4().hex}.json"
    ready = directory / f"ready-{uuid.uuid4().hex}"
    parameters.write_text(json.dumps({
        "process": os.getpid(), "installer": str(installer),
        "executable": str(executable), "directory": str(executable.parent),
        "log": str(directory / "install.log"), "status": str(directory / "status.json"),
        "ready": str(ready),
        "sha256": release.sha256,
    }), "utf-8")
    helper = directory / "apply-update.ps1"
    helper.write_bytes(b"\xef\xbb\xbf" + Path(__file__).with_name("apply_update.ps1").read_bytes())
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    process = None
    try:
        process = subprocess.Popen(
            [str(powershell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-File", str(helper), "-ParametersFile", str(parameters)],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        deadline = time.monotonic() + 10
        while not ready.exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError(
                    "O Windows não iniciou o atualizador. O aplicativo continuará aberto."
                )
            time.sleep(0.05)
        ready.unlink(missing_ok=True)
    except Exception:
        if process is not None and process.poll() is None:
            process.terminate()
        parameters.unlink(missing_ok=True)
        raise
