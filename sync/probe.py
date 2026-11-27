from __future__ import annotations

import socket
import ssl
from typing import Literal

from sync.logger import get_logger

log = get_logger("probe")

Scheme = Literal["http", "https"]


def detect_scheme(host: str, port: int, timeout: float = 3.0) -> Scheme | None:
    """Find out whether a backend speaks HTTPS or plain HTTP.

    Opens a TCP connection and attempts a TLS handshake without verifying the
    certificate (backends such as PBS or Proxmox use self-signed ones).

    Returns ``"https"`` if the handshake succeeds, ``"http"`` if the server
    answers but rejects TLS, and ``None`` if the result is unknown (backend
    unreachable or no answer in time). Callers should keep the current scheme
    when ``None`` is returned, so a restarting container does not flip it.
    """
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        log.debug("Probe %s:%d unreachable: %s", host, port, exc)
        return None

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with ctx.wrap_socket(sock, server_hostname=host):
            return "https"
    except TimeoutError:
        log.debug("Probe %s:%d timed out during TLS handshake", host, port)
        return None
    except (ssl.SSLError, ConnectionError) as exc:
        # Plain HTTP servers answer a ClientHello with garbage or close the
        # connection, both end up here.
        log.debug("Probe %s:%d is not TLS: %s", host, port, exc)
        return "http"
    except OSError as exc:
        log.debug("Probe %s:%d failed: %s", host, port, exc)
        return None
    finally:
        sock.close()
