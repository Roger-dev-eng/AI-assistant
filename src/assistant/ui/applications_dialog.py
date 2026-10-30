from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from assistant.storage.applications import ApplicationStore


class ApplicationsDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.store = ApplicationStore(path)
        self.setWindowTitle("Aplicativos cadastrados")
        self.resize(650, 450)
        layout = QVBoxLayout(self)
        notice = QLabel("Cadastre um executável e os nomes que você usa por voz. "
                        "A abertura é direta, sem analisar a tela. Não são aceitos argumentos ou scripts. "
                        "Chrome, Word, Calculadora e Bloco de Notas mantêm a abertura padrão quando não cadastrados.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.items = QListWidget()
        self.items.currentTextChanged.connect(self.select)
        layout.addWidget(self.items)
        form = QFormLayout()
        self.name, self.executable, self.aliases = QLineEdit(), QLineEdit(), QLineEdit()
        form.addRow("Nome", self.name)
        form.addRow("Nomes alternativos (separados por ;)", self.aliases)
        row = QHBoxLayout()
        row.addWidget(self.executable)
        browse = QPushButton("Selecionar .exe…")
        browse.clicked.connect(self.browse)
        row.addWidget(browse)
        form.addRow("Executável", row)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        for label, callback in (("Novo", self.clear), ("Salvar", self.save),
                                ("Remover cadastro", self.remove), ("Fechar", self.accept)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.items.clear()
        self.items.addItems([app["name"] for app in self.store.list()])

    def select(self, name):
        if name:
            app = self.store.resolve(name)
            self.name.setText(app["name"])
            self.executable.setText(app["executable"])
            self.aliases.setText("; ".join(app["aliases"]))
            self.name.setReadOnly(True)

    def clear(self):
        self.items.clearSelection()
        self.name.setReadOnly(False)
        for field in (self.name, self.executable, self.aliases):
            field.clear()

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar aplicativo", "", "Aplicativos (*.exe)")
        if path:
            self.executable.setText(path)

    def save(self):
        try:
            self.store.save(self.name.text(), self.executable.text(), self.aliases.text().split(";"))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Cadastro não salvo", str(exc))

    def remove(self):
        item = self.items.currentItem()
        if item and QMessageBox.question(self, "Remover cadastro", "Remover somente o cadastro? O aplicativo não será desinstalado.") == QMessageBox.StandardButton.Yes:
            self.store.remove(item.text())
            self.refresh()
            self.clear()
