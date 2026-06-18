from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class DiscoveredContainer:
    """Raw container data from Proxmox discovery."""

    vmid: int
    name: str
    node: str
    ip: str
    tags: str


@dataclass(frozen=True)
class Service:
    """A resolved service derived from a container tag."""

    name: str
    port: int
    container_ip: str
    vmid: int
    hostname: str


class DiffAction(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class ProxyHostDiff:
    """A single change to apply to NPM."""

    action: DiffAction
    hostname: str
    forward_host: str | None = None
    forward_port: int | None = None
    npm_host_id: int | None = None


@dataclass(frozen=True)
class DnsRecordDiff:
    """A single change to apply to Pi-hole DNS."""

    action: DiffAction
    domain: str
    ip: str


@dataclass(frozen=True)
class SyncResult:
    """Summary of a sync run."""

    npm_created: int = 0
    npm_updated: int = 0
    npm_deleted: int = 0
    dns_created: int = 0
    dns_deleted: int = 0
