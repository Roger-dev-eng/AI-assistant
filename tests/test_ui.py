import os
import time
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from assistant.config import Settings
from assistant.ui.main_window import MainWindow
from assistant.ui.worker import TaskWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(app, condition, timeout=8):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert condition(), "Timed out waiting for UI/worker state"


@pytest.fixture
def make_window(app, tmp_path):
    windows = []

    def create(**kwargs):
        window = MainWindow(Settings(), tmp_path / "usage.sqlite3", enable_tray=False, **kwargs)
        windows.append(window)
        window.show()
        return window

    yield create
    for window in windows:
        if window.worker is not None:
            window.stop_task()
            assert window.worker.wait(8000)
            app.processEvents()
        window.request_exit()
        app.processEvents()


def submit(window, text):
    window.command.setText(text)
    window.submit()


def test_simulated_task_keeps_ui_responsive(app, make_window):
    window = make_window(dry_run=True, force_offline=True)
    submit(window, "Abra o Chrome")
    assert not window.send_button.isEnabled()
    assert window.stop_button.isEnabled()
    wait_until(app, lambda: window.worker is None)
    assert "SIMULATION: open_app" in window.transcript.toPlainText()
    assert window.send_button.isEnabled()
    assert not window.cloud.isEnabled()
    assert "0 requisições" in window.usage_label.text()


def test_offline_unknown_request_is_shown_as_error(app, make_window):
    window = make_window(force_offline=True)
    submit(window, "Converse comigo sobre astronomia")
    wait_until(app, lambda: window.worker is None)
    assert "Cloud disabled" in window.transcript.toPlainText()
    assert window.send_button.isEnabled()


def factory_with_backend(backend):
    def factory(*args, **kwargs):
        return TaskWorker(*args, **kwargs, backend_factory=lambda: backend)

    return factory


def test_denial_in_gui_prevents_effects(app, make_window):
    backend = Mock()
    window = make_window(worker_factory=factory_with_backend(backend))
    submit(window, "feche o bloco de notas e depois abra o chrome")
    wait_until(app, lambda: window.confirmation_box is not None)
    assert window.stop_button.isEnabled()
    window.confirmation_box.button(QMessageBox.StandardButton.No).click()
    wait_until(app, lambda: window.worker is None)
    assert not backend.mock_calls
    assert "Action denied" in window.transcript.toPlainText()


def test_approval_in_gui_executes_once(app, make_window):
    backend = Mock()
    backend.close_app.return_value = "Requested close."
    window = make_window(worker_factory=factory_with_backend(backend))
    submit(window, "close notepad")
    wait_until(app, lambda: window.confirmation_box is not None)
    window.confirmation_box.button(QMessageBox.StandardButton.Yes).click()
    wait_until(app, lambda: window.worker is None)
    backend.close_app.assert_called_once_with(app="notepad")
    assert "Requested close" in window.transcript.toPlainText()


def test_stop_while_confirmation_is_pending(app, make_window):
    backend = Mock()
    window = make_window(worker_factory=factory_with_backend(backend))
    submit(window, "close notepad")
    wait_until(app, lambda: window.confirmation_box is not None)
    window.stop_task()
    wait_until(app, lambda: window.worker is None)
    assert not backend.mock_calls
    assert window.confirmation_box is None
    assert "Task interrupted" in window.transcript.toPlainText()


def test_exit_waits_for_worker_before_closing(app, make_window):
    backend = Mock()
    window = make_window(worker_factory=factory_with_backend(backend))
    submit(window, "close notepad")
    wait_until(app, lambda: window.confirmation_box is not None)
    window.request_exit()
    wait_until(app, lambda: window.worker is None)
    assert not window.isVisible()
    assert not backend.mock_calls


def test_response_is_rendered_as_plain_text(make_window):
    window = make_window()
    window.show_result('<img src="https://example.com/image">')
    assert '<img src="https://example.com/image">' in window.transcript.toPlainText()


def test_tray_hides_restores_and_exits(app, tmp_path):
    with (
        patch("assistant.ui.main_window.QSystemTrayIcon.isSystemTrayAvailable", return_value=True),
        patch("assistant.ui.main_window.SystemTray") as tray,
    ):
        window = MainWindow(Settings(), tmp_path / "tray.sqlite3")
        try:
            window.show()
            window.close()
            assert not window.isVisible()
            assert not window.exiting
            window.restore_window()
            assert window.isVisible()
            window.request_exit()
            assert not window.isVisible()
            tray.return_value.hide.assert_called_once()
        finally:
            window.request_exit()
            app.processEvents()
