from __future__ import annotations

from typing import TYPE_CHECKING

from sync.diff import compute_dns_diff, compute_npm_diff

if TYPE_CHECKING:
    from sync.config import Settings
from sync.logger import get_logger
from sync.models import DiffAction, SyncResult
from sync.npm import NpmClient
from sync.parser import build_services
from sync.pihole import PiholeClient
from sync.proxmox import ProxmoxClient

log = get_logger("engine")


def sync(settings: Settings) -> SyncResult:
    """Execute a full synchronisation run.

    Returns a ``SyncResult`` summarising what was done.
    Raises ``ConflictError`` if duplicate service names are detected.
    """
    pve = ProxmoxClient(
        base_url=settings.PROXMOX_URL,
        token_id=settings.PROXMOX_TOKEN_ID,
        token_secret=settings.PROXMOX_TOKEN_SECRET,
    )
    npm = NpmClient(
        base_url=settings.NPM_URL,
        user=settings.NPM_USER,
        password=settings.NPM_PASSWORD,
    )
    pihole: PiholeClient | None = None
    if settings.DNS_MODE == "managed":
        pihole = PiholeClient(
            base_url=settings.PIHOLE_URL,
            password=settings.PIHOLE_PASSWORD,
        )

    try:
        return _run(settings, pve, npm, pihole)
    finally:
        pve.close()
        npm.close()
        if pihole is not None:
            pihole.close()


def _run(
    settings: Settings,
    pve: ProxmoxClient,
    npm: NpmClient,
    pihole: PiholeClient | None,
) -> SyncResult:
    # 1. Discovery
    containers = pve.discover()
    if not containers:
        log.info("No tagged containers found, nothing to do")
        return SyncResult()

    # 2. Parse + conflict check (raises ConflictError on duplicates)
    services = build_services(containers, settings.DOMAIN)

    # 3. Compute NPM diff
    actual_hosts = npm.list_hosts()
    npm_actions = compute_npm_diff(services, actual_hosts)

    # 4. Compute DNS diff (only in managed mode)
    dns_actions = []
    if pihole is not None:
        actual_records = pihole.list_records()
        dns_actions = compute_dns_diff(services, actual_records, settings.NPM_IP, settings.DOMAIN)

    # 5. Log summary
    total = len(npm_actions) + len(dns_actions)
    if total == 0:
        log.info("Everything in sync, no changes needed")
        return SyncResult()

    log.info(
        "Planned changes: %d NPM actions, %d DNS actions",
        len(npm_actions),
        len(dns_actions),
    )

    # 6. Dry run guard
    if settings.DRY_RUN:
        log.info("DRY RUN — no changes applied")
        return SyncResult(
            npm_created=sum(1 for a in npm_actions if a.action == DiffAction.CREATE),
            npm_updated=sum(1 for a in npm_actions if a.action == DiffAction.UPDATE),
            npm_deleted=sum(1 for a in npm_actions if a.action == DiffAction.DELETE),
            dns_created=sum(1 for a in dns_actions if a.action == DiffAction.CREATE),
            dns_deleted=sum(1 for a in dns_actions if a.action == DiffAction.DELETE),
        )

    # 7. Apply NPM changes
    npm_created = npm_updated = npm_deleted = 0
    for action in npm_actions:
        if action.action == DiffAction.CREATE:
            assert action.forward_host is not None
            assert action.forward_port is not None
            npm.create_host(
                hostname=action.hostname,
                forward_host=action.forward_host,
                forward_port=action.forward_port,
                ssl=settings.ENABLE_SSL,
            )
            npm_created += 1
        elif action.action == DiffAction.UPDATE:
            assert action.npm_host_id is not None
            assert action.forward_host is not None
            assert action.forward_port is not None
            npm.update_host(
                host_id=action.npm_host_id,
                hostname=action.hostname,
                forward_host=action.forward_host,
                forward_port=action.forward_port,
                ssl=settings.ENABLE_SSL,
            )
            npm_updated += 1
        elif action.action == DiffAction.DELETE:
            assert action.npm_host_id is not None
            npm.delete_host(action.npm_host_id)
            npm_deleted += 1

    # 8. Apply DNS changes
    dns_created = dns_deleted = 0
    if pihole is not None:
        for action in dns_actions:
            if action.action == DiffAction.CREATE:
                pihole.create_record(action.domain, action.ip)
                dns_created += 1
            elif action.action == DiffAction.DELETE:
                pihole.delete_record(action.domain, action.ip)
                dns_deleted += 1

    result = SyncResult(
        npm_created=npm_created,
        npm_updated=npm_updated,
        npm_deleted=npm_deleted,
        dns_created=dns_created,
        dns_deleted=dns_deleted,
    )
    log.info(
        "Sync complete: NPM(+%d ~%d -%d) DNS(+%d -%d)",
        result.npm_created,
        result.npm_updated,
        result.npm_deleted,
        result.dns_created,
        result.dns_deleted,
    )
    return result
