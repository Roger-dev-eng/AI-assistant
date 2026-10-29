from dataclasses import replace

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from assistant.ui.audio_worker import AudioWorker
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
        audio_worker_factory=AudioWorker,
    ):
        super().__init__()
        self.settings = settings
        self.database_path = database_path
        self.worker_factory = worker_factory
        self.audio_worker_factory = audio_worker_factory
        self.worker = None
        self.worker_kind = None
        self.last_response = ""
        self.last_detected_language = "pt"
        self.queued_speech = ""
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

        voice_row = QHBoxLayout()
        self.language = QComboBox()
        self.language.addItem("Automático (fala)", "auto")
        self.language.addItem("Português", "pt")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(settings.language))
        self.language.setAccessibleName("Idioma da voz")
        self.language.setToolTip(
            "Automático detecta a fala; leitura usa o último idioma detectado ou português."
        )
        self.record_button = QPushButton("Gravar comando")
        self.record_button.setToolTip(
            f"Ativa o microfone por até {settings.recording_seconds}s. Revise antes de enviar."
        )
        self.speak_button = QPushButton("Ler seleção/resposta")
        self.read_responses = QCheckBox("Ler respostas")
        self.read_responses.setChecked(settings.voice_enabled)
        voice_row.addWidget(self.language)
        voice_row.addWidget(self.record_button)
        voice_row.addWidget(self.speak_button)
        voice_row.addWidget(self.read_responses)
        voice_row.addStretch()
        layout.addLayout(voice_row)

        wake_row = QHBoxLayout()
        self.wake_button = QPushButton("Ativar escuta")
        self.wake_button.setToolTip(
            "Experimental: reconhece Assistente/Assistant localmente. "
            f"Escuta por até {settings.wake_listen_seconds}s; pode consumir CPU."
        )
        self.microphone_label = QLabel("Microfone desligado")
        self.microphone_label.setAccessibleName("Estado do microfone")
        wake_row.addWidget(self.wake_button)
        wake_row.addWidget(self.microphone_label)
        wake_row.addStretch()
        layout.addLayout(wake_row)

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
        self.record_button.clicked.connect(self.record_command)
        self.speak_button.clicked.connect(self.speak_response)
        self.wake_button.clicked.connect(self.toggle_wake)
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
        self.record_button.setEnabled(not busy and not self.exiting)
        self.speak_button.setEnabled(not busy and not self.exiting)
        self.language.setEnabled(not busy and not self.exiting)
        self.read_responses.setEnabled(not busy and not self.exiting)
        self.wake_button.setEnabled((not busy or self.worker_kind == "wake") and not self.exiting)
        self.wake_button.setText("Parar escuta" if self.worker_kind == "wake" else "Ativar escuta")
        if self.tray is not None:
            self.tray.update_controls()

    def set_microphone_active(self, active):
        self.microphone_label.setText(
            "Microfone ativo · áudio local" if active else "Microfone desligado"
        )
        self.microphone_label.setStyleSheet("color: #b42318; font-weight: 600;" if active else "")
        if self.tray is not None:
            self.tray.set_microphone_active(active)

    @Slot()
    def toggle_wake(self):
        if self.worker_kind == "wake":
            self.stop_task()
        else:
            self.start_audio("wake")

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
        self.worker_kind = "task"
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
        self.last_response = text
        if (
            self.read_responses.isChecked()
            and not self.exiting
            and self.worker is not None
            and not self.worker.cancelled.is_set()
        ):
            self.queued_speech = text

    def speech_language(self):
        selected = self.language.currentData()
        return self.last_detected_language if selected == "auto" else selected

    def start_audio(self, mode, text=""):
        if self.worker is not None or self.exiting:
            return
        language = (
            self.language.currentData() if mode in {"record", "wake"} else self.speech_language()
        )
        self.worker = self.audio_worker_factory(
            self.settings, mode=mode, text=text, language=language, parent=self
        )
        self.worker_kind = mode
        self.worker.failed.connect(self.show_error)
        self.worker.phase.connect(self.audio_phase)
        self.worker.transcript_ready.connect(self.review_transcript)
        self.worker.finished.connect(self.task_finished)
        self.set_busy(True)
        self.state_label.setText("Preparando áudio… microfone desligado.")
        self.worker.start()

    @Slot()
    def record_command(self):
        if self.worker is not None and self.worker_kind in {"record", "wake"}:
            self.worker.recording_finished.set()
            self.record_button.setEnabled(False)
            self.record_button.setText("Gravar comando")
            return
        self.start_audio("record")

    @Slot()
    def speak_response(self):
        selection = self.transcript.textCursor().selectedText().replace("\u2029", "\n")
        text = selection or self.last_response
        if not text.strip():
            self.append_message(
                "Voz", "Selecione um texto ou envie um comando antes de pedir a leitura."
            )
            return
        self.start_audio("speak", text)

    @Slot(str)
    def audio_phase(self, text):
        if self.worker is None or self.exiting or self.worker.cancelled.is_set():
            return
        self.state_label.setText(text)
        self.set_microphone_active(text.startswith("Microfone ativo"))
        if self.worker_kind == "record" and text.startswith("Microfone ativo"):
            self.record_button.setText("Concluir gravação")
            self.record_button.setEnabled(True)
        elif self.worker_kind == "record":
            self.record_button.setText("Gravar comando")
            self.record_button.setEnabled(False)
        elif self.worker_kind == "wake":
            capturing = "ativação detectada" in text
            self.record_button.setText("Concluir gravação" if capturing else "Gravar comando")
            self.record_button.setEnabled(capturing)

    @Slot(str, str)
    def review_transcript(self, text, language):
        if self.exiting or self.worker is None or self.worker.cancelled.is_set():
            return
        self.last_detected_language = language
        if self.worker_kind == "wake":
            self.restore_window()
        self.command.setText(text)
        self.append_message(
            "Transcrição", text + "\nRevise o comando e clique Enviar para executar."
        )

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
        self.queued_speech = ""
        if self.worker is None:
            return
        self.worker.cancelled.set()
        self.wake_button.setEnabled(False)
        if self.tray is not None:
            self.tray.update_controls()
        if self.pending_confirmation is not None:
            self.pending_confirmation.answer(False)
        if self.confirmation_box is not None:
            self.confirmation_box.close()
        self.state_label.setText("Interrompendo… aguardando a operação atual terminar.")
        self.stop_button.setEnabled(False)

    @Slot()
    def task_finished(self):
        worker = self.worker
        kind = self.worker_kind
        self.worker = None
        self.worker_kind = None
        self.set_microphone_active(False)
        self.record_button.setText("Gravar comando")
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
            if kind == "task" and self.queued_speech:
                text = self.queued_speech
                self.queued_speech = ""
                self.start_audio("speak", text)

    @Slot()
    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def hide_to_tray(self):
        if self.pending_confirmation is not None or self.worker_kind == "record":
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
