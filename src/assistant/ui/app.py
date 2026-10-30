import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from assistant.config import data_path, preferences_path
from assistant.ui.main_window import MainWindow
from assistant.ui.single_instance import SingleInstance, update_in_progress


def run_desktop(settings, dry_run=False, force_offline=False, start_in_tray=False, setup=False):
    application = QApplication(sys.argv[:1])
    application.setApplicationName("Assistente de IA")
    application.setQuitOnLastWindowClosed(False)
    if update_in_progress(data_path().parent):
        return 0  # The updater will reopen the app after replacing its files.
    instance = SingleInstance(data_path().parent)
    if not instance.acquire():
        notice = QMessageBox()
        notice.setWindowTitle("Assistente já aberto")
        notice.setText("O assistente já está aberto, mas não confirmou a ativação. "
                       "Verifique a janela ou a bandeja.")
        notice.finished.connect(application.quit)

        def handoff_finished(delivered):
            if delivered:
                application.quit()
            else:
                notice.open()

        instance.handoff_finished.connect(handoff_finished)
        QTimer.singleShot(0, instance.notify_existing)
        try:
            return application.exec()
        finally:
            instance.close()
    try:
        window = MainWindow(settings, data_path(), dry_run, force_offline)
        window.exit_ready.connect(application.quit, Qt.ConnectionType.QueuedConnection)
        instance.activation_requested.connect(window.restore_window)
        if not start_in_tray or window.tray is None:
            window.show()
        if setup or not preferences_path().is_file():
            window.show()
            window.open_settings()
        return application.exec()
    finally:
        instance.close()
