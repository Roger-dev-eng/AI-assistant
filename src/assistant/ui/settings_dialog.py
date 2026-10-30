from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from assistant.config import data_path, save_preferences
from assistant.security.startup import configure_startup
from assistant.ui.database_dialog import DatabaseDialog


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.original = settings
        self.saved_settings = None
        self.fields = {}
        self.setWindowTitle("Configuração do assistente")
        self.resize(650, 520)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Configurações locais. Credenciais permanecem no perfil AWS.\n"
            "Voz usa modelos já presentes no disco; nenhum modelo será baixado."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        def page(name):
            widget = QWidget()
            form = QFormLayout(widget)
            tabs.addTab(widget, name)
            return form

        def field(form, key, label, minimum=0, maximum=1000):
            value = getattr(settings, key)
            if key in {"speech_provider", "sonic_voice"}:
                control = QComboBox()
                choices = (
                    {"local": "Local · Whisper/Piper", "sonic": "Nova 2 Sonic · áudio na AWS"}
                    if key == "speech_provider"
                    else {voice: voice for voice in ("carolina", "leo", "tiffany", "matthew")}
                )
                for data, name in choices.items():
                    control.addItem(name, data)
                control.setCurrentIndex(control.findData(value))
            elif isinstance(value, bool):
                control = QCheckBox()
                control.setChecked(value)
            elif isinstance(value, int):
                control = QSpinBox()
                control.setRange(minimum, maximum)
                control.setValue(value)
            elif isinstance(value, float) or key.endswith("_rate"):
                control = QDoubleSpinBox()
                control.setRange(0, 10000)
                control.setDecimals(6)
                control.setValue(value or 0)
            else:
                control = QLineEdit(value)
            self.fields[key] = control
            form.addRow(label, control)
            return control

        general = page("Geral e privacidade")
        field(general, "start_with_windows", "Iniciar com Windows (microfone desligado)")
        field(general, "memory_enabled", "Guardar contexto local (texto sem criptografia)")
        field(general, "memory_retention_days", "Retenção em dias", 1, 365)
        field(general, "memory_max_turns", "Máximo de interações guardadas", 1, 20)
        field(general, "command_history_enabled", "Salvar comandos e navegação (sem criptografia)")
        field(general, "command_history_retention_days", "Retenção dos comandos em dias", 1, 365)
        self.database_button = QPushButton("Ver banco de dados…")
        self.database_button.clicked.connect(self.open_database)
        general.addRow("Histórico, navegação e consumo", self.database_button)
        applications = QPushButton("Cadastrar aplicativos…")
        applications.clicked.connect(self.open_applications)
        general.addRow("Abertura direta por nome ou apelido", applications)
        navigation_notice = QLabel(
            "A correlação usa uma janela separada do Chrome/Edge controlada pelo assistente. "
            "Ela fecha ao sair, mas seu perfil mantém os logins no disco. Entre nas contas nessa janela uma vez; "
            "os sites ainda podem exigir novo login ou CAPTCHA. O perfil pessoal do Chrome não é importado. "
            "Comandos conhecidos continuam locais; "
            "o histórico não autoriza repetir ações. Desativar não apaga registros existentes."
        )
        navigation_notice.setWordWrap(True)
        general.addRow(navigation_notice)
        field(general, "monthly_budget", "Cota estimada mensal (US$)")
        field(general, "daily_requests", "Máximo de requisições por dia", 1, 10000)

        aws = page("AWS e modelos")
        for key, label in [
            ("cloud_enabled", "Habilitar Bedrock"),
            ("profile", "Perfil AWS"),
            ("region", "Região"),
            ("model_id", "Modelo/perfil de inferência principal"),
            ("input_rate", "Principal: US$/milhão de tokens de entrada"),
            ("output_rate", "Principal: US$/milhão de tokens de saída"),
            ("secondary_model_id", "Modelo alternativo (opcional)"),
            ("secondary_input_rate", "Alternativo: US$/milhão de entrada"),
            ("secondary_output_rate", "Alternativo: US$/milhão de saída"),
        ]:
            field(aws, key, label)
        voice = page("Voz local")
        field(voice, "speech_provider", "Reconhecimento e resposta por voz")
        for key, label, directory in [
            ("whisper_model_path", "Pasta faster-whisper", True),
            ("piper_voice_pt", "Voz Piper português (.onnx)", False),
            ("piper_voice_en", "Voz Piper inglês (.onnx)", False),
        ]:
            row = QHBoxLayout()
            control = QLineEdit(getattr(settings, key))
            self.fields[key] = control
            button = QPushButton("Procurar…")
            button.clicked.connect(
                lambda checked=False, c=control, d=directory: self.pick_model(c, d)
            )
            row.addWidget(control)
            row.addWidget(button)
            voice.addRow(label, row)
        field(voice, "voice_enabled", "Ler respostas automaticamente")
        field(voice, "recording_seconds", "Limite de gravação em segundos", 1, 30)
        field(voice, "wake_listen_seconds", "Limite de escuta por ativação", 15, 600)
        field(voice, "silence_seconds", "Pausa para encerrar captura (0,8–3s)")
        sonic = page("Voz AWS")
        sonic.addRow(
            QLabel(
                "Após a ativação, Sonic recebe o áudio e pode executar ferramentas.\n"
                "Ações sensíveis exigem confirmação. Simular ações não impede cobrança AWS."
            )
        )
        for key, label in [
            ("sonic_model_id", "Modelo Sonic"),
            ("sonic_voice", "Voz"),
            ("sonic_text_input_rate", "US$/milhão de tokens de texto de entrada"),
            ("sonic_text_output_rate", "US$/milhão de tokens de texto de saída"),
            ("sonic_audio_input_rate", "US$/milhão de tokens de fala de entrada"),
            ("sonic_audio_output_rate", "US$/milhão de tokens de fala de saída"),
            ("sonic_reservation_usd", "Reserva estimada por sessão (US$)"),
        ]:
            field(sonic, key, label)
        field(sonic, "sonic_timeout_seconds", "Tempo máximo da sessão (segundos)", 30, 180)
        automation = page("Controle e tarefas")
        field(automation, "desktop_automation_enabled", "Permitir controles de interface e WhatsApp Web")
        field(automation, "automation_max_steps", "Máximo de etapas da automação", 5, 30)
        field(automation, "automation_input_bytes", "Limite de contexto da automação (bytes)", 24000, 128000)
        field(automation, "research_enabled", "Permitir tarefas de pesquisa e documento Word")
        automation_notice = QLabel(
            "Nomes dos controles inspecionados podem ser enviados à IA. Cliques e preenchimentos "
            "exigem confirmação. WhatsApp Web exige login por QR e nova confirmação antes de enviar. "
            "A pesquisa usa AWS com os limites de custo existentes e continua após a resposta de voz. "
            "Acompanhe/cancele em Ver banco de dados → Tarefas. Ao sair, tarefas pendentes são canceladas."
        )
        automation_notice.setWordWrap(True)
        automation.addRow(automation_notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def pick_model(self, control, directory):
        path = (
            QFileDialog.getExistingDirectory(self, "Modelo local")
            if directory
            else QFileDialog.getOpenFileName(self, "Voz local", filter="Piper (*.onnx)")[0]
        )
        if path:
            control.setText(path)

    def open_applications(self):
        from assistant.ui.applications_dialog import ApplicationsDialog

        ApplicationsDialog(data_path(), self).exec()

    def open_database(self):
        path = getattr(self.parent(), "database_path", data_path())
        dialog = DatabaseDialog(path, int(self.fields["command_history_retention_days"].value()), self)
        dialog.exec()

    def save(self):
        values = {}
        for key, control in self.fields.items():
            if isinstance(control, QComboBox):
                values[key] = control.currentData()
            elif isinstance(control, QCheckBox):
                values[key] = control.isChecked()
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                values[key] = control.value()
            else:
                values[key] = control.text().strip()
        if not values["secondary_model_id"]:
            values["secondary_input_rate"] = values["secondary_output_rate"] = None
        try:
            updated = replace(self.original, **values)
            if updated.start_with_windows != self.original.start_with_windows:
                configure_startup(updated.start_with_windows)
            try:
                save_preferences(updated)
            except Exception:
                if updated.start_with_windows != self.original.start_with_windows:
                    configure_startup(self.original.start_with_windows)
                raise
        except Exception as exc:
            QMessageBox.warning(self, "Configuração não salva", str(exc))
            return
        self.saved_settings = updated
        self.accept()
