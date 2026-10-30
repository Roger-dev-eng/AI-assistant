import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QEventLoop, QLockFile, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

ACTIVATION_TIMEOUT_MS = 2000


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
        self.notified = False
        if self.lock.tryLock(0):
            self.owner = True
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.close()
                raise RuntimeError("Não foi possível iniciar a comunicação local do assistente.")
            return True
        if self.lock.error() != QLockFile.LockError.LockFailedError:
            raise RuntimeError("Não foi possível bloquear a pasta de dados do assistente.")
        client = QLocalSocket(self)
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        received = bytearray()

        def acknowledge():
            if client.bytesAvailable():
                received.extend(bytes(client.readAll()))
            if b"\n" in received:
                self.notified = bytes(received).split(b"\n", 1)[0] == b"activated"
                loop.quit()

        client.connected.connect(lambda: client.write(b"activate\n"))
        client.readyRead.connect(acknowledge)
        client.errorOccurred.connect(loop.quit)
        client.disconnected.connect(acknowledge)
        client.disconnected.connect(loop.quit)
        timer.timeout.connect(loop.quit)
        timer.start(ACTIVATION_TIMEOUT_MS)
        client.connectToServer(self.name)
        # Process events until the first instance confirms activation, not merely
        # until Windows accepts bytes into the outgoing pipe buffer.
        if not self.notified:
            loop.exec()
        timer.stop()
        client.abort()
        client.deleteLater()
        return False

    def receive(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            received = bytearray()

            def activate(socket=client, buffer=received):
                if socket.property("activationHandled"):
                    return
                buffer.extend(bytes(socket.readAll()))
                if len(buffer) > 64:
                    socket.abort()
                    return
                if b"\n" not in buffer:
                    return
                socket.setProperty("activationHandled", True)
                if bytes(buffer).split(b"\n", 1)[0] == b"activate":
                    self.activation_requested.emit()
                    socket.write(b"activated\n")
                    socket.flush()
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
