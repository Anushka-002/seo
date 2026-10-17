"""SSRF protection: never fetch loopback, private, link-local or metadata addresses."""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx

ALLOWED_PORTS = {None, 80, 443, 8080, 8443}


class BlockedHostError(ValueError):
    """Raised when a URL points at a private, internal or unsupported address."""


def is_public_ip(ip: str) -> bool:
    """True only for globally routable addresses (IPv4-mapped IPv6 is unwrapped first)."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def ensure_public_host(host: str) -> None:
    """Resolve `host` and raise BlockedHostError if any address is not public.

    Unresolvable names are allowed through: the request itself will fail with a DNS error.
    """
    host = host.strip("[]")
    try:
        ipaddress.ip_address(host)
        addrs = [host]
    except ValueError:
        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo, host, None, proto=socket.IPPROTO_TCP
            )
        except socket.gaierror:
            return
        addrs = [info[4][0] for info in infos]
    if not all(is_public_ip(a) for a in addrs):
        raise BlockedHostError("That address is private or internal and cannot be fetched.")


def check_url_shape(url: str) -> None:
    """Allow only http(s) on common web ports with a hostname."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BlockedHostError("Only http(s) URLs can be fetched.")
    if parsed.port not in ALLOWED_PORTS:
        raise BlockedHostError("That port is not allowed.")


def request_guard() -> Callable[[httpx.Request], Awaitable[None]]:
    """httpx 'request' event hook: runs before every request, including each redirect hop."""

    async def guard(request: httpx.Request) -> None:
        check_url_shape(str(request.url))
        await ensure_public_host(request.url.host)

    return guard


def guarded_client(
    *, enabled: bool = True, headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    """AsyncClient that follows redirects but re-validates every hop."""
    hooks = {"request": [request_guard()]} if enabled else {}
    return httpx.AsyncClient(headers=headers, follow_redirects=True, event_hooks=hooks)
