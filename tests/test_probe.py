from __future__ import annotations

import socket
import ssl
import threading
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sync.probe import detect_scheme

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _serve(handler: Callable[[socket.socket, threading.Event], None]) -> Iterator[int]:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]
    stop = threading.Event()

    def loop() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except TimeoutError:
                continue
            handler(conn, stop)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    yield port
    stop.set()
    t.join()
    srv.close()


@pytest.fixture
def http_port() -> Iterator[int]:
    """A plain HTTP server: reads the ClientHello, answers 400 and closes."""

    def handle(conn: socket.socket, stop: threading.Event) -> None:
        with conn:
            conn.recv(1024)
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")

    yield from _serve(handle)


@pytest.fixture
def silent_port() -> Iterator[int]:
    """Accepts the connection but never answers."""

    def handle(conn: socket.socket, stop: threading.Event) -> None:
        with conn:
            stop.wait(2)

    yield from _serve(handle)


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port: int = s.getsockname()[1]
    s.close()
    return port


def test_plain_http_backend(http_port: int) -> None:
    assert detect_scheme("127.0.0.1", http_port, timeout=2) == "http"


def test_unreachable_backend_is_unknown() -> None:
    assert detect_scheme("127.0.0.1", _closed_port(), timeout=1) is None


def test_silent_backend_is_unknown(silent_port: int) -> None:
    assert detect_scheme("127.0.0.1", silent_port, timeout=0.3) is None


def test_tls_backend_without_cert_verification() -> None:
    ctx = MagicMock()
    with (
        patch("sync.probe.socket.create_connection", return_value=MagicMock()),
        patch("sync.probe.ssl.create_default_context", return_value=ctx),
    ):
        assert detect_scheme("10.0.0.2", 8007) == "https"
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE
