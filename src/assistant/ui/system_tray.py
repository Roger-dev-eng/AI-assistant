from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class SystemTray(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(window.windowIcon(), window)
        self.setToolTip("Assistente de IA")
        self.menu = QMenu(window)
        self.menu.addAction("Abrir assistente", window.restore_window)
        self.listen_action = self.menu.addAction("Ativar escuta", window.toggle_wake)
        self.menu.addAction("Interromper tarefa", window.stop_task)
        self.menu.addSeparator()
        self.menu.addAction("Sair", window.request_exit)
        self.setContextMenu(self.menu)
        self.activated.connect(self._activate)
        self.window = window

    def update_controls(self):
        listening = self.window.worker_kind == "wake" or self.window.sonic_wake
        self.listen_action.setText("Parar escuta" if listening else "Ativar escuta")
        self.listen_action.setEnabled(
            not self.window.exiting
            and (
                self.window.worker is None
                or (listening and not self.window.worker.cancelled.is_set())
            )
        )

    def set_microphone_active(self, active):
        self.setToolTip(
            "Assistente de IA · MICROFONE ATIVO (local)"
            if active
            else "Assistente de IA · microfone desligado"
        )
        if active:
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor("#dc2626"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(4, 4, 24, 24)
            painter.end()
            self.setIcon(QIcon(pixmap))
        else:
            self.setIcon(self.window.windowIcon())

    def _activate(self, reason):
        if reason in (self.ActivationReason.Trigger, self.ActivationReason.DoubleClick):
            self.window.restore_window()
