import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from assistant.config import Settings
from assistant.core.intent_router import Action
from assistant.storage.activity import ActivityStore
from assistant.ui.database_dialog import DatabaseDialog
from assistant.ui.settings_dialog import SettingsDialog


def test_settings_exposes_database_view_and_read_only_command_details(tmp_path):
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    path = tmp_path / "usage.sqlite3"
    store = ActivityStore(path)
    store.record("task", "abre o YouTube", Action("open_site", {"url": "https://www.youtube.com"}),
                 "completed", "Site aberto")
    settings = SettingsDialog(Settings())
    with patch("assistant.ui.settings_dialog.DatabaseDialog") as viewer:
        settings.database_button.click()
        viewer.return_value.exec.assert_called_once()
    dialog = DatabaseDialog(path)
    table = dialog.tables["Comandos"]
    assert table.rowCount() == 1
    dialog.show_row(table, ["created", "command_text", "tool", "arguments", "status", "result"], 0)
    assert "abre o YouTube" in dialog.details.toPlainText()
    assert "completed" in dialog.details.toPlainText()
    dialog.close()
    settings.close()
    dialog.deleteLater()
    settings.deleteLater()
    application.processEvents()
