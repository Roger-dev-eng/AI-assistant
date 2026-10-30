import os
import time
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from assistant.audio.speech_to_text import Transcript
from assistant.config import Settings
from assistant.ui.main_window import MainWindow
from assistant.ui.worker import TaskWorker


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


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
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def submit(window, text):
    window.command.setText(text)
    window.submit()


def test_local_and_aws_tabs_separate_their_controls(make_window):
    window = make_window()
    assert window.mode_tabs.tabText(0) == "Uso local"
    assert window.mode_tabs.tabText(1) == "AWS"
    assert window.local_page.isAncestorOf(window.record_button)
    assert window.local_page.isAncestorOf(window.read_responses)
    assert window.aws_page.isAncestorOf(window.cloud)
    assert window.aws_page.isAncestorOf(window.sonic_record_button)
    assert window.record_button.isVisible()
    assert not window.sonic_record_button.isVisible()
    window.mode_tabs.setCurrentIndex(1)
    assert window.sonic_record_button.isVisible()
    assert not window.record_button.isVisible()
    assert window.speech_choice.currentData() == "sonic"


def test_local_tab_blocks_cloud_even_with_aws_permission_checked(app, make_window):
    selected = []

    def factory(*args, **kwargs):
        selected.append(args[1].cloud_enabled)
        return TaskWorker(*args, **kwargs, backend_factory=Mock)

    window = make_window(dry_run=True, worker_factory=factory)
    window.cloud.setChecked(True)
    submit(window, "Open Chrome")
    wait_until(app, lambda: window.worker is None)
    window.mode_tabs.setCurrentIndex(1)
    submit(window, "Open Chrome")
    wait_until(app, lambda: window.worker is None)
    assert selected == [False, True]


def test_only_one_instance_owns_lock_and_second_activates_first(app, tmp_path):
    from assistant.ui.single_instance import SingleInstance

    first, second = SingleInstance(tmp_path), SingleInstance(tmp_path)
    activated = Mock()
    first.activation_requested.connect(activated)
    try:
        assert first.acquire()
        assert not second.acquire()
        second.notify_existing()
        wait_until(app, lambda: second.notification_finished)
        assert second.notified
        activated.assert_called_once()
        first.close()
        assert second.acquire()
    finally:
        first.close()
        second.close()


def test_unacknowledged_activation_does_not_start_a_second_instance(app, tmp_path, monkeypatch):
    from assistant.ui.single_instance import SingleInstance

    monkeypatch.setattr("assistant.ui.single_instance.ACTIVATION_TIMEOUT_MS", 30)
    first, second = SingleInstance(tmp_path), SingleInstance(tmp_path)
    delivered = Mock()
    second.handoff_finished.connect(delivered)
    try:
        assert first.acquire()
        first.server.newConnection.disconnect(first.receive)
        assert not second.acquire()
        second.notify_existing()
        wait_until(app, lambda: delivered.called)
        delivered.assert_called_once_with(False)
        assert not second.owner
        assert not second.notified
        assert first.owner
    finally:
        second.close()
        first.close()


def test_activation_between_real_processes(app, tmp_path):
    import subprocess
    import sys

    from assistant.ui.single_instance import SingleInstance

    owner = SingleInstance(tmp_path)
    activated = Mock()
    owner.activation_requested.connect(activated)
    child = None
    try:
        assert owner.acquire()
        script = (
            "import sys\nfrom PySide6.QtCore import QCoreApplication, QTimer\n"
            "from assistant.ui.single_instance import SingleInstance\n"
            "app=QCoreApplication([])\nguard=SingleInstance(sys.argv[1])\n"
            "owned=guard.acquire()\n"
            "if not owned:\n"
            "    guard.handoff_finished.connect(lambda delivered: app.quit())\n"
            "    QTimer.singleShot(0, guard.notify_existing)\n"
            "    app.exec()\n"
            "print(str(owned)+','+str(guard.notified), flush=True)\nguard.close()\n"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path)], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        wait_until(app, lambda: child.poll() is not None)
        stdout, stderr = child.communicate(timeout=3)
        assert child.returncode == 0, stderr
        assert stdout.strip() == "False,True"
        activated.assert_called_once()
    finally:
        if child is not None and child.poll() is None:
            child.terminate()  # Only the isolated client process created by this test.
            child.wait(timeout=5)
        owner.close()


