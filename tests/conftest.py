from __future__ import annotations

import pytest

from sync.models import DiscoveredContainer, Service


@pytest.fixture
def sample_containers() -> list[DiscoveredContainer]:
    return [
        DiscoveredContainer(
            vmid=100,
            name="media",
            node="pve",
            ip="192.168.178.100",
            tags="jellyfin+8096;sonarr+8989",
        ),
        DiscoveredContainer(
            vmid=101,
            name="monitoring",
            node="pve",
            ip="192.168.178.101",
            tags="grafana+3000",
        ),
    ]


@pytest.fixture
def sample_services() -> list[Service]:
    return [
        Service(
            name="jellyfin",
            port=8096,
            container_ip="192.168.178.100",
            vmid=100,
            hostname="jellyfin.example.com",
        ),
        Service(
            name="sonarr",
            port=8989,
            container_ip="192.168.178.100",
            vmid=100,
            hostname="sonarr.example.com",
        ),
        Service(
            name="grafana",
            port=3000,
            container_ip="192.168.178.101",
            vmid=101,
            hostname="grafana.example.com",
        ),
    ]
