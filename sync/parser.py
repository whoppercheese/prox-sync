from __future__ import annotations

import re

from sync.logger import get_logger
from sync.models import DiscoveredContainer, Service

log = get_logger("parser")

_SERVICE_TAG_RE = re.compile(r"^([a-z][a-z0-9-]*)\+(\d+)$")


class ConflictError(Exception):
    """Raised when multiple containers claim the same service name."""

    def __init__(self, conflicts: dict[str, list[tuple[int, int]]]) -> None:
        self.conflicts = conflicts
        lines = []
        for svc, owners in sorted(conflicts.items()):
            entries = ", ".join(f"CT {vmid} (port {port})" for vmid, port in owners)
            lines.append(f"  {svc}: {entries}")
        msg = "Service name conflict detected:\n" + "\n".join(lines)
        super().__init__(msg)


def parse_tags(raw: str) -> list[tuple[str, int]]:
    """Parse a Proxmox tag string into valid ``(service_name, port)`` pairs.

    Tags are semicolon-separated.  Only tags matching ``<name>+<port>`` are
    returned; all others are silently ignored.
    """
    results: list[tuple[str, int]] = []
    for tag in raw.split(";"):
        tag = tag.strip()
        match = _SERVICE_TAG_RE.match(tag)
        if match:
            results.append((match.group(1), int(match.group(2))))
    return results


def build_services(
    containers: list[DiscoveredContainer],
    domain: str,
) -> list[Service]:
    """Convert discovered containers into a flat list of services.

    Raises ``ConflictError`` if two or more containers define the same
    service name.
    """
    seen: dict[str, list[tuple[int, int]]] = {}
    services: list[Service] = []

    for ct in containers:
        for svc_name, port in parse_tags(ct.tags):
            seen.setdefault(svc_name, []).append((ct.vmid, port))
            services.append(
                Service(
                    name=svc_name,
                    port=port,
                    container_ip=ct.ip,
                    vmid=ct.vmid,
                    hostname=f"{svc_name}.{domain}",
                )
            )

    conflicts = {name: owners for name, owners in seen.items() if len(owners) > 1}
    if conflicts:
        for name, owners in conflicts.items():
            log.error(
                "Conflict: service '%s' defined by multiple containers: %s",
                name,
                owners,
            )
        raise ConflictError(conflicts)

    log.info("Parsed %d services from %d containers", len(services), len(containers))
    return services
