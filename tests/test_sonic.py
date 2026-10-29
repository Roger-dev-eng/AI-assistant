import asyncio
import json
from dataclasses import replace
from threading import Event
from unittest.mock import AsyncMock, Mock

import pytest

from assistant.ai.sonic_provider import SonicProvider
from assistant.audio.recording import SilenceEndpoint
from assistant.cloud.usage_tracker import UsageTracker
from assistant.config import Settings
from assistant.core.action_executor import ActionExecutor

sdk = pytest.importorskip("aws_sdk_bedrock_runtime.models")


def text_events(role, text, identifier):
    return [
        {
            "contentStart": {
                "contentId": identifier,
                "role": role,
                "additionalModelFields": '{"generationStage":"FINAL"}',
            }
        },
        {"textOutput": {"contentId": identifier, "content": text}},
        {"contentEnd": {"contentId": identifier, "stopReason": "END_TURN"}},
    ]


class FakeStream:
    def __init__(self, events):
        self.events = events
        self.sent = []
        self.input_stream = Mock()
        self.input_stream.send = AsyncMock(side_effect=self.send)
        self.input_stream.close = AsyncMock()
        self.closed = False

    async def send(self, chunk):
        self.sent.append(json.loads(chunk.value.bytes_)["event"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def await_output(self):
        async def iterator():
            for event in self.events:
                await asyncio.sleep(0)
                yield sdk.InvokeModelWithBidirectionalStreamOutputChunk(
                    value=sdk.BidirectionalOutputPayloadPart(
                        bytes_=json.dumps({"event": event}).encode()
                    )
                )

        return None, iterator()


class FakeClient:
    def __init__(self, stream):
        self.stream = stream
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def invoke_model_with_bidirectional_stream(self, request):
        assert request.model_id == "amazon.nova-2-sonic-v1:0"
        return self.stream


def make_provider(tmp_path, events, confirm=True, cancelled=None, cloud=True):
    stream = FakeStream(events)
    client = FakeClient(stream)

    async def factory(settings):
        return client

    tracker = UsageTracker(tmp_path / "usage.sqlite3")
    backend = Mock()
    backend.open_app.return_value = "Opened chrome."
    backend.close_app.return_value = "Requested close."
    provider = SonicProvider(
        replace(Settings(), cloud_enabled=cloud),
        tracker,
        ActionExecutor(backend, Mock(return_value=confirm)),
        cancelled or Event(),
        client_factory=factory,
    )
    return provider, stream, client, tracker, backend


def usage_event():
    return {
        "usageEvent": {
            "details": {
                "total": {
                    "input": {"textTokens": 100, "speechTokens": 200},
                    "output": {"textTokens": 10, "speechTokens": 50},
                }
            }
        }
    }


def test_sonic_consumes_final_text_and_closes_both_streams(tmp_path):
    events = text_events("USER", "Olá", "u") + text_events("ASSISTANT", "Olá, tudo bem?", "a")
    events += [usage_event(), {"completionEnd": {"stopReason": "END_TURN"}}]
    provider, stream, client, tracker, backend = make_provider(tmp_path, events)
    try:
        response = provider.run(b"\x01\x00" * 1600)
        assert response.text == "Olá, tudo bem?"
        assert response.transcript == "Olá"
        assert stream.closed and client.closed
        stream.input_stream.close.assert_awaited_once()
        assert not backend.mock_calls
        assert tracker.summary()[1] == pytest.approx(
            (100 * 0.33 + 200 * 3 + 10 * 2.75 + 50 * 12) / 1e6
        )
        assert any("sessionEnd" in item for item in stream.sent)
    finally:
        tracker.close()


def test_tool_execution_requires_final_user_transcript(tmp_path):
    events = [
        {
            "toolUse": {
                "contentId": "t",
                "toolUseId": "1",
                "toolName": "open_app",
                "content": '{"app":"chrome"}',
            }
        },
        {"contentEnd": {"contentId": "t", "stopReason": "TOOL_USE"}},
    ]
    provider, stream, client, tracker, backend = make_provider(tmp_path, events)
    try:
        with pytest.raises(ValueError, match="transcrição final"):
            provider.run(b"\x01\x00" * 1600)
        assert not backend.mock_calls
        assert stream.closed and client.closed
    finally:
        tracker.close()


def test_denial_stops_remaining_actions_and_discards_audio(tmp_path):
    events = text_events("USER", "Feche o bloco de notas", "u")
    events += [
        {
            "toolUse": {
                "contentId": "t",
                "toolUseId": "1",
                "toolName": "close_app",
                "content": '{"app":"notepad"}',
            }
        },
        {"contentEnd": {"contentId": "t", "stopReason": "TOOL_USE"}},
    ]
    provider, stream, client, tracker, backend = make_provider(tmp_path, events, confirm=False)
    try:
        response = provider.run(b"\x01\x00" * 1600)
        assert "cancelada" in response.text
        assert not response.audio
        assert not backend.mock_calls
    finally:
        tracker.close()


def test_tool_results_return_to_sonic_after_validated_execution(tmp_path):
    events = text_events("USER", "Abra o Chrome", "u")
    events += [
        {
            "toolUse": {
                "contentId": "t",
                "toolUseId": "1",
                "toolName": "open_app",
                "content": '{"app":"chrome"}',
            }
        },
        {"contentEnd": {"contentId": "t", "stopReason": "TOOL_USE"}},
    ]
    events += text_events("ASSISTANT", "Chrome aberto.", "a")
    events += [usage_event(), {"completionEnd": {"stopReason": "END_TURN"}}]
    provider, stream, client, tracker, backend = make_provider(tmp_path, events)
    try:
        provider.run(b"\x01\x00" * 1600)
        backend.open_app.assert_called_once_with(app="chrome")
        assert any(
            item.get("toolResult", {}).get("content") == '{"result": "Opened chrome."}'
            for item in stream.sent
        )
    finally:
        tracker.close()


@pytest.mark.parametrize("cloud,cancelled", [(False, False), (True, True)])
def test_no_network_or_reservation_when_disabled_or_cancelled(tmp_path, cloud, cancelled):
    cancellation = Event()
    if cancelled:
        cancellation.set()
    provider, stream, client, tracker, backend = make_provider(
        tmp_path, [], cancelled=cancellation, cloud=cloud
    )
    try:
        with pytest.raises((RuntimeError, InterruptedError)):
            provider.run(b"\x01\x00")
        assert tracker.summary()[0] == 0
        assert not stream.sent
    finally:
        tracker.close()


def test_budget_blocks_before_opening_stream(tmp_path):
    provider, stream, client, tracker, backend = make_provider(tmp_path, [])
    provider.settings = replace(provider.settings, monthly_budget=0.01)
    try:
        with pytest.raises(RuntimeError, match="budget"):
            provider.run(b"\x01\x00")
        assert not stream.sent
    finally:
        tracker.close()


def test_access_denied_explains_permission_and_releases_reservation(tmp_path):
    provider, stream, client, tracker, backend = make_provider(tmp_path, [])
    client.invoke_model_with_bidirectional_stream = AsyncMock(
        side_effect=sdk.AccessDeniedException(message="Denied")
    )
    try:
        with pytest.raises(RuntimeError, match="bedrock:InvokeModel"):
            provider.run(b"\x01\x00")
        assert tracker.summary() == (1, 0)
        assert client.closed
        assert not backend.mock_calls
    finally:
        tracker.close()


def test_cancelling_open_stream_closes_transport_and_prevents_tools(tmp_path):
    cancellation = Event()
    provider, stream, client, tracker, backend = make_provider(
        tmp_path, [], cancelled=cancellation
    )

    async def await_output():
        async def iterator():
            cancellation.set()
            await asyncio.sleep(1)
            if False:
                yield None

        return None, iterator()

    stream.await_output = await_output
    try:
        with pytest.raises(InterruptedError):
            provider.run(b"\x01\x00")
        assert stream.closed and client.closed
        stream.input_stream.close.assert_awaited_once()
        assert not backend.mock_calls
    finally:
        tracker.close()


def test_usage_is_not_double_counted_and_unknown_failures_keep_reservation(tmp_path):
    provider, stream, client, tracker, backend = make_provider(
        tmp_path, [usage_event(), usage_event()]
    )
    try:
        with pytest.raises(RuntimeError, match="sem uma resposta completa"):
            provider.run(b"\x01\x00")
        assert provider.counts["input_speech"] == 200
        assert tracker.summary()[1] == 0.25
    finally:
        tracker.close()


def test_silence_endpoint_ignores_initial_silence_and_waits_for_a_pause():
    np = pytest.importorskip("numpy")
    endpoint = SilenceEndpoint(1)
    assert not endpoint.feed(np.zeros(32000, dtype="float32"))
    assert not endpoint.feed(np.ones(16000, dtype="float32") * 0.1)
    assert not endpoint.feed(np.zeros(8000, dtype="float32"))
    assert endpoint.feed(np.zeros(8000, dtype="float32"))


def test_short_pause_does_not_cut_following_speech():
    np = pytest.importorskip("numpy")
    endpoint = SilenceEndpoint(1)
    endpoint.feed(np.ones(3200, dtype="float32") * 0.1)
    assert not endpoint.feed(np.zeros(8000, dtype="float32"))
    assert not endpoint.feed(np.ones(3200, dtype="float32") * 0.1)
    assert not endpoint.feed(np.zeros(8000, dtype="float32"))
