from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class SystemTray(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(window.windowIcon(), window)
        self.setToolTip("Assistente de IA")
        self.menu = QMenu(window)
        self.menu.addAction("Abrir assistente", window.restore_window)
        self.menu.addAction("Interromper tarefa", window.stop_task)
        self.menu.addSeparator()
        self.menu.addAction("Sair", window.request_exit)
        self.setContextMenu(self.menu)
        self.activated.connect(self._activate)
        self.window = window

    def _activate(self, reason):
        if reason in (self.ActivationReason.Trigger, self.ActivationReason.DoubleClick):
            self.window.restore_window()
