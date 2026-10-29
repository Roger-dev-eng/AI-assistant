from threading import Event
from unittest.mock import Mock

import pytest
from jsonschema import ValidationError

from assistant.core.action_executor import ActionExecutor
from assistant.core.intent_router import Action


@pytest.mark.parametrize(
    "action",
    [
        Action("shell", {"command": "calc"}),
        Action("open_app", {"app": "powershell"}),
        Action("open_app", {"app": "chrome", "command": "calc"}),
        Action("open_site", {"url": "file:///C:/secret"}),
        Action("open_site", {"url": "https://127.0.0.1"}),
        Action("set_volume", {"percent": True}),
        Action("set_volume", {"percent": 101}),
    ],
)
def test_reject_invalid_action_before_effects(action):
    backend = Mock()
    executor = ActionExecutor(backend, Mock(return_value=True))
    with pytest.raises((ValueError, ValidationError)):
        executor.execute_plan([Action("open_app", {"app": "chrome"}), action])
    assert not backend.mock_calls


@pytest.mark.parametrize(
    "action", [Action("close_app", {"app": "notepad"}), Action("set_volume", {"percent": 90})]
)
def test_sensitive_actions_can_be_denied(action):
    backend, confirm = Mock(), Mock(return_value=False)
    assert ActionExecutor(backend, confirm).execute(action) == "Action denied by user."
    confirm.assert_called_once()
    assert not backend.mock_calls


def test_cancel_blocks_next_action():
    cancelled, backend = Event(), Mock()
    backend.open_app.side_effect = lambda **kw: cancelled.set()
    executor = ActionExecutor(backend, Mock(), cancelled=cancelled)
    with pytest.raises(InterruptedError):
        executor.execute_plan([Action("open_app", {"app": "chrome"}), Action("active_app")])
    backend.active_app.assert_not_called()


def test_dry_run_has_no_side_effects():
    backend, confirm = Mock(), Mock()
    assert "SIMULATION" in ActionExecutor(backend, confirm, True).execute(
        Action("close_app", {"app": "notepad"})
    )
    assert not backend.mock_calls
    confirm.assert_not_called()


def test_local_denial_stops_plan():
    backend = Mock()
    executor = ActionExecutor(backend, Mock(return_value=False))
    assert executor.execute_plan(
        [Action("close_app", {"app": "notepad"}), Action("open_app", {"app": "chrome"})]
    ) == ["Action denied by user."]
    assert not backend.mock_calls
