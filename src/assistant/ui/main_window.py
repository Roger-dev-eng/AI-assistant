from dataclasses import replace

from PySide6.QtCore import Qt, QTimer, Slot
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
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assistant.ai.model_selector import select_model
from assistant.cloud.usage_tracker import UsageTracker
from assistant.storage.memory import ConversationMemory
from assistant.ui.audio_worker import AudioWorker
from assistant.ui.settings_dialog import SettingsDialog
from assistant.ui.sonic_worker import SonicWorker
from assistant.ui.system_tray import SystemTray
from assistant.ui.update_dialog import UpdateDialog
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
        sonic_worker_factory=SonicWorker,
    ):
        super().__init__()
        self.settings = settings
        self.database_path = database_path
        self.worker_factory = worker_factory
        self.audio_worker_factory = audio_worker_factory
        self.sonic_worker_factory = sonic_worker_factory
        self.sonic_wake = False
        self.update_dialog = None
        self.worker = None
        self.worker_kind = None
        self.last_response = ""
        self.last_detected_language = "pt"
        self.queued_speech = ""
        self.force_offline = force_offline
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
        options.addWidget(self.simulation)
        self.model_choice = QComboBox()
        self.model_choice.addItem("Modelo principal", False)
        if settings.secondary_model_id:
            self.model_choice.addItem("Modelo alternativo", True)
        options.addStretch()
        self.clear_button = QPushButton("Limpar conversa")
        options.addWidget(self.clear_button)
        layout.addLayout(options)

        self.mode_tabs = QTabWidget()
        self.local_page, self.aws_page = QWidget(), QWidget()
        local_layout, aws_layout = QVBoxLayout(self.local_page), QVBoxLayout(self.aws_page)
        self.mode_tabs.addTab(self.local_page, "Uso local")
        self.mode_tabs.addTab(self.aws_page, "AWS")
        layout.addWidget(self.mode_tabs)
        local_notice = QLabel("Comandos locais · transcrição com Whisper · leitura com Piper")
        local_notice.setWordWrap(True)
        local_layout.addWidget(local_notice)

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
        local_layout.addLayout(voice_row)

        wake_row = QHBoxLayout()
        self.speech_choice = QComboBox(self)
        self.speech_choice.addItem("Voz local · Whisper/Piper", "local")
        self.speech_choice.addItem("Nova 2 Sonic · áudio na AWS", "sonic")
        self.speech_choice.setCurrentIndex(self.speech_choice.findData(settings.speech_provider))
        self.speech_choice.setToolTip(
            "Sonic envia a gravação à AWS e pode executar comandos após sua fala. "
            "Simular ações preserva as ferramentas sem efeitos reais; áudio AWS é cobrado."
        )
        self.speech_choice.hide()
        self.wake_button = QPushButton("Ativar escuta")
        self.wake_button.setToolTip(
            "Experimental: reconhece Assistente/Assistant localmente. "
            f"Escuta por até {settings.wake_listen_seconds}s; pode consumir CPU."
        )
        self.microphone_label = QLabel("Microfone desligado")
        self.microphone_label.setAccessibleName("Estado do microfone")
        wake_row.addWidget(self.wake_button)
        wake_row.addStretch()
        local_layout.addLayout(wake_row)
        local_layout.addStretch()

        aws_options = QHBoxLayout()
        aws_options.addWidget(self.cloud)
        aws_options.addWidget(self.model_choice)
        aws_options.addStretch()
        aws_layout.addLayout(aws_options)
        aws_notice = QLabel(
            "Texto com Bedrock · voz com Nova 2 Sonic. O áudio é enviado à AWS e a resposta "
            "falada toca automaticamente. A nuvem pode consumir créditos, inclusive em simulação."
        )
        aws_notice.setWordWrap(True)
        aws_layout.addWidget(aws_notice)
        sonic_row = QHBoxLayout()
        self.sonic_record_button = QPushButton("Gravar comando · Sonic")
        self.sonic_wake_button = QPushButton("Ativar escuta · Sonic")
        self.sonic_wake_button.setToolTip(
            "A palavra Assistente é detectada pelo Whisper local; o comando segue para o Sonic."
        )
        sonic_row.addWidget(self.sonic_record_button)
        sonic_row.addWidget(self.sonic_wake_button)
        sonic_row.addStretch()
        aws_layout.addLayout(sonic_row)
        layout.addWidget(self.microphone_label)
        self.mode_tabs.setCurrentIndex(1 if settings.speech_provider == "sonic" else 0)

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
        self.usage_label.setWordWrap(True)
        aws_layout.addWidget(self.usage_label)
        aws_layout.addStretch()
        self.setCentralWidget(content)
        self.force_offline = force_offline

        self.command.returnPressed.connect(self.submit)
        self.send_button.clicked.connect(self.submit)
        self.stop_button.clicked.connect(self.stop_task)
        self.clear_button.clicked.connect(self.transcript.clear)
        self.record_button.clicked.connect(self.record_command)
        self.speak_button.clicked.connect(self.speak_response)
        self.wake_button.clicked.connect(self.toggle_wake)
        self.sonic_record_button.clicked.connect(lambda: self.start_sonic())
        self.sonic_wake_button.clicked.connect(self.toggle_wake)
        self.mode_tabs.currentChanged.connect(self.mode_changed)
        self.speech_choice.currentIndexChanged.connect(self.mode_tabs.setCurrentIndex)
        stop_action = QAction(self)
        stop_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        stop_action.triggered.connect(self.stop_task)
        self.addAction(stop_action)
        menu = self.menuBar().addMenu("Aplicativo")
        self.settings_action = menu.addAction("Configurações…", self.open_settings)
        self.forget_action = menu.addAction("Apagar contexto guardado", self.forget_memory)
        self.update_action = menu.addAction("Verificar atualizações…", self.open_updates)
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
        self.mode_changed(self.mode_tabs.currentIndex())

    @Slot(int)
    def mode_changed(self, index):
        self.speech_choice.setCurrentIndex(index)
        self.command.setPlaceholderText(
            "Comando local · sem envio à AWS…" if index == 0
            else "Comando de texto · Bedrock quando habilitado…"
        )
        if self.tray is not None:
            self.tray.update_controls()

    def append_message(self, author, text):
        # Plain text: model output cannot inject HTML, links, or image loads.
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"{author}\n{text}\n\n")
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def set_busy(self, busy):
        self.mode_tabs.tabBar().setEnabled(not busy and not self.exiting)
        self.command.setEnabled(not busy and not self.exiting)
        self.send_button.setEnabled(not busy and not self.exiting)
        self.stop_button.setEnabled(busy and self.update_dialog is None and not self.exiting)
        self.cloud.setEnabled(not busy and not self.force_offline and not self.exiting)
        self.simulation.setEnabled(not busy and not self.exiting)
        self.record_button.setEnabled(not busy and not self.exiting)
        self.speak_button.setEnabled(not busy and not self.exiting)
        self.language.setEnabled(not busy and not self.exiting)
        self.read_responses.setEnabled(not busy and not self.exiting)
        self.speech_choice.setEnabled(not busy and not self.exiting)
        self.sonic_record_button.setEnabled(not busy and not self.exiting)
        self.model_choice.setEnabled(not busy and not self.exiting)
        self.settings_action.setEnabled(not busy and not self.exiting)
        self.forget_action.setEnabled(not busy and not self.exiting)
        self.update_action.setEnabled(not busy and not self.exiting)
        self.wake_button.setEnabled(
            (not busy or self.worker_kind == "wake") and not self.exiting
        )
        self.wake_button.setText(
            "Parar escuta" if self.worker_kind == "wake" else "Ativar escuta"
        )
        self.sonic_wake_button.setEnabled((not busy or self.sonic_wake) and not self.exiting)
        self.sonic_wake_button.setText(
            "Parar escuta · Sonic" if self.sonic_wake else "Ativar escuta · Sonic"
        )
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
    def open_updates(self):
        if self.worker is not None or self.exiting or self.update_dialog is not None:
            return
        dialog = UpdateDialog(self)
        self.update_dialog = dialog
        dialog.install_ready.connect(self.request_exit)
        dialog.finished.connect(self.updates_closed)
        self.set_busy(True)
        dialog.exec()

    @Slot(int)
    def updates_closed(self, result):
        self.update_dialog = None
        self.set_busy(False)
        if self.exiting:
            QTimer.singleShot(0, self.request_exit)

    @Slot()
    def toggle_wake(self):
        if self.update_dialog is not None:
            return
        if self.worker_kind == "wake" or self.sonic_wake:
            self.stop_task()
        elif self.speech_choice.currentData() == "sonic":
            self.start_sonic(wake=True)
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
        settings = select_model(
            replace(self.settings, cloud_enabled=self.cloud.isChecked()
                    and self.mode_tabs.currentIndex() == 1),
            self.mode_tabs.currentIndex() == 1 and self.model_choice.currentData(),
        )
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
            and self.mode_tabs.currentIndex() == 0
            and self.worker_kind == "task"
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

    def start_sonic(self, wake=False):
        if self.worker is not None or self.exiting:
            return
        if not self.cloud.isChecked():
            self.show_error(
                "Marque Permitir Bedrock (AWS) para usar Nova 2 Sonic. O áudio será enviado à AWS."
            )
            return
        self.sonic_wake = wake
        self.queued_speech = ""
        settings = replace(self.settings, cloud_enabled=True)
        self.worker = self.sonic_worker_factory(
            settings,
            self.database_path,
            self.simulation.isChecked(),
            language=self.language.currentData(),
            wake=wake,
            parent=self,
        )
        self.worker_kind = "sonic"
        self.worker.result.connect(self.show_result)
        self.worker.failed.connect(self.show_error)
        self.worker.phase.connect(self.audio_phase)
        self.worker.user_text.connect(self.sonic_transcript)
        self.worker.action_done.connect(self.sonic_action)
        self.worker.confirmation_requested.connect(self.ask_confirmation)
        self.worker.usage_updated.connect(self.update_usage)
        self.worker.finished.connect(self.task_finished)
        self.set_busy(True)
        self.state_label.setText("Preparando interação Sonic… microfone desligado.")
        self.worker.start()

    @Slot(str)
    def sonic_transcript(self, text):
        if self.worker is None or self.worker.cancelled.is_set() or self.exiting:
            return
        self.restore_window()
        self.append_message("Você (voz enviada à AWS)", text)

    @Slot(str)
    def sonic_action(self, text):
        self.append_message("Ação", text)

    @Slot()
    def record_command(self):
        if self.worker is not None and self.worker_kind in {"record", "wake"}:
            self.worker.recording_finished.set()
            self.record_button.setEnabled(False)
            self.record_button.setText("Gravar comando")
            return
        if self.speech_choice.currentData() == "sonic":
            self.start_sonic()
        else:
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

    @Slot()
    def open_settings(self):
        if self.worker is not None:
            return
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() and dialog.saved_settings is not None:
            self.settings = dialog.saved_settings
            self.speech_choice.setCurrentIndex(
                self.speech_choice.findData(self.settings.speech_provider)
            )
            self.cloud.setChecked(self.settings.cloud_enabled and not self.force_offline)
            self.read_responses.setChecked(self.settings.voice_enabled)
            self.model_choice.clear()
            self.model_choice.addItem("Modelo principal", False)
            if self.settings.secondary_model_id:
                self.model_choice.addItem("Modelo alternativo", True)
            if not self.settings.memory_enabled:
                self.forget_memory()
            self.append_message(
                "Configuração",
                "Configurações salvas. Variáveis do ambiente/.env têm prioridade ao reiniciar.",
            )

    @Slot()
    def forget_memory(self):
        if self.worker is not None:
            return
        memory = ConversationMemory(self.database_path)
        try:
            memory.clear()
        finally:
            memory.close()
        self.append_message(
            "Privacidade", "Contexto guardado apagado. O registro de consumo foi preservado."
        )

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
        self.sonic_wake_button.setEnabled(False)
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
        self.sonic_wake = False
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
        if (
            self.pending_confirmation is not None
            or self.worker_kind == "record"
            or (self.worker_kind == "sonic" and not self.sonic_wake)
        ):
            self.stop_task()
        self.hide()

    @Slot()
    def request_exit(self):
        self.exiting = True
        if self.update_dialog is not None:
            self.update_dialog.reject()
            return
        if self.worker is not None:
            self.stop_task()
            self.set_busy(True)
            self.state_label.setText("Encerrando após a operação atual…")
        else:
            self.close()

    def closeEvent(self, event):
        if self.update_dialog is not None:
            self.request_exit()
            event.ignore()
            return
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
