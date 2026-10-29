import ipaddress
import socket
from urllib.parse import urlsplit


def public_https_url(url: str) -> str:
    """Reject local addresses, credentials, custom ports and non-HTTPS schemes."""
    if not isinstance(url, str) or len(url) > 2000 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Invalid search result URL.")
    parts = urlsplit(url)
    host = parts.hostname
    if (
        parts.scheme != "https"
        or not host
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
        or "\\" in url
    ):
        raise ValueError("Only public HTTPS links without credentials are allowed.")
    host = host.lower().rstrip(".")
    if (
        "." not in host
        or host.endswith((".localhost", ".local", ".internal", ".home", ".lan"))
        or host == "localhost"
    ):
        raise ValueError("Local addresses are not allowed.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            host.encode("idna")
        except UnicodeError as exc:
            raise ValueError("Invalid hostname.") from exc
    else:
        if not address.is_global:
            raise ValueError("Private addresses are not allowed.")
    return url


def verify_public_resolution(url: str):
    public_https_url(url)
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Search result resolves to a non-public address.")
