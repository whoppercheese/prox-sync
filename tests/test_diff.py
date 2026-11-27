from __future__ import annotations

from typing import Literal

from sync.diff import compute_dns_creates, compute_dns_deletes, compute_npm_diff
from sync.models import DiffAction, Service
from sync.npm import MANAGED_MARKER


def _npm_host(
    host_id: int,
    hostname: str,
    forward_host: str,
    forward_port: int,
    managed: bool = True,
    forward_scheme: str = "http",
) -> dict[str, object]:
    return {
        "id": host_id,
        "domain_names": [hostname],
        "forward_scheme": forward_scheme,
        "forward_host": forward_host,
        "forward_port": forward_port,
        "advanced_config": MANAGED_MARKER if managed else "",
    }


def _svc(
    name: str,
    port: int,
    ip: str,
    domain: str = "example.com",
    scheme: Literal["http", "https"] | None = None,
) -> Service:
    return Service(
        name=name,
        port=port,
        container_ip=ip,
        vmid=100,
        hostname=f"{name}.{domain}",
        scheme=scheme,
    )


class TestComputeNpmDiff:
    def test_create_new_host(self) -> None:
        desired = [_svc("jellyfin", 8096, "10.0.0.1")]
        actions = compute_npm_diff(desired, [])
        assert len(actions) == 1
        assert actions[0].action == DiffAction.CREATE
        assert actions[0].hostname == "jellyfin.example.com"
        assert actions[0].forward_host == "10.0.0.1"
        assert actions[0].forward_port == 8096

    def test_no_change(self) -> None:
        desired = [_svc("jellyfin", 8096, "10.0.0.1")]
        actual = [_npm_host(1, "jellyfin.example.com", "10.0.0.1", 8096)]
        actions = compute_npm_diff(desired, actual)
        assert actions == []

    def test_update_ip(self) -> None:
        desired = [_svc("jellyfin", 8096, "10.0.0.2")]
        actual = [_npm_host(1, "jellyfin.example.com", "10.0.0.1", 8096)]
        actions = compute_npm_diff(desired, actual)
        assert len(actions) == 1
        assert actions[0].action == DiffAction.UPDATE
        assert actions[0].npm_host_id == 1
        assert actions[0].forward_host == "10.0.0.2"

    def test_update_port(self) -> None:
        desired = [_svc("jellyfin", 9000, "10.0.0.1")]
        actual = [_npm_host(1, "jellyfin.example.com", "10.0.0.1", 8096)]
        actions = compute_npm_diff(desired, actual)
        assert len(actions) == 1
        assert actions[0].action == DiffAction.UPDATE
        assert actions[0].forward_port == 9000

    def test_delete_removed_service(self) -> None:
        actual = [_npm_host(1, "jellyfin.example.com", "10.0.0.1", 8096)]
        actions = compute_npm_diff([], actual)
        assert len(actions) == 1
        assert actions[0].action == DiffAction.DELETE
        assert actions[0].npm_host_id == 1

    def test_ignores_unmanaged_hosts(self) -> None:
        actual = [_npm_host(1, "manual.example.com", "10.0.0.1", 80, managed=False)]
        actions = compute_npm_diff([], actual)
        assert actions == []

    def test_mixed_operations(self) -> None:
        desired = [
            _svc("jellyfin", 8096, "10.0.0.1"),
            _svc("grafana", 3000, "10.0.0.2"),
        ]
        actual = [
            _npm_host(1, "jellyfin.example.com", "10.0.0.1", 8096),
            _npm_host(2, "sonarr.example.com", "10.0.0.1", 8989),
        ]
        actions = compute_npm_diff(desired, actual)
        action_map = {a.hostname: a.action for a in actions}
        assert action_map == {
            "grafana.example.com": DiffAction.CREATE,
            "sonarr.example.com": DiffAction.DELETE,
        }


class TestSchemeDiff:
    def test_create_uses_detected_https(self) -> None:
        actions = compute_npm_diff([_svc("pbs", 8007, "10.0.0.2", scheme="https")], [])
        assert actions[0].action == DiffAction.CREATE
        assert actions[0].forward_scheme == "https"

    def test_create_defaults_to_http_when_unknown(self) -> None:
        actions = compute_npm_diff([_svc("pbs", 8007, "10.0.0.2")], [])
        assert actions[0].forward_scheme == "http"

    def test_update_when_scheme_differs(self) -> None:
        desired = [_svc("pbs", 8007, "10.0.0.2", scheme="https")]
        actual = [_npm_host(1, "pbs.example.com", "10.0.0.2", 8007)]
        actions = compute_npm_diff(desired, actual)
        assert len(actions) == 1
        assert actions[0].action == DiffAction.UPDATE
        assert actions[0].forward_scheme == "https"

    def test_no_change_when_scheme_matches(self) -> None:
        desired = [_svc("pbs", 8007, "10.0.0.2", scheme="https")]
        actual = [_npm_host(1, "pbs.example.com", "10.0.0.2", 8007, forward_scheme="https")]
        assert compute_npm_diff(desired, actual) == []

    def test_unknown_scheme_keeps_current(self) -> None:
        desired = [_svc("pbs", 8007, "10.0.0.2")]
        actual = [_npm_host(1, "pbs.example.com", "10.0.0.2", 8007, forward_scheme="https")]
        assert compute_npm_diff(desired, actual) == []

    def test_ip_change_keeps_https_when_unknown(self) -> None:
        # Regression: an IP/port update used to reset the scheme to http
        desired = [_svc("pbs", 8007, "10.0.0.9")]
        actual = [_npm_host(1, "pbs.example.com", "10.0.0.2", 8007, forward_scheme="https")]
        actions = compute_npm_diff(desired, actual)
        assert actions[0].action == DiffAction.UPDATE
        assert actions[0].forward_scheme == "https"


class TestComputeDnsCreates:
    def test_create_record(self) -> None:
        desired = [_svc("jellyfin", 8096, "10.0.0.1")]
        actions = compute_dns_creates(desired, [], "192.168.1.1", "example.com")
        assert len(actions) == 1
        assert actions[0].action == DiffAction.CREATE
        assert actions[0].domain == "jellyfin.example.com"

    def test_no_change(self) -> None:
        desired = [_svc("jellyfin", 8096, "10.0.0.1")]
        actual = [("jellyfin.example.com", "192.168.1.1")]
        actions = compute_dns_creates(desired, actual, "192.168.1.1", "example.com")
        assert actions == []


class TestComputeDnsDeletes:
    def test_delete_after_npm_removal(self) -> None:
        actual = [("jellyfin.example.com", "192.168.1.1")]
        actions = compute_dns_deletes({"jellyfin.example.com"}, actual)
        assert len(actions) == 1
        assert actions[0].action == DiffAction.DELETE
        assert actions[0].domain == "jellyfin.example.com"
        assert actions[0].ip == "192.168.1.1"

    def test_skips_when_no_dns_record(self) -> None:
        actions = compute_dns_deletes({"jellyfin.example.com"}, [])
        assert actions == []

    def test_keeps_manual_dns_when_npm_not_deleted(self) -> None:
        actual = [("manual.example.com", "192.168.1.1")]
        actions = compute_dns_deletes(set(), actual)
        assert actions == []
