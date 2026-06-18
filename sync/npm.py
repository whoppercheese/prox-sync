from __future__ import annotations

from typing import Any

import httpx

from sync.logger import get_logger

log = get_logger("npm")

MANAGED_MARKER = "# prox-sync:managed"


class NpmClient:
    """Client for the Nginx Proxy Manager REST API."""

    def __init__(self, base_url: str, user: str, password: str) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=60.0,
        )
        self._token = self._authenticate(user, password)
        self._client.headers["Authorization"] = f"Bearer {self._token}"

    def close(self) -> None:
        self._client.close()

    def _authenticate(self, user: str, password: str) -> str:
        resp = self._client.post("/api/tokens", json={"identity": user, "secret": password})
        resp.raise_for_status()
        token: str = resp.json()["token"]
        log.info("Authenticated with NPM")
        return token

    def list_hosts(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/nginx/proxy-hosts")
        resp.raise_for_status()
        hosts: list[dict[str, Any]] = resp.json()
        return hosts

    def list_managed_hosts(self) -> list[dict[str, Any]]:
        """Return only proxy hosts that were created by prox-sync."""
        return [h for h in self.list_hosts() if MANAGED_MARKER in (h.get("advanced_config") or "")]

    def create_host(
        self,
        hostname: str,
        forward_host: str,
        forward_port: int,
        *,
        ssl: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "domain_names": [hostname],
            "forward_scheme": "http",
            "forward_host": forward_host,
            "forward_port": forward_port,
            "allow_websocket_upgrade": True,
            "block_exploits": True,
            "access_list_id": 0,
            "advanced_config": MANAGED_MARKER,
            "meta": {"prox_sync": True},
            "locations": [],
        }

        if ssl:
            payload.update(
                {
                    "certificate_id": "new",
                    "ssl_forced": True,
                    "hsts_enabled": True,
                    "hsts_subdomains": False,
                    "http2_support": True,
                }
            )
        else:
            payload.update(
                {
                    "certificate_id": 0,
                    "ssl_forced": False,
                    "hsts_enabled": False,
                    "hsts_subdomains": False,
                    "http2_support": False,
                }
            )

        resp = self._client.post("/api/nginx/proxy-hosts", json=payload)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        log.info("Created proxy host for %s → %s:%d", hostname, forward_host, forward_port)
        return result

    def update_host(
        self,
        host_id: int,
        hostname: str,
        forward_host: str,
        forward_port: int,
        *,
        ssl: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "domain_names": [hostname],
            "forward_scheme": "http",
            "forward_host": forward_host,
            "forward_port": forward_port,
            "allow_websocket_upgrade": True,
            "block_exploits": True,
            "access_list_id": 0,
            "advanced_config": MANAGED_MARKER,
            "meta": {"prox_sync": True},
            "locations": [],
        }

        if ssl:
            payload.update(
                {
                    "certificate_id": "new",
                    "ssl_forced": True,
                    "hsts_enabled": True,
                    "hsts_subdomains": False,
                    "http2_support": True,
                }
            )
        else:
            payload.update(
                {
                    "certificate_id": 0,
                    "ssl_forced": False,
                    "hsts_enabled": False,
                    "hsts_subdomains": False,
                    "http2_support": False,
                }
            )

        resp = self._client.put(f"/api/nginx/proxy-hosts/{host_id}", json=payload)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        log.info(
            "Updated proxy host %d for %s → %s:%d",
            host_id,
            hostname,
            forward_host,
            forward_port,
        )
        return result

    def delete_host(self, host_id: int) -> None:
        resp = self._client.delete(f"/api/nginx/proxy-hosts/{host_id}")
        resp.raise_for_status()
        log.info("Deleted proxy host %d", host_id)