def test_desktop_process_exits_after_explicit_shutdown(tmp_path):
    import subprocess
    import sys

    (tmp_path / "settings.json").write_text("{}", "utf-8")
    script = (
        "from unittest.mock import patch\n"
        "from PySide6.QtCore import QTimer\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from assistant.config import Settings\n"
        "from assistant.ui.app import run_desktop\n"
        "from assistant.ui.main_window import MainWindow\n"
        "class ClosingWindow(MainWindow):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        super().__init__(*args, **kwargs)\n"
        "        QApplication.instance().setQuitOnLastWindowClosed(False)\n"
        "        QTimer.singleShot(50, self.request_exit)\n"
        "with patch('assistant.ui.app.MainWindow', ClosingWindow):\n"
        "    raise SystemExit(run_desktop(Settings(), dry_run=True, force_offline=True))\n"
    )
    environment = dict(os.environ, ASSISTANT_DATA_DIR=str(tmp_path), QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-c", script], env=environment, capture_output=True, text=True,
        timeout=15, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "desktop.lock").exists()


def test_sonic_requires_cloud_choice_before_creating_worker(make_window):
    factory = Mock()
    window = make_window(force_offline=True, sonic_worker_factory=factory)
    window.speech_choice.setCurrentIndex(window.speech_choice.findData("sonic"))
    window.record_command()
    factory.assert_not_called()
    assert window.worker is None
    assert "Permitir Bedrock" in window.transcript.toPlainText()


def test_sonic_result_does_not_queue_piper(make_window):
    window = make_window()
    window.read_responses.setChecked(True)
    window.worker_kind = "sonic"
    window.show_result("Resposta já falada pelo Sonic")
    assert not window.queued_speech


def test_update_dialog_downloads_then_hands_off_after_worker_finishes(app, tmp_path):
    from assistant.ui.update_dialog import UpdateDialog
    from assistant.updates import Release

    release = Release("0.3.0", "AssistantDesktop-0.3.0-Setup.exe", "", "", 10)
    installer = tmp_path / release.name
    ready = Mock()
    with (
        patch("assistant.ui.update_dialog.update_directory", return_value=tmp_path),
        patch("assistant.ui.update_dialog.check_update", return_value=release),
        patch("assistant.ui.update_dialog.installed_executable"),
        patch("assistant.ui.update_dialog.download_update", return_value=installer) as download,
        patch("assistant.ui.update_dialog.start_install") as install,
        patch("assistant.ui.update_dialog.QMessageBox.question",
              return_value=QMessageBox.StandardButton.Yes),
    ):
        dialog = UpdateDialog()
        dialog.install_ready.connect(ready)
        dialog.show()
        wait_until(app, lambda: dialog.job is None and dialog.release is not None)
        dialog.download()
        wait_until(app, lambda: ready.called)
        assert dialog.job is None
        download.assert_called_once()
        install.assert_called_once_with(release, installer, tmp_path)
        dialog.deleteLater()


def test_update_shutdown_disables_new_work_before_requesting_exit(app, make_window):
    window = make_window()
    with patch.object(window, "request_exit") as exit_request:
        window.prepare_update_shutdown()
        assert window.exiting
        assert not window.send_button.isEnabled()
        assert not window.record_button.isEnabled()
        assert not window.sonic_record_button.isEnabled()
        wait_until(app, lambda: exit_request.called)
        exit_request.assert_called_once()


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
    ready = Mock()
    window.exit_ready.connect(ready)
    submit(window, "close notepad")
    wait_until(app, lambda: window.confirmation_box is not None)
    window.request_exit()
    wait_until(app, lambda: window.worker is None)
    assert not window.isVisible()
    ready.assert_called_once()
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
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


