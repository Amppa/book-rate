"""Two-tier test contract.

Offline tier (default): outbound sockets, DNS resolution and subprocess
spawning are blocked, so a forgotten mock fails loudly instead of silently
hitting the network.

Live tier: tests marked ``@pytest.mark.live`` opt out and may hit the network.
Loopback traffic (localhost / 127.0.0.1 / ::1) is always allowed so FastAPI
TestClient and anyio portal internals keep working offline.

Usage:
    pytest           run the offline tier (default)
    pytest -m live   run the real-request integration tier
"""
import socket
import subprocess

import pytest


class OfflineViolation(AssertionError):
    """Raised when an offline test attempts a real outbound call."""


_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _is_loopback_target(args):
    """Return True when any positional argument targets the loopback host."""
    for a in args:
        if isinstance(a, str) and a in _LOOPBACK_HOSTS:
            return True
        if isinstance(a, (tuple, list)) and a:
            first = a[0]
            if isinstance(first, str) and first in _LOOPBACK_HOSTS:
                return True
    return False


@pytest.fixture(autouse=True)
def enforce_offline(request):
    """Block real outbound I/O for every test unless marked ``live``."""
    if request.node.get_closest_marker("live"):
        yield
        return

    saved = []

    def swap(obj, name, label):
        original = getattr(obj, name)

        def guard(*args, **kwargs):
            if _is_loopback_target(args):
                return original(*args, **kwargs)
            raise OfflineViolation(
                "OFFLINE VIOLATION: " + label + " was called. Mock the network "
                "layer, or mark this test with @pytest.mark.live if it truly "
                "needs internet access."
            )

        saved.append((obj, name, original))
        setattr(obj, name, guard)

    swap(socket.socket, "connect", "socket.connect")
    swap(socket.socket, "connect_ex", "socket.connect_ex")
    swap(socket, "create_connection", "socket.create_connection")
    swap(socket, "getaddrinfo", "socket.getaddrinfo")
    swap(subprocess, "check_output", "subprocess.check_output")
    swap(subprocess, "check_call", "subprocess.check_call")
    swap(subprocess, "call", "subprocess.call")
    swap(subprocess, "run", "subprocess.run")
    swap(subprocess.Popen, "__init__", "subprocess.Popen.__init__")

    try:
        yield
    finally:
        for obj, name, original in reversed(saved):
            setattr(obj, name, original)


@pytest.fixture(autouse=True)
def _skip_rate_limit_sleeps(request):
    """Offline tier: skip inter-request cooldown sleeps on the shared limiter.

    Patches the singleton INSTANCE only, so unit tests that build their own
    DomainRateLimiter keep exercising the real sleeping logic.
    """
    if request.node.get_closest_marker("live"):
        yield
        return
    from book_rate.utils.rate_limiter import global_rate_limiter
    original = global_rate_limiter.__dict__.get("wait_if_needed")
    global_rate_limiter.wait_if_needed = lambda key, custom_cooldown=None: 0.0
    try:
        yield
    finally:
        if original is None:
            del global_rate_limiter.wait_if_needed
        else:
            global_rate_limiter.wait_if_needed = original
