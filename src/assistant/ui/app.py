import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from assistant.config import data_path, preferences_path
from assistant.ui.main_window import MainWindow
from assistant.ui.single_instance import SingleInstance, update_in_progress


def run_desktop(settings, dry_run=False, force_offline=False, start_in_tray=False, setup=False):
    application = QApplication(sys.argv[:1])
    application.setApplicationName("Assistente de IA")
    if update_in_progress(data_path().parent):
        return 0  # The updater will reopen the app after replacing its files.
    instance = SingleInstance(data_path().parent)
    if not instance.acquire():
        if not instance.notified:
            QMessageBox.information(None, "Assistente já aberto",
                                    "O assistente já está aberto. Verifique a janela ou a bandeja.")
        return 0
    try:
        window = MainWindow(settings, data_path(), dry_run, force_offline)
        instance.activation_requested.connect(window.restore_window)
        if not start_in_tray or window.tray is None:
            window.show()
        if setup or not preferences_path().is_file():
            window.show()
            window.open_settings()
        return application.exec()
    finally:
        instance.close()
