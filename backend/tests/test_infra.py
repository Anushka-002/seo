"""SSRF guard, rate limiter, and progress broker."""

import asyncio
import socket

import httpx
import pytest
from starlette.requests import Request

from app.services import netguard
from app.services.netguard import (
    BlockedHostError,
    check_url_shape,
    ensure_public_host,
    guarded_client,
    is_public_ip,
    request_guard,
)
from app.services.progress import ProgressBroker
from app.services.ratelimit import RateLimiter, client_ip, hash_ip


# ---------------------------------------------------------------- netguard
@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.1.1", "169.254.169.254", "0.0.0.0",
     "::1", "fe80::1", "fd00::1", "::ffff:127.0.0.1", "224.0.0.1", "100.64.0.1"],
)  # fmt: skip
def test_non_public_addresses_are_rejected(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"])
def test_public_addresses_are_allowed(ip):
    assert is_public_ip(ip)


@pytest.mark.parametrize(
    "url", ["ftp://example.com/x", "file:///etc/passwd", "http:///nohost", "http://example.com:22/"]
)
def test_check_url_shape_rejects(url):
    with pytest.raises(BlockedHostError):
        check_url_shape(url)


def test_check_url_shape_accepts_normal_urls():
    for url in ("https://example.com/a", "http://example.com:8080/a", "https://example.com:443/"):
        check_url_shape(url)


async def test_ip_literals_are_checked_without_dns():
    with pytest.raises(BlockedHostError):
        await ensure_public_host("169.254.169.254")
    with pytest.raises(BlockedHostError):
        await ensure_public_host("[::1]")
    await ensure_public_host("8.8.8.8")


async def test_hostname_resolving_to_private_ip_is_blocked(monkeypatch):
    def fake(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(netguard.socket, "getaddrinfo", fake)
    with pytest.raises(BlockedHostError):
        await ensure_public_host("evil.example")


async def test_mixed_dns_answers_are_blocked(monkeypatch):
    def fake(host, *a, **k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr(netguard.socket, "getaddrinfo", fake)
    with pytest.raises(BlockedHostError):
        await ensure_public_host("rebind.example")


async def test_unresolvable_host_is_let_through_to_fail_naturally(monkeypatch):
    def fake(*a, **k):
        raise socket.gaierror("nope")

    monkeypatch.setattr(netguard.socket, "getaddrinfo", fake)
    await ensure_public_host("does-not-exist.example")


async def test_redirect_to_internal_address_is_blocked_on_the_hop():
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        if request.url.host == "8.8.8.8":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        return httpx.Response(200, text="SECRET")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        event_hooks={"request": [request_guard()]},
    )
    async with client:
        with pytest.raises(BlockedHostError):
            await client.get("http://8.8.8.8/start")
    assert hits == ["http://8.8.8.8/start"]  # the internal hop was never requested


async def test_guarded_client_blocks_loopback_before_connecting():
    async with guarded_client(enabled=True) as client:
        with pytest.raises(BlockedHostError):
            await client.get("http://127.0.0.1:8080/admin")


# ---------------------------------------------------------------- rate limiter
def test_sliding_window_limit_and_recovery():
    now = [0.0]
    rl = RateLimiter(limit=3, window=100, clock=lambda: now[0])
    assert [rl.check("a")[0] for _ in range(3)] == [True, True, True]
    allowed, retry = rl.check("a")
    assert not allowed and 1 <= retry <= 101
    assert rl.check("b")[0]  # other keys unaffected
    now[0] = 101.0
    assert rl.check("a")[0]


def test_retry_after_shrinks_over_time():
    now = [0.0]
    rl = RateLimiter(limit=1, window=60, clock=lambda: now[0])
    rl.check("k")
    first = rl.check("k")[1]
    now[0] = 30.0
    assert rl.check("k")[1] < first


def _req(xff: str | None, host: str = "9.9.9.9") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (host, 1234)})


def test_client_ip_uses_rightmost_trusted_hop_not_spoofable_left():
    assert client_ip(_req("6.6.6.6, 1.2.3.4"), trusted_hops=1) == "1.2.3.4"
    assert client_ip(_req("6.6.6.6, 1.2.3.4, 10.0.0.1"), trusted_hops=2) == "1.2.3.4"
    assert client_ip(_req("1.2.3.4"), trusted_hops=2) == "1.2.3.4"


def test_client_ip_falls_back_to_socket_peer():
    assert client_ip(_req(None)) == "9.9.9.9"
    assert client_ip(_req("1.2.3.4"), trusted_hops=0) == "9.9.9.9"


def test_hash_ip_is_stable_and_not_the_ip():
    assert hash_ip("1.2.3.4") == hash_ip("1.2.3.4") != hash_ip("1.2.3.5")
    assert "1.2.3.4" not in hash_ip("1.2.3.4") and len(hash_ip("x")) == 16


# ---------------------------------------------------------------- progress broker
async def _collect(broker, aid, n=None):
    got = []
    async for e in broker.subscribe(aid):
        got.append(e)
        if n and len(got) >= n:
            break
    return got


async def test_late_subscriber_replays_history_then_gets_live_events():
    b = ProgressBroker()
    b.publish("a", "queued", "q", 2)
    b.publish("a", "searching", "s", 10)
    task = asyncio.create_task(_collect(b, "a"))
    await asyncio.sleep(0.01)
    b.publish("a", "done", "d", 100, status="done")
    events = await asyncio.wait_for(task, 1)
    assert [e.stage for e in events] == ["queued", "searching", "done"]
    assert [e.seq for e in events] == [0, 1, 2]


async def test_stream_ends_after_error_and_multiple_subscribers_each_get_all():
    b = ProgressBroker()
    t1, t2 = (asyncio.create_task(_collect(b, "x")) for _ in range(2))
    await asyncio.sleep(0.01)
    b.publish("x", "searching", "s", 10)
    b.publish("x", "error", "boom", 0, status="error")
    r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), 1)
    assert [e.stage for e in r1] == [e.stage for e in r2] == ["searching", "error"]


async def test_early_close_unsubscribes():
    b = ProgressBroker()
    b.publish("y", "queued", "q", 2)
    agen = b.subscribe("y")
    await agen.__anext__()
    assert len(b._subs["y"]) == 1
    await agen.aclose()
    assert b._subs["y"] == []


async def test_forget_and_is_known():
    b = ProgressBroker()
    assert not b.is_known("z")
    b.publish("z", "queued", "q", 2)
    assert b.is_known("z") and len(b.history("z")) == 1
    b.forget("z")
    assert not b.is_known("z")
