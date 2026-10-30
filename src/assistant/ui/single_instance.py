import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def update_in_progress(directory):
    cache = (Path(directory) / "updates").resolve()
    try:
        data = json.loads((cache / "active-update.json").read_text("utf-8-sig"))
        helper = Path(data["executable"]).resolve()
        if helper.parent != cache or not helper.name.startswith("AssistantUpdater-"):
            return False
        import psutil

        try:
            process = psutil.Process(int(data["process"]))
            return os.path.normcase(process.exe()) == os.path.normcase(str(helper))
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


class SingleInstance(QObject):
    """One desktop per data directory, with local activation of the existing window."""

    activation_requested = Signal()

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(os.path.normcase(str(directory)).encode()).hexdigest()[:24]
        self.name = f"AssistantDesktop-{identity}"
        self.lock = QLockFile(str(directory / "desktop.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.receive)
        self.owner = False
        self.notified = False

    def acquire(self):
        if self.lock.tryLock(0):
            self.owner = True
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.close()
                raise RuntimeError("Não foi possível iniciar a comunicação local do assistente.")
            return True
        if self.lock.error() != QLockFile.LockError.LockFailedError:
            raise RuntimeError("Não foi possível bloquear a pasta de dados do assistente.")
        client = QLocalSocket()
        client.connectToServer(self.name)
        if client.waitForConnected(2000):
            client.write(b"activate\n")
            self.notified = client.bytesToWrite() == 0 or client.waitForBytesWritten(1000)
            client.disconnectFromServer()
        return False

    def receive(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()

            def activate(socket=client):
                if not socket.canReadLine():
                    return
                if bytes(socket.readLine()).strip() == b"activate":
                    self.activation_requested.emit()
                socket.disconnectFromServer()

            client.readyRead.connect(activate)
            client.disconnected.connect(client.deleteLater)
            if client.bytesAvailable():
                activate()

    def close(self):
        if self.owner:
            self.server.close()
            self.lock.unlock()
            self.owner = False
