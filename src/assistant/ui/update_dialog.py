import json
import os
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from assistant.updates import (
    check_update,
    current_version,
    download_update,
    ensure_no_other_instances,
    installed_executable,
    start_install,
)


def update_directory():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AssistantDesktop" / "updates"


class UpdateJob(QThread):
    value = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, operation, release=None, installer=None, parent=None):
        super().__init__(parent)
        self.operation, self.release, self.installer = operation, release, installer
        self.cancelled = Event()

    def run(self):
        try:
            if self.operation == "check":
                value = check_update()
            elif self.operation == "download":
                value = download_update(
                    self.release, update_directory(), self.cancelled, self.progress.emit
                )
            else:
                start_install(self.release, self.installer, update_directory())
                value = True
            if not self.cancelled.is_set():
                self.value.emit(value)
        except InterruptedError:
            self.failed.emit("Atualização cancelada.")
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    install_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.job, self.release, self.installer = None, None, None
        self.closing, self.ready = False, False
        self.setWindowTitle("Atualizações do assistente")
        self.resize(540, 260)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Versão instalada: {current_version()}"))
        self.status = QLabel("Consultar versões oficiais publicadas no GitHub.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        notice = QLabel(
            "A atualização substitui esta instalação e preserva configurações, "
            "modelos e credenciais. O app será fechado e reaberto após a instalação."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row = QHBoxLayout()
        self.check_button = QPushButton("Verificar novamente")
        self.install_button = QPushButton("Baixar e atualizar")
        self.install_button.setEnabled(False)
        self.close_button = QPushButton("Fechar")
        row.addWidget(self.check_button)
        row.addWidget(self.install_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.check_button.clicked.connect(self.check)
        self.install_button.clicked.connect(self.download)
        self.close_button.clicked.connect(self.reject)
        status_file = update_directory() / "status.json"
        if status_file.is_file():
            try:
                previous = json.loads(status_file.read_text("utf-8-sig"))
                self.status.setText(previous.get("message", ""))
                status_file.unlink()
            except (OSError, ValueError):
                pass
        else:
            QTimer.singleShot(0, self.check)

    def begin(self, operation):
        if self.job is not None:
            return
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.close_button.setText("Cancelar" if operation != "install" else "Aguarde…")
        self.close_button.setEnabled(operation != "install")
        self.job = UpdateJob(operation, self.release, self.installer, self)
        self.job.value.connect(self.received)
        self.job.failed.connect(self.status.setText)
        self.job.progress.connect(self.progress.setValue)
        self.job.finished.connect(self.finished_job)
        self.job.start()

    def check(self):
        self.release = None
        self.installer = None
        self.progress.hide()
        self.status.setText("Consultando a versão mais recente no GitHub…")
        self.begin("check")

    def download(self):
        if self.release is None or self.job is not None:
            return
        self.installer = None
        try:
            ensure_no_other_instances(installed_executable())
        except RuntimeError as exc:
            self.status.setText(str(exc))
            return
        if QMessageBox.question(
            self, "Atualizar aplicativo",
            f"Baixar e instalar a versão {self.release.version}?\n"
            "O assistente será fechado e reaberto. Suas configurações serão preservadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Baixando e verificando o instalador…")
        self.progress.setValue(0)
        self.progress.show()
        self.begin("download")

    def received(self, value):
        if self.job.operation == "check":
            self.release = value
            self.status.setText(
                f"Versão {value.version} disponível ({value.size / 1_000_000:.0f} MB)."
                if value else "Nenhuma versão mais recente publicada."
            )
        elif self.job.operation == "download":
            self.installer = value
        else:
            self.ready = True

    def finished_job(self):
        operation = self.job.operation
        self.job.deleteLater()
        self.job = None
        if self.ready:
            self.accept()
            self.install_ready.emit()
        elif self.closing:
            super().reject()
        elif operation == "download" and self.installer:
            self.status.setText("Integridade verificada. Preparando a atualização…")
            self.begin("install")
        else:
            self.check_button.setEnabled(True)
            self.install_button.setEnabled(self.release is not None)
            self.close_button.setEnabled(True)
            self.close_button.setText("Fechar")

    def reject(self):
        if self.job is not None:
            if self.job.operation == "install":
                return
            self.closing = True
            self.job.cancelled.set()
            self.close_button.setEnabled(False)
            self.status.setText("Cancelando…")
            return
        super().reject()

    def closeEvent(self, event):
        if self.job is not None:
            self.reject()
            event.ignore()
        else:
            event.accept()
