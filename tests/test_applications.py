from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from assistant.config import Settings
from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.storage.activity import ActivityStore, database_snapshot
from assistant.storage.applications import ApplicationStore
from assistant.tools.windows import WindowsTools


def catalogue(tmp_path):
    executable = tmp_path / "browser.exe"
    executable.write_bytes(b"synthetic test file; never executed")
    store = ApplicationStore(tmp_path / "usage.sqlite3")
    store.save("Meu navegador", str(executable), ["Chrome", "navegador de trabalho"])
    return store, executable


def test_aliases_persist_and_similar_words_only_produce_suggestions(tmp_path):
    store, executable = catalogue(tmp_path)
    reopened = ApplicationStore(store.path)
    assert reopened.resolve("CHROME")["executable"] == str(executable.resolve())
    assert reopened.suggest("navegador") == ["Meu navegador"]
    with pytest.raises(ValueError):
        reopened.resolve("navegador")
    with pytest.raises(ValueError, match="outro aplicativo"):
        reopened.save("Outro", str(executable), ["chrome"])
    ActivityStore(store.path).clear()
    assert database_snapshot(store.path)["Aplicativos"][1]
    reopened.remove("Meu navegador")
    assert reopened.list() == [] and executable.is_file()


def test_registered_open_bypasses_model_and_interface_inspection(tmp_path):
    store, executable = catalogue(tmp_path)
    backend, provider = WindowsTools(), Mock()
    executor = ActionExecutor(backend, Mock(return_value=True), settings=Settings(), database_path=store.path)
    with patch.object(backend, "_windows"), patch("subprocess.Popen") as launch, patch.object(backend, "inspect_app") as inspect:
        result = Orchestrator(executor, provider).run("Abra o Chrome")
    assert "Meu navegador" in result
    launch.assert_called_once_with([str(executable.resolve())], shell=False)
    provider.converse.assert_not_called()
    inspect.assert_not_called()


def test_missing_executable_cannot_launch_and_offline_configuration_is_preserved(tmp_path):
    store, executable = catalogue(tmp_path)
    executable.unlink()
    backend = WindowsTools()
    backend.configure_runtime(replace(Settings(), cloud_enabled=False), store.path)
    with patch.object(backend, "_windows"), patch("subprocess.Popen") as launch:
        with pytest.raises(RuntimeError, match="não está disponível"):
            backend.open_app("Chrome")
    launch.assert_not_called()
    assert backend.runtime().cloud_enabled is False


def test_catalogue_rejects_scripts_arguments_and_shells(tmp_path):
    store = ApplicationStore(tmp_path / "usage.sqlite3")
    path = tmp_path / "powershell.exe"
    path.write_bytes(b"not executable")
    with pytest.raises(ValueError, match="Interpretadores"):
        store.save("Terminal", str(path), [])
    with pytest.raises(ValueError):
        store.save("Programa", str(path) + " --argument", [])
