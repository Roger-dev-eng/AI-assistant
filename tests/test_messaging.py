from threading import Event

import pytest
from playwright.sync_api import sync_playwright

from assistant.storage.tasks import TaskStore
from assistant.tools.messaging import WhatsAppTools


@pytest.fixture
def messaging_page():
    # Entirely synthetic DOM: no WhatsApp connection, accounts or real messages.
    with sync_playwright() as api:
        browser = api.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <div id="side"><div contenteditable="true" role="textbox"></div></div>
            <div id="pane-side"><span title="João">João</span></div>
            <div id="main"><header><span title="João">João</span></header>
              <footer><div contenteditable="true" role="textbox"></div>
              <button aria-label="Enviar">Enviar</button></footer></div>
            <script>
            window.sendCount = 0;
            document.querySelector('button').onclick = () => {
              window.sendCount++;
              const editor = document.querySelector('#main [contenteditable]');
              const outgoing = document.createElement('div');
              outgoing.className = 'message-out';
              outgoing.textContent = editor.innerText;
              document.querySelector('#main').appendChild(outgoing);
              editor.innerText = '';
            };
            </script>
        """)
        yield page
        browser.close()


def test_prepare_never_sends_and_confirmed_attempt_cannot_repeat(messaging_page, tmp_path):
    page, cancelled = messaging_page, Event()
    tools = WhatsAppTools(lambda event: page)
    draft = tools.prepare("João", "Bom dia", cancelled)
    assert page.evaluate("window.sendCount") == 0
    assert "João" in tools.describe(draft["draft_id"], cancelled)
    store = TaskStore(tmp_path / "usage.sqlite3")
    assert "apareceu" in tools.send(draft["draft_id"], store, cancelled)
    with pytest.raises(RuntimeError):
        tools.send(draft["draft_id"], store, cancelled)
    with pytest.raises(RuntimeError):
        store.claim_send(draft["draft_id"])
    assert page.evaluate("window.sendCount") == 1


def test_changed_message_and_replaced_page_block_send(messaging_page, tmp_path):
    page, cancelled = messaging_page, Event()
    tools = WhatsAppTools(lambda event: page)
    draft = tools.prepare("João", "Bom dia", cancelled)
    page.locator("#main [contenteditable]").fill("Texto alterado")
    store = TaskStore(tmp_path / "usage.sqlite3")
    with pytest.raises(RuntimeError, match="mudou"):
        tools.send(draft["draft_id"], store, cancelled)
    tools.page_factory = lambda event: object()
    with pytest.raises(RuntimeError, match="sessão"):
        tools.send(draft["draft_id"], store, cancelled)
    assert page.evaluate("window.sendCount") == 0


def test_existing_draft_is_preserved(messaging_page):
    page = messaging_page
    page.locator("#main [contenteditable]").fill("Rascunho do usuário")
    tools = WhatsAppTools(lambda event: page)
    with pytest.raises(RuntimeError, match="preservado"):
        tools.prepare("João", "Substituição", Event())
    assert page.locator("#main [contenteditable]").inner_text() == "Rascunho do usuário"
    assert page.evaluate("window.sendCount") == 0
