import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from assistant.config import Settings
from assistant.ui.settings_dialog import SettingsDialog


def test_configuration_saves_valid_preferences_without_startup_side_effects():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = SettingsDialog(Settings())
    with (
        patch("assistant.ui.settings_dialog.save_preferences") as save,
        patch("assistant.ui.settings_dialog.configure_startup") as startup,
    ):
        dialog.fields["memory_enabled"].setChecked(True)
        dialog.fields["memory_retention_days"].setValue(2)
        dialog.save()
    assert dialog.saved_settings.memory_enabled
    assert dialog.saved_settings.memory_retention_days == 2
    save.assert_called_once()
    startup.assert_not_called()
    dialog.deleteLater()


def test_invalid_secondary_model_rates_never_save_or_enable_startup():
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(Settings())
    with (
        patch("assistant.ui.settings_dialog.save_preferences") as save,
        patch("assistant.ui.settings_dialog.configure_startup") as startup,
        patch("assistant.ui.settings_dialog.QMessageBox.warning") as warning,
    ):
        dialog.fields["secondary_model_id"].setText("alternate")
        dialog.save()
    assert dialog.saved_settings is None
    warning.assert_called_once()
    save.assert_not_called()
    startup.assert_not_called()
    dialog.deleteLater()
    app.processEvents()