def test_voice_transcript_is_reviewed_before_any_execution(app, make_window):
    task_factory = Mock()
    with (
        patch("assistant.ui.audio_worker.SpeechToText") as stt,
        patch("assistant.ui.audio_worker.record_microphone", return_value=object()),
    ):
        stt.return_value.transcribe.return_value = Transcript("Abra o Chrome", "pt")
        window = make_window(worker_factory=task_factory)
        window.record_command()
        wait_until(app, lambda: window.worker is None)
    assert window.command.text() == "Abra o Chrome"
    assert "Revise o comando" in window.transcript.toPlainText()
    assert window.send_button.isEnabled()
    task_factory.assert_not_called()


def test_microphone_is_not_opened_when_model_is_missing(app, make_window):
    with patch("assistant.ui.audio_worker.record_microphone") as microphone:
        window = make_window()
        window.record_command()
        wait_until(app, lambda: window.worker is None)
    microphone.assert_not_called()
    assert "WHISPER_MODEL_PATH" in window.transcript.toPlainText()


def test_stopping_recording_discards_transcript(app, make_window):
    def capture(cancelled, finished, seconds, on_recording):
        on_recording()
        cancelled.wait(4)
        if cancelled.is_set():
            raise InterruptedError()
        raise RuntimeError("Test capture was not cancelled")

    with (
        patch("assistant.ui.audio_worker.SpeechToText") as stt,
        patch("assistant.ui.audio_worker.record_microphone", side_effect=capture),
    ):
        window = make_window()
        window.record_command()
        wait_until(app, lambda: window.record_button.text() == "Concluir gravação")
        window.stop_task()
        wait_until(app, lambda: window.worker is None)
    assert window.command.text() == ""
    stt.return_value.transcribe.assert_not_called()
    assert window.record_button.text() == "Gravar comando"


def test_optional_spoken_reply_starts_after_task_finishes(app, make_window):
    with (
        patch("assistant.ui.audio_worker.TextToSpeech") as tts,
        patch("assistant.ui.audio_worker.play_wav") as play,
    ):
        tts.return_value.synthesize.return_value = b"audio"
        window = make_window(dry_run=True)
        window.read_responses.setChecked(True)
        window.language.setCurrentIndex(window.language.findData("en"))
        submit(window, "Open Notepad")
        wait_until(app, lambda: window.worker is None)
    play.assert_called_once()
    assert tts.return_value.synthesize.call_args.args[1] == "en"
    assert window.send_button.isEnabled()


def test_missing_piper_voice_does_not_break_text_conversation(app, make_window):
    window = make_window()
    window.last_response = "Olá"
    window.speak_response()
    wait_until(app, lambda: window.worker is None)
    assert "PIPER_VOICE" in window.transcript.toPlainText()
    assert window.send_button.isEnabled()


def test_wake_command_restores_window_and_requires_review(app, make_window):
    task_factory = Mock()
    with patch(
        "assistant.ui.audio_worker.listen_for_command", return_value=Transcript("Open Chrome", "en")
    ):
        window = make_window(worker_factory=task_factory)
        window.hide()
        window.toggle_wake()
        wait_until(app, lambda: window.worker is None)
    assert window.isVisible()
    assert window.command.text() == "Open Chrome"
    assert window.last_detected_language == "en"
    assert window.microphone_label.text() == "Microfone desligado"
    task_factory.assert_not_called()


def test_stopping_wake_listener_closes_microphone_without_restarting(app, make_window):
    def listen(stt, language, cancelled, finished, settings, phase):
        phase("Microfone ativo · aguardando Assistente ou Assistant…")
        cancelled.wait(4)
        if cancelled.is_set():
            raise InterruptedError()
        raise RuntimeError("Expected cancellation")

    with patch("assistant.ui.audio_worker.listen_for_command", side_effect=listen):
        window = make_window()
        window.toggle_wake()
        wait_until(app, lambda: "ativo" in window.microphone_label.text())
        assert window.wake_button.isEnabled()
        assert window.wake_button.text() == "Parar escuta"
        assert not window.send_button.isEnabled()
        window.toggle_wake()
        wait_until(app, lambda: window.worker is None)
    assert window.command.text() == ""
    assert window.wake_button.text() == "Ativar escuta"
    assert window.microphone_label.text() == "Microfone desligado"
