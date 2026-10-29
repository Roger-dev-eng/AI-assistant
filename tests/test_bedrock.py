from dataclasses import replace
from unittest.mock import Mock

import pytest

from assistant.ai.bedrock_provider import BedrockProvider
from assistant.cloud.usage_tracker import UsageTracker
from assistant.config import Settings
from assistant.core.action_executor import ActionExecutor
from assistant.core.orchestrator import Orchestrator


@pytest.fixture
def tracker(tmp_path):
    value = UsageTracker(tmp_path / "usage.sqlite3")
    yield value
    value.close()


def test_cloud_disabled_never_calls_client(tracker):
    client = Mock()
    with pytest.raises(RuntimeError, match="disabled"):
        BedrockProvider(Settings(), tracker, client).converse([])
    client.converse.assert_not_called()
    assert tracker.summary()[0] == 0


def test_response_is_metered(tracker):
    settings = replace(Settings(), cloud_enabled=True)
    message = {"role": "assistant", "content": [{"text": "Olá"}]}
    client = Mock()
    client.converse.return_value = {
        "output": {"message": message},
        "usage": {"inputTokens": 1000, "outputTokens": 200},
    }
    assert BedrockProvider(settings, tracker, client).converse([]) == message
    assert tracker.summary() == (1, pytest.approx(0.000063))
    assert "toolConfig" in client.converse.call_args.kwargs


def test_failed_request_keeps_reservation_and_blocks_retry(tracker):
    settings = replace(Settings(), cloud_enabled=True, daily_requests=1)
    client = Mock()
    client.converse.side_effect = RuntimeError("network")
    provider = BedrockProvider(settings, tracker, client)
    with pytest.raises(RuntimeError, match="network"):
        provider.converse([])
    assert tracker.summary()[1] > 0
    with pytest.raises(RuntimeError, match="Daily"):
        provider.converse([])
    assert client.converse.call_count == 1


def test_budget_blocks_before_network(tracker):
    settings = replace(Settings(), cloud_enabled=True, monthly_budget=0.000001)
    client = Mock()
    with pytest.raises(RuntimeError, match="budget"):
        BedrockProvider(settings, tracker, client).converse([])
    client.converse.assert_not_called()


def test_reservation_persists_on_reopen(tmp_path):
    path = tmp_path / "usage.sqlite3"
    tracker = UsageTracker(path)
    tracker.reserve(Settings(), 1)
    tracker.close()
    reopened = UsageTracker(path)
    assert reopened.summary() == (1, 1)
    reopened.close()


def test_tool_results_returned_to_model():
    provider, backend = Mock(), Mock()
    backend.open_app.return_value = "Opened chrome."
    provider.converse.side_effect = [
        {
            "role": "assistant",
            "content": [
                {"toolUse": {"toolUseId": "abc", "name": "open_app", "input": {"app": "chrome"}}}
            ],
        },
        {"role": "assistant", "content": [{"text": "Pronto."}]},
    ]
    assistant = Orchestrator(ActionExecutor(backend, Mock()), provider)
    assert assistant.run("Por favor inicie meu Chrome agora") == "Pronto."
    backend.open_app.assert_called_once_with(app="chrome")
    messages = provider.converse.call_args.args[0]
    assert messages[-1]["content"][0]["toolResult"]["toolUseId"] == "abc"


def test_local_commands_never_call_provider():
    provider = Mock()
    backend = Mock()
    backend.open_app.return_value = "Opened chrome."
    assistant = Orchestrator(ActionExecutor(backend, Mock()), provider)
    assert assistant.run("Abra o Chrome") == "Opened chrome."
    provider.converse.assert_not_called()


def test_denial_stops_remaining_cloud_actions():
    provider, backend = Mock(), Mock()
    provider.converse.return_value = {
        "role": "assistant",
        "content": [
            {"toolUse": {"toolUseId": "1", "name": "close_app", "input": {"app": "notepad"}}},
            {"toolUse": {"toolUseId": "2", "name": "open_app", "input": {"app": "chrome"}}},
        ],
    }
    assistant = Orchestrator(ActionExecutor(backend, Mock(return_value=False)), provider)
    assert "cancel" in assistant.run("Feche meu editor e abra meu navegador")
    assert not backend.mock_calls


def test_tool_rounds_are_bounded():
    provider, backend = Mock(), Mock()
    backend.active_app.return_value = "Notepad"
    provider.converse.return_value = {
        "role": "assistant",
        "content": [{"toolUse": {"toolUseId": "1", "name": "active_app", "input": {}}}],
    }
    assistant = Orchestrator(ActionExecutor(backend, Mock()), provider, max_rounds=2)
    assert "limit" in assistant.run("Me conte qual janela está ativa agora").lower()
    assert provider.converse.call_count == 2


def test_malformed_cloud_plan_has_no_side_effects():
    provider, backend = Mock(), Mock()
    provider.converse.return_value = {
        "role": "assistant",
        "content": [
            {"toolUse": {"toolUseId": "1", "name": "open_app", "input": {"app": "chrome"}}},
            {"toolUse": {"name": "active_app", "input": {}}},
        ],
    }
    assistant = Orchestrator(ActionExecutor(backend, Mock()), provider)
    with pytest.raises(ValueError, match="identifier"):
        assistant.run("Please open my browser now")
    assert not backend.mock_calls


def test_cancelled_cloud_response_does_not_continue():
    provider, backend = Mock(), Mock()
    executor = ActionExecutor(backend, Mock())

    def response(messages):
        executor.cancelled.set()
        return {"role": "assistant", "content": [{"text": "Too late"}]}

    provider.converse.side_effect = response
    with pytest.raises(InterruptedError):
        Orchestrator(executor, provider).run("Please talk to me")
    assert not backend.mock_calls
