#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/whoppercheese/prox-sync.git"
INSTALL_DIR="/opt/prox-sync"
CONFIG_DIR="/etc/prox-sync"
ENV_FILE="${CONFIG_DIR}/.env"

# ---------- helpers ----------

info()  { printf '\033[1;34m>>>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m>>>\033[0m %s\n' "$*"; }
err()   { printf '\033[1;31m>>>\033[0m %s\n' "$*" >&2; }

need_cmd() {
    if ! command -v "$1" &>/dev/null; then
        err "$1 not found, installing..."
        return 1
    fi
    return 0
}

# ---------- root check ----------

if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root."
    exit 1
fi

# ---------- packages ----------

info "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git >/dev/null

# ---------- clone / update ----------

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    info "Cloning repository..."
    git clone "$REPO" "$INSTALL_DIR"
fi

# ---------- venv + install ----------

info "Setting up Python virtual environment..."
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install --quiet "${INSTALL_DIR}"

# ---------- config ----------

mkdir -p "$CONFIG_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    cp "${INSTALL_DIR}/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    info "Created ${ENV_FILE} — edit it with your values before starting the timer."
    NEEDS_CONFIG=1
else
    ok "Config already exists at ${ENV_FILE}, skipping."
    NEEDS_CONFIG=0
fi

# ---------- systemd ----------

info "Installing systemd units..."
cp "${INSTALL_DIR}/systemd/proxmox-sync.service" /etc/systemd/system/
cp "${INSTALL_DIR}/systemd/proxmox-sync.timer"   /etc/systemd/system/
systemctl daemon-reload

if [[ $NEEDS_CONFIG -eq 0 ]]; then
    systemctl enable --now proxmox-sync.timer
    ok "Timer enabled and started."
else
    systemctl enable proxmox-sync.timer
    ok "Timer enabled (not started — configure ${ENV_FILE} first, then run: systemctl start proxmox-sync.timer)"
fi

# ---------- done ----------

echo ""
ok "prox-sync installed to ${INSTALL_DIR}"
echo ""
echo "  Config:      ${ENV_FILE}"
echo "  Manual run:  ${INSTALL_DIR}/.venv/bin/python -m sync.main"
echo "  Dry run:     DRY_RUN=true ${INSTALL_DIR}/.venv/bin/python -m sync.main"
echo "  Logs:        journalctl -u proxmox-sync.service"
echo "  Timer:       systemctl status proxmox-sync.timer"
echo ""

if [[ $NEEDS_CONFIG -eq 1 ]]; then
    echo "  NEXT STEP:   nano ${ENV_FILE}"
    echo "               systemctl start proxmox-sync.timer"
    echo ""
fi
