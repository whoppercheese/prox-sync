from __future__ import annotations

from typing import Any

from sync.logger import get_logger
from sync.models import DiffAction, DnsRecordDiff, ProxyHostDiff, Service
from sync.npm import MANAGED_MARKER

log = get_logger("diff")


def _host_domain(host: dict[str, Any]) -> str:
    """Extract the primary domain name from an NPM proxy host record."""
    names: list[str] = host.get("domain_names", [])
    return names[0] if names else ""


def _is_managed(host: dict[str, Any]) -> bool:
    return MANAGED_MARKER in (host.get("advanced_config") or "")


def compute_npm_diff(
    desired: list[Service],
    actual_hosts: list[dict[str, Any]],
) -> list[ProxyHostDiff]:
    """Compare desired services against existing NPM proxy hosts.

    Returns a list of create / update / delete actions.
    """
    desired_by_hostname = {svc.hostname: svc for svc in desired}

    managed_by_hostname: dict[str, dict[str, Any]] = {}
    for host in actual_hosts:
        if _is_managed(host):
            managed_by_hostname[_host_domain(host)] = host

    actions: list[ProxyHostDiff] = []

    for hostname, svc in desired_by_hostname.items():
        existing = managed_by_hostname.pop(hostname, None)
        if existing is None:
            actions.append(
                ProxyHostDiff(
                    action=DiffAction.CREATE,
                    hostname=hostname,
                    forward_host=svc.container_ip,
                    forward_port=svc.port,
                )
            )
            log.info("Plan CREATE proxy host %s → %s:%d", hostname, svc.container_ip, svc.port)
        else:
            host_id = int(existing["id"])
            ip_changed = existing.get("forward_host") != svc.container_ip
            port_changed = existing.get("forward_port") != svc.port
            if ip_changed or port_changed:
                actions.append(
                    ProxyHostDiff(
                        action=DiffAction.UPDATE,
                        hostname=hostname,
                        forward_host=svc.container_ip,
                        forward_port=svc.port,
                        npm_host_id=host_id,
                    )
                )
                log.info(
                    "Plan UPDATE proxy host %d (%s) → %s:%d",
                    host_id,
                    hostname,
                    svc.container_ip,
                    svc.port,
                )

    for hostname, host in managed_by_hostname.items():
        host_id = int(host["id"])
        actions.append(
            ProxyHostDiff(
                action=DiffAction.DELETE,
                hostname=hostname,
                npm_host_id=host_id,
            )
        )
        log.info("Plan DELETE proxy host %d (%s)", host_id, hostname)

    return actions


def compute_dns_creates(
    desired: list[Service],
    actual_records: list[tuple[str, str]],
    npm_ip: str,
    domain: str,
) -> list[DnsRecordDiff]:
    """Plan DNS record creates for desired services that are missing in Pi-hole."""
    desired_domains = {svc.hostname for svc in desired}
    existing_matching = {
        d for d, ip in actual_records if d.endswith(f".{domain}") and ip == npm_ip
    }

    actions: list[DnsRecordDiff] = []
    for d in desired_domains - existing_matching:
        actions.append(DnsRecordDiff(action=DiffAction.CREATE, domain=d, ip=npm_ip))
        log.info("Plan CREATE DNS record %s → %s", d, npm_ip)
    return actions


def compute_dns_deletes(
    deleted_npm_hostnames: set[str],
    actual_records: list[tuple[str, str]],
) -> list[DnsRecordDiff]:
    """Plan DNS deletes only for hostnames removed from NPM in this sync run."""
    records_by_domain = dict(actual_records)
    actions: list[DnsRecordDiff] = []

    for hostname in sorted(deleted_npm_hostnames):
        ip = records_by_domain.get(hostname)
        if ip is None:
            continue
        actions.append(DnsRecordDiff(action=DiffAction.DELETE, domain=hostname, ip=ip))
        log.info("Plan DELETE DNS record %s → %s", hostname, ip)

    return actions
