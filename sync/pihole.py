from __future__ import annotations

from contextlib import suppress
from typing import Any
from urllib.parse import quote

import httpx

from sync.logger import get_logger

log = get_logger("pihole")


class PiholeAuthError(RuntimeError):
    """Raised when Pi-hole rejects the provided password or app password."""


class PiholeClient:
    """Client for the Pi-hole v6 REST API."""

    def __init__(self, base_url: str, password: str) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=30.0,
            verify=False,
        )
        self._sid: str | None = None
        self._csrf: str | None = None

        if password:
            try:
                self._sid, self._csrf = self._authenticate(password)
            except PiholeAuthError as exc:
                if self._is_passwordless_pihole():
                    log.warning(
                        "Pi-hole app/web password auth failed but the instance has no "
                        "web password set; continuing without authentication"
                    )
                else:
                    raise PiholeAuthError(f"{exc}\n{self._auth_failure_hint()}") from exc
        else:
            log.info("Pi-hole password not set, using unauthenticated API")

    def close(self) -> None:
        if self._sid:
            with suppress(httpx.HTTPError):
                self._client.delete("/api/auth", headers=self._headers())
        self._client.close()

    def _fetch_api_config(self) -> dict[str, Any] | None:
        try:
            resp = self._client.get("/api/config/webserver/api")
            if not resp.is_success:
                return None
            data: dict[str, Any] = resp.json()
            api_cfg = data.get("config", {}).get("webserver", {}).get("api")
            if isinstance(api_cfg, dict):
                return api_cfg
        except (httpx.HTTPError, ValueError):
            return None
        return None

    def _is_passwordless_pihole(self) -> bool:
        """Return True when Pi-hole has no web interface password configured."""
        api_cfg = self._fetch_api_config()
        return api_cfg is not None and api_cfg.get("pwhash") == ""

    def _auth_failure_hint(self) -> str:
        hints = [
            "Hints:",
            "- App passwords only work when a web interface password is set in Pi-hole.",
            "- If Pi-hole has no web password, leave PIHOLE_PASSWORD empty in .env.",
            "- Regenerate the app password after setting the web password.",
        ]
        api_cfg = self._fetch_api_config()
        if api_cfg is not None:
            if api_cfg.get("pwhash") == "":
                hints.append("- Detected: web password is NOT set (pwhash is empty).")
            if not api_cfg.get("app_sudo"):
                hints.append(
                    "- Detected: app_sudo is disabled. Enable with: "
                    "sudo pihole-FTL --config webserver.api.app_sudo true"
                )
        return "\n".join(hints)

    def _authenticate(self, password: str) -> tuple[str, str | None]:
        resp = self._client.post("/api/auth", json={"password": password})

        try:
            data: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise PiholeAuthError(
                f"Pi-hole authentication failed: invalid JSON response (HTTP {resp.status_code})"
            ) from exc

        session = data.get("session", {})
        if resp.status_code == 401:
            message = session.get("message") or data.get("error", {}).get("message", "Unauthorized")
            raise PiholeAuthError(f"Pi-hole authentication failed: {message}")

        if resp.status_code == 429:
            message = data.get("error", {}).get("message", "Rate limit exceeded")
            raise PiholeAuthError(f"Pi-hole authentication failed: {message}")

        if not resp.is_success:
            message = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            raise PiholeAuthError(f"Pi-hole authentication failed: {message}")

        sid = session.get("sid")
        if not session.get("valid") or not sid or session.get("validity", 0) <= 0:
            message = session.get("message", "no SID returned")
            raise PiholeAuthError(f"Pi-hole authentication failed: {message}")

        csrf: str | None = session.get("csrf")
        log.info("Authenticated with Pi-hole")
        return str(sid), csrf

    def _headers(self) -> dict[str, str]:
        if not self._sid:
            return {}
        headers = {"X-FTL-SID": self._sid}
        if self._csrf:
            headers["X-FTL-CSRF"] = self._csrf
        return headers

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
