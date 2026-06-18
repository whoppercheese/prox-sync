from __future__ import annotations

import re

import httpx

from sync.logger import get_logger
from sync.models import DiscoveredContainer

log = get_logger("proxmox")

_NET_IP_RE = re.compile(r"ip=(\d+\.\d+\.\d+\.\d+)/\d+")


class ProxmoxClient:
    """Thin client around the Proxmox VE REST API."""

    def __init__(self, base_url: str, token_id: str, token_secret: str) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"PVEAPIToken={token_id}={token_secret}"},
            verify=False,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, **params: str) -> list[dict[str, object]]:
        resp = self._client.get(f"/api2/json{path}", params=params)
        if not resp.is_success:
            detail = self._error_detail(resp)
            raise httpx.HTTPStatusError(
                detail,
                request=resp.request,
                response=resp,
            )
        data: list[dict[str, object]] = resp.json()["data"]
        return data

    @staticmethod
    def _error_detail(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            errors = body.get("errors")
            if errors:
                return f"{resp.status_code} {resp.reason_phrase}: {errors}"
        except ValueError:
            pass
        return f"{resp.status_code} {resp.reason_phrase} for {resp.request.url}"

    def discover(self) -> list[DiscoveredContainer]:
        """List all running LXC containers that have tags and a resolvable IP."""
        # Proxmox accepts type=vm here (not type=lxc); filter response items by type.
        resources = self._get("/cluster/resources", type="vm")
        containers: list[DiscoveredContainer] = []

        for res in resources:
            if str(res.get("type", "")) != "lxc":
                continue

            status = str(res.get("status", ""))
            if status != "running":
                continue

            tags = str(res.get("tags", ""))
            if not tags:
                continue

            vmid = int(res["vmid"])  # type: ignore[arg-type]
            name = str(res.get("name", ""))
            node = str(res.get("node", ""))

            ip = self._resolve_ip(node, vmid)
            if not ip:
                log.warning("Container %d (%s) has no resolvable IP, skipping", vmid, name)
                continue

            containers.append(
                DiscoveredContainer(vmid=vmid, name=name, node=node, ip=ip, tags=tags)
            )

        log.info("Discovered %d tagged containers", len(containers))
        return containers

    def _resolve_ip(self, node: str, vmid: int) -> str | None:
        """Try static IP from config first, fall back to interfaces endpoint."""
        ip = self._ip_from_config(node, vmid)
        if ip:
            return ip
        return self._ip_from_interfaces(node, vmid)

    def _ip_from_config(self, node: str, vmid: int) -> str | None:
        """Parse the static IP from net0..netN config keys."""
        resp = self._client.get(f"/api2/json/nodes/{node}/lxc/{vmid}/config")
        resp.raise_for_status()
        config: dict[str, object] = resp.json()["data"]

        for key in sorted(config):
            if not key.startswith("net"):
                continue
            match = _NET_IP_RE.search(str(config[key]))
            if match:
                return match.group(1)
        return None

    def _ip_from_interfaces(self, node: str, vmid: int) -> str | None:
        """Get the IP from the container's live network interfaces."""
        try:
            resp = self._client.get(f"/api2/json/nodes/{node}/lxc/{vmid}/interfaces")
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return None

        interfaces: list[dict[str, object]] = resp.json()["data"]
        for iface in interfaces:
            if str(iface.get("name", "")) == "lo":
                continue
            inet = str(iface.get("inet", ""))
            if inet:
                return inet.split("/")[0]
        return None
