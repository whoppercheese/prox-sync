# prox-sync

Synchronises Proxmox LXC container services (defined via tags) to **Pi-hole** DNS records and **Nginx Proxy Manager** reverse proxy hosts.

Proxmox is the single source of truth. Tag a container, and DNS + reverse proxy entries are created, updated or removed automatically.

## How it works

1. **Discovery** — queries the Proxmox API for all running LXC containers with tags.
2. **Parsing** — extracts valid `<service>+<port>` tags (e.g. `jellyfin+8096`).
3. **Diff** — compares desired state against the current NPM proxy hosts (and optionally Pi-hole DNS records).
4. **Apply** — creates, updates or deletes resources to reach the desired state.

Every run is fully **idempotent** and **declarative**.

## Tag syntax

Add tags to your LXC containers in Proxmox:

```
jellyfin+8096
grafana+3000
paperless+8000
```

Proxmox does not allow `:` in tags, so `+` is used as the separator.

A container can have multiple service tags (semicolon-separated in Proxmox).

Each tag produces:

| | Value |
|---|---|
| Hostname | `<service>.<DOMAIN>` |
| Target | `<container-ip>:<port>` |

## DNS modes

### `standard` (recommended)

Pi-hole is not managed. A wildcard DNS entry is assumed:

```
*.myhome.net → NPM_IP
```

Only NPM proxy hosts are synced.

### `managed`

prox-sync creates and deletes individual Pi-hole DNS records:

```
jellyfin.myhome.net → NPM_IP
```

## Quick start (Proxmox LXC)

The fastest way to deploy is a small Debian/Ubuntu LXC in Proxmox.

### 1. Create the LXC

In the Proxmox UI (or CLI):

- Template: `debian-12-standard` or `ubuntu-24.04-standard`
- Resources: 1 core, 256 MB RAM, 2 GB disk is plenty
- Network: DHCP or static — must be able to reach Proxmox API, NPM and Pi-hole

### 2. Prepare the Proxmox API token

Run this on your **Proxmox host** (not inside the LXC):

```bash
pveum user add sync@pve
pveum aclmod / -user sync@pve -role PVEAuditor
pveum user token add sync@pve sync-token --privsep 0
```

Save the token secret — you'll need it in the next step.

### 3. Run the setup script

SSH into the LXC and run:

```bash
apt-get update && apt-get install -y curl
curl -fsSL https://raw.githubusercontent.com/whoppercheese/prox-sync/main/setup.sh | bash
```

Or clone first if you prefer to review:

```bash
git clone https://github.com/whoppercheese/prox-sync.git /opt/prox-sync
bash /opt/prox-sync/setup.sh
```

The script installs all dependencies, creates a venv, copies the systemd timer and generates the config at `/etc/prox-sync/.env`.

### 4. Configure

```bash
nano /etc/prox-sync/.env
```

Fill in your values:

| Variable | Description |
|---|---|
| `PROXMOX_URL` | Proxmox API URL (e.g. `https://192.168.178.2:8006`) |
| `PROXMOX_TOKEN_ID` | API token ID (`sync@pve!sync-token`) |
| `PROXMOX_TOKEN_SECRET` | API token secret from step 2 |
| `DOMAIN` | Base domain (e.g. `myhome.net`) |
| `DNS_MODE` | `standard` (wildcard DNS) or `managed` (Pi-hole per-record) |
| `NPM_URL` | NPM admin URL (e.g. `http://192.168.178.164:81`) |
| `NPM_IP` | NPM host IP for DNS records |
| `NPM_USER` | NPM login email |
| `NPM_PASSWORD` | NPM login password |
| `PIHOLE_URL` | Pi-hole base URL (e.g. `http://192.168.178.10` or `https://pi.hole`) |
| `PIHOLE_PASSWORD` | Web password or app password (see Pi-hole setup below) |
| `ENABLE_SSL` | `true` to auto-provision Let's Encrypt |
| `DRY_RUN` | `true` to preview without applying |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### 5. Start

```bash
# Test with a dry run first
DRY_RUN=true /opt/prox-sync/.venv/bin/python -m sync.main

# Start the timer (runs every 5 minutes)
systemctl start proxmox-sync.timer
```

Done. From now on, tag your LXC containers in Proxmox and everything else happens automatically.

### Pi-hole setup (`DNS_MODE=managed`)

**Option A — no web password (simplest homelab setup)**

If your Pi-hole has no web interface password, leave `PIHOLE_PASSWORD` empty in `.env`. The API works without authentication.

**Option B — app password (recommended for secured Pi-hole)**

1. Set a **web interface password** in Pi-hole (Settings > Web interface). App passwords do **not** work without one.
2. Generate an **app password** in Settings > API > App password.
3. Enable write access for app-password sessions:

```bash
sudo pihole-FTL --config webserver.api.app_sudo true
```

4. Test authentication from the sync LXC:

```bash
curl -s -X POST "http://YOUR_PIHOLE/api/auth" \
  -H "Content-Type: application/json" \
  -d '{"password":"YOUR_APP_PASSWORD"}' | jq
```

A successful response contains `"valid": true`, a non-null `"sid"`, and `"validity" > 0`. Use the Pi-hole host root URL in `PIHOLE_URL` (no `/admin` suffix).

### Updating

Re-run the setup script — it pulls the latest code and reinstalls:

```bash
bash /opt/prox-sync/setup.sh
```

### Useful commands

```bash
# Manual sync
/opt/prox-sync/.venv/bin/python -m sync.main

# Dry run
DRY_RUN=true /opt/prox-sync/.venv/bin/python -m sync.main

# Check timer
systemctl status proxmox-sync.timer

# Follow logs
journalctl -u proxmox-sync.service -f
```

## Delete protection

Only resources created by prox-sync are modified or deleted:

- **NPM**: proxy hosts with `# prox-sync:managed` in their advanced config
- **Pi-hole**: records matching `*.<DOMAIN>` pointing to `NPM_IP`

Manually created hosts and records are never touched.

## Conflict detection

If two containers define the same service name (e.g. `jellyfin+8096` on CT 100 and `jellyfin+8097` on CT 101):

- No changes are applied
- The conflict is logged
- Exit code 1

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Service name conflict |
| 2 | API or runtime error |

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check sync/ tests/
ruff format sync/ tests/
mypy sync/
```

## Project structure

```
sync/
  main.py        — entry point
  config.py      — settings from .env
  models.py      — data classes
  proxmox.py     — Proxmox API client
  npm.py         — NPM API client
  pihole.py      — Pi-hole API client
  parser.py      — tag parsing + conflict detection
  diff.py        — desired vs actual state diff
  engine.py      — orchestrator

tests/           — unit tests
systemd/         — service + timer units
```
