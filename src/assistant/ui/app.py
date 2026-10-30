import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from assistant.config import data_path, preferences_path
from assistant.runtime_log import configure, mark
from assistant.ui.main_window import MainWindow
from assistant.ui.single_instance import SingleInstance, update_in_progress


def run_desktop(settings, dry_run=False, force_offline=False, start_in_tray=False, setup=False):
    configure()
    mark("qt.application.create.begin")
    application = QApplication(sys.argv[:1])
    mark("qt.application.create.end", platform=application.platformName())
    application.aboutToQuit.connect(lambda: mark("qt.application.about_to_quit"))
    application.destroyed.connect(lambda: mark("qt.application.destroyed"))
    application.setApplicationName("Assistente de IA")
    application.setQuitOnLastWindowClosed(False)
    if update_in_progress(data_path().parent):
        mark("desktop.update_in_progress")
        return 0  # The updater will reopen the app after replacing its files.
    mark("instance.create.begin")
    instance = SingleInstance(data_path().parent)
    mark("instance.acquire.begin")
    if not instance.acquire():
        mark("instance.acquire.end", available=False)
        notice = QMessageBox()
        notice.setWindowTitle("Assistente já aberto")
        notice.setText("O assistente já está aberto, mas não confirmou a ativação. "
                       "Verifique a janela ou a bandeja.")
        notice.finished.connect(application.quit)

        def handoff_finished(delivered):
            mark("instance.handoff.finished", delivered=delivered)
            if delivered:
                application.quit()
            else:
                notice.open()

        instance.handoff_finished.connect(handoff_finished)
        QTimer.singleShot(0, instance.notify_existing)
        try:
            mark("qt.secondary.event_loop.begin")
            code = application.exec()
            mark("qt.secondary.event_loop.end", code=code)
            return code
        finally:
            mark("instance.close.begin")
            instance.close()
            mark("instance.close.end")
    mark("instance.acquire.end", available=True)
    try:
        mark("window.create.begin")
        window = MainWindow(settings, data_path(), dry_run, force_offline)
        mark("window.create.end")
        window.destroyed.connect(lambda: mark("window.destroyed"))
        window.exit_ready.connect(application.quit, Qt.ConnectionType.QueuedConnection)
        instance.activation_requested.connect(window.restore_window)
        if not start_in_tray or window.tray is None:
            mark("window.show.begin")
            window.show()
            mark("window.show.end")
        if setup or not preferences_path().is_file():
            window.show()
            window.open_settings()
        mark("qt.event_loop.begin")
        code = application.exec()
        mark("qt.event_loop.end", code=code)
        return code
    finally:
        from assistant.core.research import shutdown_research
        from assistant.tools.navigation import shutdown_navigation

        shutdown_research()
        shutdown_navigation()
        mark("instance.close.begin")
        instance.close()
        mark("instance.close.end")
        mark("desktop.return")
