"""Small HTTPS-only article reader with pinned public IPs and bounded redirects/body size."""

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from assistant.security.urls import public_https_url


def public_addresses(host):
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
        raise ValueError("A fonte não aponta exclusivamente para endereços públicos.")
    return addresses


class PublicConnection(http.client.HTTPSConnection):
    def connect(self):
        # Resolve once, reject any private answer, then connect to that exact IP.
        # TLS still checks the original hostname, preventing a DNS rebind on connect.
        address = public_addresses(self.host)[0]
        raw = socket.create_connection((address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ignored = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer", "header", "form", "noscript", "svg"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "header", "form", "noscript", "svg"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def read_article(url, cancelled, connection_factory=PublicConnection):
    for _ in range(5):
        if cancelled.is_set():
            raise InterruptedError("Pesquisa interrompida.")
        public_https_url(url)
        parts = urlsplit(url)
        connection = connection_factory(parts.hostname, timeout=10, context=ssl.create_default_context())
        try:
            connection.request("GET", (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                               headers={"User-Agent": "AssistantDesktop-Research", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if response.status != 200:
                raise RuntimeError(f"A fonte retornou HTTP {response.status}; nenhum bloqueio foi contornado.")
            content_type = response.getheader("Content-Type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "text/plain")):
                raise ValueError("Esta fonte não é uma página de texto/HTML suportada.")
            if response.getheader("Content-Encoding", "identity") not in {"", "identity"}:
                raise ValueError("A fonte não forneceu texto sem compressão.")
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("A página excedeu o limite de leitura.")
            if cancelled.is_set():
                raise InterruptedError("Pesquisa interrompida.")
            decoded = body.decode("utf-8", errors="replace")
            parser = ArticleText()
            parser.feed(decoded)
            text = " ".join(" ".join(parser.parts).split())[:5000]
            if any(marker in text.lower() for marker in (
                "verify you are human", "sign in to continue", "faça login para continuar",
                "confirme que você é humano",
            )):
                raise RuntimeError("A fonte exige acesso ou verificação; nenhum bloqueio foi contornado.")
            if len(text) < 200:
                raise RuntimeError("Não há texto suficiente; a página pode exigir login ou JavaScript.")
            return {"url": url, "text": text}
        finally:
            connection.close()
    raise ValueError("A fonte excedeu o limite de redirecionamentos.")
