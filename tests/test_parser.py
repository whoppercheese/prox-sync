from __future__ import annotations

import pytest

from sync.models import DiscoveredContainer
from sync.parser import ConflictError, build_services, parse_tags


class TestParseTags:
    def test_valid_single(self) -> None:
        assert parse_tags("jellyfin+8096") == [("jellyfin", 8096)]

    def test_valid_multiple(self) -> None:
        result = parse_tags("jellyfin+8096;grafana+3000;sonarr+8989")
        assert result == [("jellyfin", 8096), ("grafana", 3000), ("sonarr", 8989)]

    def test_ignores_invalid_tags(self) -> None:
        result = parse_tags("jellyfin+8096;not-a-service;grafana+3000;uppercase+ABC")
        assert result == [("jellyfin", 8096), ("grafana", 3000)]

    def test_ignores_empty_string(self) -> None:
        assert parse_tags("") == []

    def test_ignores_tags_without_port(self) -> None:
        assert parse_tags("myservice") == []

    def test_ignores_tags_with_invalid_name(self) -> None:
        assert parse_tags("123abc+80") == []
        assert parse_tags("ABC+80") == []

    def test_hyphenated_name(self) -> None:
        assert parse_tags("my-service+9000") == [("my-service", 9000)]

    def test_strips_whitespace(self) -> None:
        result = parse_tags(" jellyfin+8096 ; grafana+3000 ")
        assert result == [("jellyfin", 8096), ("grafana", 3000)]

    def test_semicolon_only(self) -> None:
        assert parse_tags(";;;") == []


class TestBuildServices:
    def test_builds_services(self, sample_containers: list[DiscoveredContainer]) -> None:
        services = build_services(sample_containers, "example.com")
        assert len(services) == 3
        hostnames = {s.hostname for s in services}
        assert hostnames == {
            "jellyfin.example.com",
            "sonarr.example.com",
            "grafana.example.com",
        }

    def test_conflict_raises(self) -> None:
        containers = [
            DiscoveredContainer(
                vmid=100, name="ct1", node="pve", ip="10.0.0.1", tags="jellyfin+8096"
            ),
            DiscoveredContainer(
                vmid=101, name="ct2", node="pve", ip="10.0.0.2", tags="jellyfin+8097"
            ),
        ]
        with pytest.raises(ConflictError) as exc_info:
            build_services(containers, "example.com")
        assert "jellyfin" in str(exc_info.value)
        assert exc_info.value.conflicts["jellyfin"] == [(100, 8096), (101, 8097)]

    def test_no_services(self) -> None:
        containers = [
            DiscoveredContainer(
                vmid=100, name="ct1", node="pve", ip="10.0.0.1", tags="no-valid-tag"
            ),
        ]
        services = build_services(containers, "example.com")
        assert services == []

    def test_empty_containers(self) -> None:
        services = build_services([], "example.com")
        assert services == []
