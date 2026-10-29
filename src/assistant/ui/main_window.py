from dataclasses import replace

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assistant.cloud.usage_tracker import UsageTracker
from assistant.ui.system_tray import SystemTray
from assistant.ui.worker import TaskWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings,
        database_path,
        dry_run=False,
        force_offline=False,
        enable_tray=True,
        worker_factory=TaskWorker,
    ):
        super().__init__()
        self.settings = settings
        self.database_path = database_path
        self.worker_factory = worker_factory
        self.worker = None
        self.pending_confirmation = None
        self.confirmation_box = None
        self.exiting = False
        self.setWindowTitle("Assistente de IA · Windows")
        self.resize(820, 640)
        self.setMinimumSize(600, 440)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel("Assistente de IA")
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(title)
        subtitle = QLabel("Comandos em português e inglês · execução local e Bedrock")
        layout.addWidget(subtitle)

        options = QHBoxLayout()
        self.cloud = QCheckBox("Permitir Bedrock (AWS)")
        self.cloud.setChecked(settings.cloud_enabled and not force_offline)
        self.cloud.setEnabled(not force_offline)
        self.cloud.setToolTip(
            "Envia solicitações não reconhecidas e resultados de ferramentas à AWS."
        )
        self.simulation = QCheckBox("Simular ações")
        self.simulation.setChecked(dry_run)
        self.simulation.setToolTip(
            "Simula ferramentas. Bedrock pode consumir créditos se habilitado."
        )
        options.addWidget(self.cloud)
        options.addWidget(self.simulation)
        options.addStretch()
        self.clear_button = QPushButton("Limpar conversa")
        options.addWidget(self.clear_button)
        layout.addLayout(options)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setAcceptRichText(False)
        self.transcript.setAccessibleName("Conversa")
        self.transcript.document().setMaximumBlockCount(1000)
        layout.addWidget(self.transcript, 1)
        self.append_message(
            "Assistente",
            "Digite um comando. Exemplos: Abra o Chrome; "
            "search Python on YouTube; volume 50%.\n"
            "Cada envio inicia uma tarefa independente. A conversa fica apenas nesta janela.",
        )

        row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("Digite um comando / Enter a command…")
        self.command.setAccessibleName("Comando")
        self.command.setMaxLength(12000)
        self.send_button = QPushButton("Enviar")
        self.send_button.setDefault(True)
        self.stop_button = QPushButton("Interromper")
        self.stop_button.setEnabled(False)
        row.addWidget(self.command, 1)
        row.addWidget(self.send_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.state_label = QLabel("Pronto · Esc interrompe a tarefa")
        layout.addWidget(self.state_label)
        self.usage_label = QLabel()
        layout.addWidget(self.usage_label)
        self.setCentralWidget(content)
        self.force_offline = force_offline

        self.command.returnPressed.connect(self.submit)
        self.send_button.clicked.connect(self.submit)
        self.stop_button.clicked.connect(self.stop_task)
        self.clear_button.clicked.connect(self.transcript.clear)
        stop_action = QAction(self)
        stop_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        stop_action.triggered.connect(self.stop_task)
        self.addAction(stop_action)
        menu = self.menuBar().addMenu("Aplicativo")
        menu.addAction("Sair", self.request_exit)

        self.tray = None
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = SystemTray(self)
            self.tray.show()
            menu.addAction("Ocultar na bandeja", self.hide_to_tray)
            self.statusBar().showMessage("Fechar a janela mantém o assistente na bandeja.")
        tracker = UsageTracker(database_path)
        try:
            self.update_usage(*tracker.summary())
        finally:
            tracker.close()

    def append_message(self, author, text):
        # Plain text: model output cannot inject HTML, links, or image loads.
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"{author}\n{text}\n\n")
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def set_busy(self, busy):
        self.command.setEnabled(not busy and not self.exiting)
        self.send_button.setEnabled(not busy and not self.exiting)
        self.stop_button.setEnabled(busy and not self.exiting)
        self.cloud.setEnabled(not busy and not self.force_offline and not self.exiting)
        self.simulation.setEnabled(not busy and not self.exiting)

    @Slot()
    def submit(self):
        if self.worker is not None or self.exiting:
            return
        text = self.command.text().strip()
        if not text:
            return
        self.append_message("Você", text)
        self.command.clear()
        settings = replace(self.settings, cloud_enabled=self.cloud.isChecked())
        self.worker = self.worker_factory(
            text, settings, self.database_path, self.simulation.isChecked(), parent=self
        )
        self.worker.result.connect(self.show_result)
        self.worker.failed.connect(self.show_error)
        self.worker.confirmation_requested.connect(self.ask_confirmation)
        self.worker.usage_updated.connect(self.update_usage)
        self.worker.finished.connect(self.task_finished)
        self.set_busy(True)
        self.state_label.setText("Executando… · Esc ou Interromper para cancelar")
        self.worker.start()

    @Slot(str)
    def show_result(self, text):
        self.append_message("Assistente", text)

    @Slot(str)
    def show_error(self, text):
        self.append_message("Erro", text)

    @Slot(int, float)
    def update_usage(self, count, cost):
        self.usage_label.setText(
            f"AWS: {count} requisições · US$ {cost:.6f} estimados (total registrado) · "
            f"cota mensal US$ {self.settings.monthly_budget:g}"
        )

    @Slot(object)
    def ask_confirmation(self, request):
        if self.exiting or self.worker is None or self.worker.cancelled.is_set():
            request.answer(False)
            return
        self.restore_window()
        self.pending_confirmation = request
        box = QMessageBox(self)
        box.setWindowTitle("Confirmar ação")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            f"Permitir esta ação?\n\n{request.description}\n\n"
            "Revise o destino e os efeitos antes de confirmar."
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        # Non-modal: the stop button remains available while the worker waits for an answer.
        box.setWindowModality(Qt.WindowModality.NonModal)
        box.finished.connect(self.answer_confirmation)
        self.confirmation_box = box
        self.state_label.setText("Aguardando confirmação…")
        box.show()

    @Slot(int)
    def answer_confirmation(self, result):
        if self.pending_confirmation is not None:
            self.pending_confirmation.answer(result == QMessageBox.StandardButton.Yes)
        self.pending_confirmation = None
        if self.confirmation_box is not None:
            self.confirmation_box.deleteLater()
            self.confirmation_box = None
        if self.worker is not None and not self.worker.cancelled.is_set():
            self.state_label.setText("Executando…")

    @Slot()
    def stop_task(self):
        if self.worker is None:
            return
        self.worker.cancelled.set()
        if self.pending_confirmation is not None:
            self.pending_confirmation.answer(False)
        if self.confirmation_box is not None:
            self.confirmation_box.close()
        self.state_label.setText("Interrompendo… aguardando a operação atual terminar.")
        self.stop_button.setEnabled(False)

    @Slot()
    def task_finished(self):
        worker = self.worker
        self.worker = None
        if self.confirmation_box is not None:
            self.confirmation_box.close()
        if worker is not None:
            worker.deleteLater()
        self.set_busy(False)
        self.state_label.setText("Pronto · Esc interrompe a tarefa")
        if self.exiting:
            self.close()
        else:
            self.command.setFocus()

    @Slot()
    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def hide_to_tray(self):
        if self.pending_confirmation is not None:
            self.stop_task()
        self.hide()

    @Slot()
    def request_exit(self):
        self.exiting = True
        if self.worker is not None:
            self.stop_task()
            self.set_busy(True)
            self.state_label.setText("Encerrando após a operação atual…")
        else:
            self.close()

    def closeEvent(self, event):
        if self.tray is not None and not self.exiting:
            self.hide_to_tray()
            event.ignore()
            return
        if self.worker is not None:
            self.request_exit()
            event.ignore()
            return
        if self.tray is not None:
            self.tray.hide()
        event.accept()
