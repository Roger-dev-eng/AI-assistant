from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from assistant.storage.activity import ActivityStore, database_snapshot

LABELS = {"created": "Horário UTC", "updated": "Atualizado UTC", "command_text": "Comando",
          "tool": "Ferramenta", "arguments": "Parâmetros", "status": "Estado", "result": "Resultado",
          "site": "Site", "url": "Endereço", "query": "Pesquisa", "model": "Modelo AWS",
          "input_tokens": "Tokens de entrada", "output_tokens": "Tokens de saída", "cost": "US$ estimado",
          "user_text": "Você", "assistant_text": "Assistente"}
LABELS.update({"id": "Tarefa", "title": "Título", "output_path": "Arquivo gerado",
               "message": "Detalhes", "sources": "Fontes e trechos", "draft_id": "Referência do envio"})


class DatabaseDialog(QDialog):
    def __init__(self, path, retention_days=30, parent=None):
        super().__init__(parent)
        self.path, self.days = path, retention_days
        self.tables = {}
        self.setWindowTitle("Banco de dados do assistente")
        self.resize(950, 600)
        layout = QVBoxLayout(self)
        notice = QLabel(
            f"Banco local: {path}\nÚltimos 200 registros por aba, em texto sem criptografia. "
            "Credenciais AWS, cookies e senhas do navegador não são consultados. "
            "Uma referência salva não garante que a aba continue aberta."
        )
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(130)
        self.details.setPlaceholderText("Clique em uma linha para ver os detalhes.")
        layout.addWidget(self.details)
        row = QHBoxLayout()
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        clear = QPushButton("Apagar comandos e contexto de navegação…")
        clear.clicked.connect(self.clear_activity)
        row.addWidget(clear)
        cancel_task = QPushButton("Cancelar tarefa selecionada")
        cancel_task.clicked.connect(self.cancel_task)
        row.addWidget(cancel_task)
        row.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()
        self.tables.clear()
        self.details.clear()
        try:
            snapshot = database_snapshot(self.path)
        except Exception as exc:
            QMessageBox.warning(self, "Banco indisponível", str(exc))
            return
        for name, (columns, rows) in snapshot.items():
            table = QTableWidget(len(rows), len(columns), self)
            table.setHorizontalHeaderLabels([LABELS.get(column, column) for column in columns])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setWordWrap(False)
            for row_index, values in enumerate(rows):
                for column_index, value in enumerate(values):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    table.setItem(row_index, column_index, item)
            table.cellClicked.connect(lambda row, col, t=table, c=columns: self.show_row(t, c, row))
            self.tables[name] = table
            self.tabs.addTab(table, f"{name} ({len(rows)})")

    def show_row(self, table, columns, row):
        self.details.setPlainText("\n".join(
            f"{LABELS.get(column, column)}: {table.item(row, index).text()}"
            for index, column in enumerate(columns)
        ))

    def clear_activity(self):
        if QMessageBox.question(
            self, "Apagar histórico de comandos",
            "Apagar os comandos e as referências de navegação salvos? "
            "O consumo AWS, as conversas e as configurações serão preservados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            ActivityStore(self.path, self.days).clear()
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível apagar", str(exc))
            return
        self.refresh()

    def cancel_task(self):
        table = self.tables.get("Tarefas")
        if table is None or self.tabs.currentWidget() is not table or table.currentRow() < 0:
            QMessageBox.information(self, "Escolha uma tarefa", "Selecione uma linha na aba Tarefas.")
            return
        try:
            from assistant.core.research import research_manager

            research_manager(self.path).cancel(table.item(table.currentRow(), 0).text())
            QMessageBox.information(self, "Cancelamento solicitado", "A tarefa vai parar na próxima etapa segura. "
                                    "Uma chamada AWS já iniciada pode ter consumo. Arquivos prontos são preservados.")
        except Exception as exc:
            QMessageBox.warning(self, "Tarefa indisponível", str(exc))
        self.refresh()
