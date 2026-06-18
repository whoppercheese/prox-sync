from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from sync.logger import get_logger

log = get_logger("pihole")


class PiholeClient:
    """Client for the Pi-hole v6 REST API."""

    def __init__(self, base_url: str, password: str) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=30.0,
        )
        self._sid = self._authenticate(password)

    def close(self) -> None:
        self._client.close()

    def _authenticate(self, password: str) -> str:
        resp = self._client.post("/api/auth", json={"password": password})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        session = data.get("session", {})
        sid: str = session.get("sid", "")
        if not sid:
            raise RuntimeError("Pi-hole authentication failed: no SID returned")
        log.info("Authenticated with Pi-hole")
        return sid

    def _headers(self) -> dict[str, str]:
        return {"sid": self._sid}

    def list_records(self) -> list[tuple[str, str]]:
        """Return all custom DNS A records as ``(domain, ip)`` tuples."""
        resp = self._client.get("/api/config/dns/hosts", headers=self._headers())
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        hosts: list[str] = data.get("config", {}).get("dns", {}).get("hosts", [])
        results: list[tuple[str, str]] = []
        for entry in hosts:
            parts = entry.split()
            if len(parts) == 2:
                results.append((parts[1], parts[0]))
        return results

    def list_managed_records(self, domain: str, npm_ip: str) -> list[tuple[str, str]]:
        """Return only records matching ``*.<domain>`` pointing to ``npm_ip``."""
        return [
            (d, ip) for d, ip in self.list_records() if d.endswith(f".{domain}") and ip == npm_ip
        ]

    def create_record(self, domain: str, ip: str) -> None:
        key = quote(f"{ip} {domain}", safe="")
        resp = self._client.put(f"/api/config/dns/hosts/{key}", headers=self._headers())
        resp.raise_for_status()
        log.info("Created DNS record %s → %s", domain, ip)

    def delete_record(self, domain: str, ip: str) -> None:
        key = quote(f"{ip} {domain}", safe="")
        resp = self._client.delete(f"/api/config/dns/hosts/{key}", headers=self._headers())
        resp.raise_for_status()
        log.info("Deleted DNS record %s → %s", domain, ip)
