import sys

from PySide6.QtWidgets import QApplication

from assistant.config import data_path, preferences_path
from assistant.ui.main_window import MainWindow


def run_desktop(settings, dry_run=False, force_offline=False, start_in_tray=False, setup=False):
    application = QApplication(sys.argv[:1])
    application.setApplicationName("Assistente de IA")
    window = MainWindow(settings, data_path(), dry_run, force_offline)
    if not start_in_tray or window.tray is None:
        window.show()
    if setup or not preferences_path().is_file():
        window.show()
        window.open_settings()
    return application.exec()
