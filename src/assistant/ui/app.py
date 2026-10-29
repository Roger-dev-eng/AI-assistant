import sys

from PySide6.QtWidgets import QApplication

from assistant.config import data_path
from assistant.ui.main_window import MainWindow


def run_desktop(settings, dry_run=False, force_offline=False):
    application = QApplication(sys.argv[:1])
    application.setApplicationName("Assistente de IA")
    window = MainWindow(settings, data_path(), dry_run, force_offline)
    window.show()
    return application.exec()
