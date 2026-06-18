from __future__ import annotations

from unittest.mock import MagicMock, patch

from sync.proxmox import ProxmoxClient


class TestProxmoxDiscover:
    @patch("sync.proxmox.httpx.Client")
    def test_uses_vm_filter_and_keeps_only_lxc(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.get.side_effect = [
            MagicMock(
                is_success=True,
                json=lambda: {
                    "data": [
                        {
                            "type": "lxc",
                            "status": "running",
                            "tags": "jellyfin+8096",
                            "vmid": 100,
                            "name": "media",
                            "node": "pve",
                        },
                        {
                            "type": "qemu",
                            "status": "running",
                            "tags": "ignored+80",
                            "vmid": 200,
                            "name": "vm",
                            "node": "pve",
                        },
                    ]
                },
            ),
            MagicMock(
                is_success=True,
                json=lambda: {"data": {"net0": "name=eth0,bridge=vmbr0,ip=10.0.0.10/24"}},
            ),
        ]

        client = ProxmoxClient("https://pve:8006", "user@pve!token", "secret")
        containers = client.discover()

        assert len(containers) == 1
        assert containers[0].vmid == 100
        assert containers[0].ip == "10.0.0.10"
        assert mock_client.get.call_args_list[0].kwargs["params"] == {"type": "vm"}
