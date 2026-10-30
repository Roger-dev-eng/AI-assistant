"""WhatsApp Web drafts: exact recipient, fresh confirmation and one attempt per draft."""

import re
import time
from uuid import uuid4

from assistant.runtime_log import mark


def update_status(store, identifier, status):
    try:
        store.send_status(identifier, status)
    except Exception:
        mark("message.status.write.failed")

class WhatsAppTools:
    def __init__(self, page_factory):
        self.page_factory = page_factory
        self.drafts = {}
        self.current = None

    @staticmethod
    def editor(page):
        editor = page.locator("#main footer [contenteditable='true'][role='textbox']")
        if editor.count() != 1:
            raise RuntimeError("Não há um campo de mensagem único. Nenhuma mensagem foi enviada.")
        return editor

    @staticmethod
    def verify_recipient(page, contact):
        header = page.locator("#main header").get_by_title(contact, exact=True)
        if header.count() != 1 or not header.is_visible():
            raise RuntimeError("O destinatário atual não pôde ser confirmado. Nenhum envio foi realizado.")

    def prepare(self, contact, text, cancelled):
        if cancelled.is_set():
            raise InterruptedError("Mensagem interrompida.")
        contact, text = contact.strip(), text.strip()
        if not contact or not text:
            raise ValueError("Informe o nome exato do contato e a mensagem.")
        page = self.page_factory(cancelled)
        search = page.locator("#side [contenteditable='true'][role='textbox']")
        if search.count() != 1 or not search.is_visible():
            raise RuntimeError("Conecte o WhatsApp Web pelo QR code na janela do assistente e tente novamente.")
        search.fill(contact)
        target = page.locator("#pane-side").get_by_title(contact, exact=True)
        target.first.wait_for(state="visible", timeout=6000)
        if target.count() != 1:
            raise RuntimeError("O contato não é único. Informe um nome completo que identifique uma pessoa.")
        if cancelled.is_set():
            raise InterruptedError("Mensagem interrompida.")
        target.click()
        self.verify_recipient(page, contact)
        editor = self.editor(page)
        if editor.inner_text().strip():
            raise RuntimeError("Essa conversa já contém um rascunho. Ele foi preservado; revise-o manualmente.")
        editor.fill(text)  # No Enter, no keyboard macros, no submit event.
        if editor.inner_text().strip() != text:
            raise RuntimeError("Não foi possível conferir o texto preparado. Revise a conversa manualmente.")
        identifier = uuid4().hex
        self.drafts = {key: draft for key, draft in self.drafts.items()
                       if time.monotonic() - draft["created"] <= 300 and not draft["attempted"]}
        self.drafts[identifier] = {"contact": contact, "text": text, "page": page,
                                   "created": time.monotonic(), "attempted": False}
        self.current = identifier
        return {"draft_id": identifier, "contact": contact, "text": text, "status": "prepared_not_sent"}

    def verify(self, identifier, cancelled):
        identifier = self.current if identifier == "current" else identifier
        draft = self.drafts.get(identifier)
        if draft is None or draft["attempted"] or time.monotonic() - draft["created"] > 300:
            raise RuntimeError("O rascunho expirou ou já teve envio tentado. Confira a conversa; não repita automaticamente.")
        if cancelled.is_set():
            raise InterruptedError("Envio interrompido.")
        page = self.page_factory(cancelled)
        if page is not draft["page"]:
            raise RuntimeError("A sessão do navegador mudou. Prepare e confirme uma nova mensagem.")
        self.verify_recipient(page, draft["contact"])
        editor = self.editor(page)
        if editor.inner_text().strip() != draft["text"]:
            raise RuntimeError("A mensagem mudou desde a preparação. Peça uma nova preparação e confirmação.")
        return identifier, draft, page, editor

    def describe(self, identifier, cancelled):
        _, draft, _, _ = self.verify(identifier, cancelled)
        return f"Enviar mensagem no WhatsApp para {draft['contact']}?\n\n{draft['text']}"

    def send(self, identifier, store, cancelled):
        identifier, draft, page, editor = self.verify(identifier, cancelled)
        button = page.locator("#main footer").get_by_role("button", name=re.compile(r"^(Enviar|Send)$", re.I))
        if button.count() != 1 or not button.is_enabled():
            raise RuntimeError("Não foi localizado um botão Enviar único. Nenhum envio foi tentado.")
        outgoing = page.locator("#main .message-out").get_by_text(draft["text"], exact=True)
        previous_count = outgoing.count()
        store.claim_send(identifier)  # Durable claim BEFORE clicking, including when history is disabled.
        draft["attempted"] = True
        try:
            if cancelled.is_set():
                raise InterruptedError("Envio interrompido antes do clique; confira o rascunho.")
            button.click(timeout=5000)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not editor.inner_text().strip() and outgoing.count() > previous_count:
                    update_status(store, identifier, "visible_in_conversation")
                    return "A mensagem apareceu na conversa. Entrega e leitura não foram verificadas."
                if cancelled.is_set():
                    break
                page.wait_for_timeout(100)
        except Exception:
            update_status(store, identifier, "uncertain")
            raise RuntimeError("O envio foi tentado, mas o resultado é incerto. Confira o WhatsApp; não houve repetição automática.") from None
        update_status(store, identifier, "uncertain")
        raise RuntimeError("Envio acionado, mas não confirmado na conversa. Confira o WhatsApp antes de qualquer novo pedido.")
