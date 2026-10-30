import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal, Slot
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
    handoff_finished = Signal(bool)

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
        self.client = None
        self.received = bytearray()
        self.notification_finished = True
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.notification_timeout)

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
        return False

    @Slot()
    def notify_existing(self):
        if self.owner or not self.notification_finished:
            return
        self.notified = False
        self.notification_finished = False
        self.received.clear()
        self.client = QLocalSocket(self)
        self.client.connected.connect(self.send_activation)
        self.client.readyRead.connect(self.read_confirmation)
        self.client.errorOccurred.connect(self.connection_ended)
        self.client.disconnected.connect(self.connection_ended)
        self.timer.start(ACTIVATION_TIMEOUT_MS)
        self.client.connectToServer(self.name)

    @Slot()
    def send_activation(self):
        if self.client is not None and not self.notification_finished:
            self.client.write(b"activate\n")

    @Slot()
    def read_confirmation(self):
        if self.client is None or self.notification_finished:
            return
        if self.client.bytesAvailable():
            self.received.extend(bytes(self.client.readAll()))
        if len(self.received) > 64:
            self.finish_notification(False)
        elif b"\n" in self.received:
            self.finish_notification(bytes(self.received).split(b"\n", 1)[0] == b"activated")

    @Slot()
    def connection_ended(self):
        self.read_confirmation()
        if not self.notification_finished:
            self.finish_notification(False)

    @Slot()
    def notification_timeout(self):
        self.finish_notification(False)

    def finish_notification(self, delivered):
        if self.notification_finished:
            return
        self.notification_finished = True
        self.notified = bool(delivered)
        self.timer.stop()
        self.dispose_client()
        self.handoff_finished.emit(self.notified)

    def dispose_client(self):
        client, self.client = self.client, None
        if client is not None:
            # Disconnect callbacks before aborting so native error/disconnect signals
            # cannot re-enter cleanup or access a client already scheduled for deletion.
            client.connected.disconnect(self.send_activation)
            client.readyRead.disconnect(self.read_confirmation)
            client.errorOccurred.disconnect(self.connection_ended)
            client.disconnected.disconnect(self.connection_ended)
            client.abort()
            client.deleteLater()

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
        self.notification_finished = True
        self.timer.stop()
        self.dispose_client()
        if self.owner:
            self.server.close()
            self.lock.unlock()
            self.owner = False
