from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("/etc/prox-sync/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    PROXMOX_URL: str = Field(description="Proxmox VE API URL, e.g. https://192.168.178.2:8006")
    PROXMOX_TOKEN_ID: str = Field(description="API token ID, e.g. sync@pve!sync-token")
    PROXMOX_TOKEN_SECRET: str = Field(description="API token secret (UUID)")

    DOMAIN: str = Field(description="Base domain for service hostnames, e.g. myhome.net")

    DNS_MODE: Literal["managed", "standard"] = Field(
        default="standard",
        description="'managed' syncs Pi-hole DNS records; 'standard' assumes wildcard DNS",
    )

    NPM_URL: str = Field(description="Nginx Proxy Manager API URL, e.g. http://192.168.178.164:81")
    NPM_IP: str = Field(description="NPM host IP that DNS records should point to")
    NPM_USER: str = Field(description="NPM login email")
    NPM_PASSWORD: str = Field(description="NPM login password")

    PIHOLE_URL: str = Field(
        default="",
        description="Pi-hole base URL without /admin suffix (required if DNS_MODE=managed)",
    )
    PIHOLE_PASSWORD: str = Field(
        default="",
        description="Pi-hole web password or app password (required if DNS_MODE=managed)",
    )

    ENABLE_SSL: bool = Field(
        default=False,
        description="Provision Let's Encrypt certificates and force HTTPS",
    )
    DRY_RUN: bool = Field(default=False, description="Log planned changes without applying them")

    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
