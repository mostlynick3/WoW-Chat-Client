"""Bounded TCP helpers. Stock WoW clients are IPv4-only, and plain
getaddrinfo()/connect() can block far past socket timeouts (DNS has no
timeout at all), which used to hang logins forever with no feedback.
"""
from __future__ import annotations

import socket
import threading
import time


def _is_literal_ip(host: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, host)
        return True
    except OSError:
        return False


def resolve_ipv4(host: str, timeout: float = 8.0, log=None) -> str:
    """Resolve to an IPv4 address with a hard deadline. Raises with a
    clear message instead of hanging."""
    if _is_literal_ip(host):
        return host
    res: dict = {}

    def _r():
        try:
            res["addrs"] = socket.getaddrinfo(host, None, socket.AF_INET,
                                              socket.SOCK_STREAM)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            res["err"] = exc

    t0 = time.time()
    t = threading.Thread(target=_r, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(
            f"DNS lookup for '{host}' timed out after {timeout:.0f}s "
            f"(no DNS answer — check the hostname and your resolver)")
    if "err" in res or not res.get("addrs"):
        raise ConnectionError(
            f"cannot resolve '{host}': {res.get('err', 'no addresses')}")
    ip = res["addrs"][0][4][0]
    if log:
        log(f"net: {host} -> {ip} ({time.time() - t0:.1f}s)")
    return ip


def connect_tcp(host: str, port: int, timeout: float = 8.0,
                log=None) -> socket.socket:
    """Connect with bounded DNS + bounded TCP handshake."""
    ip = resolve_ipv4(host, timeout, log)
    t0 = time.time()
    try:
        s = socket.create_connection((ip, port), timeout)
    except (socket.timeout, TimeoutError):
        raise TimeoutError(
            f"TCP connect to {host} ({ip}:{port}) timed out after "
            f"{timeout:.0f}s (port filtered or server down?)")
    except ConnectionRefusedError:
        raise ConnectionError(
            f"connection refused by {host} ({ip}:{port}) — "
            f"auth/world server not listening there?")
    except OSError as exc:
        raise ConnectionError(f"cannot reach {host} ({ip}:{port}): {exc}")
    if log:
        log(f"net: TCP {ip}:{port} open ({time.time() - t0:.1f}s)")
    return s
