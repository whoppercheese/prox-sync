from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sync.config import Settings
from sync.engine import sync
from sync.models import DiscoveredContainer
from sync.npm import MANAGED_MARKER
from sync.parser import ConflictError


def _make_settings(**overrides: object) -> Settings:
    defaults = {
        "PROXMOX_URL": "https://pve:8006",
        "PROXMOX_TOKEN_ID": "test@pve!token",
        "PROXMOX_TOKEN_SECRET": "secret",
        "DOMAIN": "example.com",
        "DNS_MODE": "standard",
        "NPM_URL": "http://npm:81",
        "NPM_IP": "192.168.1.1",
        "NPM_USER": "admin@test.com",
        "NPM_PASSWORD": "pass",
        "PIHOLE_URL": "",
        "PIHOLE_PASSWORD": "",
        "ENABLE_SSL": False,
        "DRY_RUN": False,
        "LOG_LEVEL": "WARNING",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestSync:
    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_no_containers(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = []

        result = sync(_make_settings())
        assert result.npm_created == 0
        mock_pve.close.assert_called_once()
        mock_npm_cls.return_value.close.assert_called_once()

    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_creates_new_hosts(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = [
            DiscoveredContainer(
                vmid=100,
                name="media",
                node="pve",
                ip="10.0.0.1",
                tags="jellyfin+8096",
            ),
        ]

        mock_npm = mock_npm_cls.return_value
        mock_npm.list_hosts.return_value = []
        mock_npm.create_host.return_value = {"id": 1}

        result = sync(_make_settings())
        assert result.npm_created == 1
        mock_npm.create_host.assert_called_once_with(
            hostname="jellyfin.example.com",
            forward_host="10.0.0.1",
            forward_port=8096,
            ssl=False,
        )

    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_dry_run_no_apply(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = [
            DiscoveredContainer(
                vmid=100,
                name="media",
                node="pve",
                ip="10.0.0.1",
                tags="jellyfin+8096",
            ),
        ]

        mock_npm = mock_npm_cls.return_value
        mock_npm.list_hosts.return_value = []

        result = sync(_make_settings(DRY_RUN=True))
        assert result.npm_created == 1
        mock_npm.create_host.assert_not_called()

    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_conflict_raises(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = [
            DiscoveredContainer(
                vmid=100, name="ct1", node="pve", ip="10.0.0.1", tags="jellyfin+8096"
            ),
            DiscoveredContainer(
                vmid=101, name="ct2", node="pve", ip="10.0.0.2", tags="jellyfin+8097"
            ),
        ]

        with pytest.raises(ConflictError):
            sync(_make_settings())

    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_deletes_stale_hosts(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = [
            DiscoveredContainer(
                vmid=100,
                name="media",
                node="pve",
                ip="10.0.0.1",
                tags="jellyfin+8096",
            ),
        ]

        mock_npm = mock_npm_cls.return_value
        mock_npm.list_hosts.return_value = [
            {
                "id": 1,
                "domain_names": ["jellyfin.example.com"],
                "forward_host": "10.0.0.1",
                "forward_port": 8096,
                "advanced_config": MANAGED_MARKER,
            },
            {
                "id": 2,
                "domain_names": ["sonarr.example.com"],
                "forward_host": "10.0.0.1",
                "forward_port": 8989,
                "advanced_config": MANAGED_MARKER,
            },
        ]

        result = sync(_make_settings())
        assert result.npm_deleted == 1
        mock_npm.delete_host.assert_called_once_with(2)

    @patch("sync.engine.PiholeClient")
    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_managed_dns_creates_records(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
        mock_pihole_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = [
            DiscoveredContainer(
                vmid=100,
                name="media",
                node="pve",
                ip="10.0.0.1",
                tags="jellyfin+8096",
            ),
        ]

        mock_npm = mock_npm_cls.return_value
        mock_npm.list_hosts.return_value = []
        mock_npm.create_host.return_value = {"id": 1}

        mock_pihole = mock_pihole_cls.return_value
        mock_pihole.list_records.return_value = []

        settings = _make_settings(
            DNS_MODE="managed",
            PIHOLE_URL="http://pihole",
            PIHOLE_PASSWORD="pass",
        )
        result = sync(settings)
        assert result.dns_created == 1
        mock_pihole.create_record.assert_called_once_with("jellyfin.example.com", "192.168.1.1")

    @patch("sync.engine.PiholeClient")
    @patch("sync.engine.NpmClient")
    @patch("sync.engine.ProxmoxClient")
    def test_managed_dns_deletes_only_after_npm_delete(
        self,
        mock_pve_cls: MagicMock,
        mock_npm_cls: MagicMock,
        mock_pihole_cls: MagicMock,
    ) -> None:
        mock_pve = mock_pve_cls.return_value
        mock_pve.discover.return_value = [
            DiscoveredContainer(
                vmid=100,
                name="media",
                node="pve",
                ip="10.0.0.1",
                tags="jellyfin+8096",
            ),
        ]

        mock_npm = mock_npm_cls.return_value
        mock_npm.list_hosts.return_value = [
            {
                "id": 1,
                "domain_names": ["jellyfin.example.com"],
                "forward_host": "10.0.0.1",
                "forward_port": 8096,
                "advanced_config": MANAGED_MARKER,
            },
            {
                "id": 2,
                "domain_names": ["sonarr.example.com"],
                "forward_host": "10.0.0.1",
                "forward_port": 8989,
                "advanced_config": MANAGED_MARKER,
            },
        ]

        mock_pihole = mock_pihole_cls.return_value
        mock_pihole.list_records.return_value = [
            ("jellyfin.example.com", "192.168.1.1"),
            ("sonarr.example.com", "192.168.1.1"),
            ("manual.example.com", "192.168.1.1"),
        ]

        settings = _make_settings(
            DNS_MODE="managed",
            PIHOLE_URL="http://pihole",
            PIHOLE_PASSWORD="pass",
        )
        result = sync(settings)
        assert result.npm_deleted == 1
        mock_npm.delete_host.assert_called_once_with(2)
        mock_pihole.delete_record.assert_called_once_with("sonarr.example.com", "192.168.1.1")
