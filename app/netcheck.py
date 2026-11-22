import ipaddress
import os
import socket
from urllib.parse import urlparse

from .apierrors import ApiError


def check_url(url):
    """Reject URLs that point at internal addresses (server-side request forgery)."""
    p = urlparse(url or "")
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ApiError(400, "INVALID_URL", "Only http and https URLs are accepted.")
    if os.getenv("ALLOW_PRIVATE_URLS", "0") == "1":
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ApiError(400, "URL_UNREACHABLE", "The host name could not be resolved.", retryable=True)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ApiError(400, "URL_NOT_ALLOWED", "URLs that point to internal addresses are not allowed.")
