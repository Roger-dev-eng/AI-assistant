import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from assistant.core.action_executor import ActionExecutor
from assistant.core.intent_router import Action
from assistant.tools.desktop import DesktopTools


def control(name="Salvar", kind="Button", password=False):
    item = Mock()
    item.element_info = SimpleNamespace(name=name, control_type=kind, automation_id=name,
                                        runtime_id=(1, 2), element=SimpleNamespace(CurrentIsPassword=password))
    item.is_visible.return_value = item.is_enabled.return_value = True
    return item


def desktop(items):
    window, process, api = Mock(), Mock(), Mock()
    window.process_id.return_value, window.handle = 101, 202
    window.window_text.return_value = "Documento1 - Word"
    window.class_name.return_value = "OpusApp"
    window.is_visible.return_value = True
    window.descendants.return_value = items
    process.name.return_value, process.create_time.return_value = "WINWORD.EXE", 1.0
    api.windows.return_value = [window]
    api.window.return_value.wrapper_object.return_value = window
    return DesktopTools(Event(), lambda: api, lambda _: process), window, process


def test_inspection_hides_password_and_macro_controls_and_tokens_expire_after_click():
    button, password, macro = control(), control("Senha", "Edit", True), control("Macros")
    tools, _, _ = desktop([button, password, macro])
    result = json.loads(tools.inspect("word"))
    assert len(result["controls"]) == 1
    token = result["controls"][0]["control_id"]
    tools.click(token)
    button.invoke.assert_called_once()
    with pytest.raises(ValueError, match="expirado"):
        tools.click(token)
    password.set_edit_text.assert_not_called()
    macro.invoke.assert_not_called()


@pytest.mark.parametrize("change", ["title", "process", "name"])
def test_changed_window_process_or_control_cannot_receive_stale_action(change):
    button = control()
    tools, window, process = desktop([button])
    token = json.loads(tools.inspect("word"))["controls"][0]["control_id"]
    if change == "title":
        window.window_text.return_value = "Outro documento - Word"
    elif change == "process":
        process.create_time.return_value = 2.0
    else:
        button.element_info.name = "Excluir"
    with pytest.raises(RuntimeError):
        tools.click(token)
    button.invoke.assert_not_called()


def test_literal_fill_never_interprets_keyboard_macros():
    edit = control("Texto", "Edit")
    tools, _, _ = desktop([edit])
    token = json.loads(tools.inspect("word"))["controls"][0]["control_id"]
    tools.fill(token, "^{ENTER}")
    edit.set_edit_text.assert_called_once_with("^{ENTER}")


def test_denial_prevents_interface_mutation_and_uncertain_send_is_not_retried():
    backend = Mock()
    executor = ActionExecutor(backend, Mock(return_value=False))
    assert executor.execute(Action("click_control", {"control_id": "a" * 32})) == "Action denied by user."
    backend.click_control.assert_not_called()
    executor.confirm.return_value = True
    backend.whatsapp_send_message.side_effect = RuntimeError("incerto")
    action = Action("whatsapp_send_message", {"draft_id": "current"})
    with pytest.raises(RuntimeError, match="incerto"):
        executor.execute(action)
    with pytest.raises(RuntimeError, match="já foi tentado"):
        executor.execute(action)
    backend.whatsapp_send_message.assert_called_once()
