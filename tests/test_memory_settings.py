from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from assistant.ai.model_selector import select_model
from assistant.config import Settings, preferences_path, save_preferences
from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator
from assistant.storage.memory import ConversationMemory


def test_memory_bounds_context_and_erases_content_without_usage(tmp_path):
    memory = ConversationMemory(tmp_path / "memory.sqlite3", max_turns=2)
    for i in range(4):
        memory.remember(f"User {i}", f"Assistant {i}")
    assert [item["content"][0]["text"] for item in memory.messages()] == [
        "User 2",
        "Assistant 2",
        "User 3",
        "Assistant 3",
    ]
    assert memory.messages(max_bytes=1) == []
    memory.clear()
    assert memory.messages() == []
    memory.close()


def test_memory_retention_removes_expired_turns(tmp_path):
    memory = ConversationMemory(tmp_path / "memory.sqlite3", retention_days=1)
    memory.remember("private", "reply")
    with memory.connection:
        memory.connection.execute(
            "UPDATE conversation SET created=?",
            ((datetime.now(UTC) - timedelta(days=2)).isoformat(),),
        )
    assert memory.messages() == []
    memory.close()


def test_orchestrator_passes_memory_as_text_without_replaying_tools(tmp_path):
    memory = ConversationMemory(tmp_path / "memory.sqlite3")
    memory.remember("Meu nome é João", "Olá João")
    provider = Mock()
    provider.converse.return_value = {
        "role": "assistant",
        "content": [{"text": "Seu nome é João."}],
    }
    assistant = Orchestrator(ActionExecutor(Mock(), Mock()), provider, memory=memory)
    assert assistant.run("Qual é meu nome?") == "Seu nome é João."
    assert provider.converse.call_args.args[0][0]["content"][0]["text"] == "Meu nome é João"
    assert len(memory.messages()) == 4
    memory.close()


def test_failed_or_cancelled_task_is_not_remembered(tmp_path):
    memory = ConversationMemory(tmp_path / "memory.sqlite3")
    provider = Mock()
    provider.converse.side_effect = RuntimeError("Offline")
    assistant = Orchestrator(ActionExecutor(Mock(), Mock()), provider, memory=memory)
    with pytest.raises(RuntimeError):
        assistant.run("Converse comigo")
    assert memory.messages() == []
    memory.close()


def test_secondary_model_requires_its_own_rates_and_never_retries():
    with pytest.raises(ValueError):
        Settings(secondary_model_id="another-model")
    settings = Settings(
        secondary_model_id="another-model", secondary_input_rate=1, secondary_output_rate=2
    )
    selected = select_model(settings, True)
    assert (selected.model_id, selected.input_rate, selected.output_rate) == ("another-model", 1, 2)
    assert select_model(settings) is settings


def test_settings_persist_without_credentials_and_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANT_DATA_DIR", str(tmp_path))
    settings = replace(Settings(), profile="my-profile", memory_enabled=True)
    save_preferences(settings)
    assert "secret" not in preferences_path().read_text("utf-8").lower()
    assert Settings.from_env().profile == "my-profile"
    monkeypatch.setenv("AWS_PROFILE", "environment-profile")
    assert Settings.from_env().profile == "environment-profile"
    assert Settings.from_env().memory_enabled


def test_startup_command_uses_only_fixed_arguments(monkeypatch):
    from assistant.security.startup import startup_command

    monkeypatch.setattr("sys.executable", "C:\\Program Files\\Assistant\\AssistantDesktop.exe")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert startup_command() == '"C:\\Program Files\\Assistant\\AssistantDesktop.exe" --gui --tray'
