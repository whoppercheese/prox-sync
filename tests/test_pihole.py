from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from sync.pihole import PiholeAuthError, PiholeClient


def _auth_response(
    *,
    sid: str = "test-sid",
    csrf: str = "test-csrf",
    valid: bool = True,
    validity: int = 300,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "session": {
                "valid": valid,
                "totp": False,
                "sid": sid,
                "csrf": csrf,
                "validity": validity,
            },
            "took": 0.001,
        },
    )


class TestPiholeAuth:
    @patch("sync.pihole.httpx.Client")
    def test_uses_x_ftl_sid_header(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.post.return_value = _auth_response()

        client = PiholeClient("http://pihole", "app-password")
        headers = client._headers()

        assert headers["X-FTL-SID"] == "test-sid"
        assert headers["X-FTL-CSRF"] == "test-csrf"

    @patch("sync.pihole.httpx.Client")
    def test_rejects_invalid_password_response(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.post.return_value = httpx.Response(
            200,
            json={
                "session": {
                    "valid": True,
                    "totp": False,
                    "sid": None,
                    "validity": -1,
                    "message": "password incorrect",
                },
                "took": 0.001,
            },
        )
        mock_client.get.return_value = httpx.Response(
            200,
            json={"config": {"webserver": {"api": {"pwhash": "set", "app_sudo": False}}}},
        )

        with pytest.raises(PiholeAuthError, match="password incorrect"):
            PiholeClient("http://pihole", "wrong-password")

    @patch("sync.pihole.httpx.Client")
    def test_falls_back_when_pihole_has_no_web_password(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.post.return_value = httpx.Response(
            200,
            json={
                "session": {
                    "valid": True,
                    "totp": False,
                    "sid": None,
                    "validity": -1,
                    "message": "password incorrect",
                },
                "took": 0.001,
            },
        )
        mock_client.get.return_value = httpx.Response(
            200,
            json={"config": {"webserver": {"api": {"pwhash": "", "app_sudo": False}}}},
        )

        client = PiholeClient("http://pihole", "app-password-that-wont-work")
        assert client._headers() == {}

    @patch("sync.pihole.httpx.Client")
    def test_passwordless_mode_without_password(self, mock_client_cls: MagicMock) -> None:
        client = PiholeClient("http://pihole", "")
        assert client._headers() == {}
        mock_client_cls.return_value.post.assert_not_called()

    @patch("sync.pihole.httpx.Client")
    def test_rejects_http_401(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.post.return_value = httpx.Response(
            401,
            json={
                "error": {"key": "unauthorized", "message": "Unauthorized", "hint": None},
                "took": 0.001,
            },
        )

        with pytest.raises(PiholeAuthError, match="Unauthorized"):
            PiholeClient("http://pihole", "wrong-password")
