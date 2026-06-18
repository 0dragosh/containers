#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_DIR="${CONFIG_DIR:-/config}"
BRIDGE_DIR="/opt/whatsapp-mcp/whatsapp-bridge"
MCP_DIR="/opt/whatsapp-mcp/whatsapp-mcp-server"
TOKEN_FILE="${CONFIG_DIR}/.bridge-token"

mkdir -p "${CONFIG_DIR}" "${CONFIG_DIR}/outbox"
chmod 700 "${CONFIG_DIR}" "${CONFIG_DIR}/outbox" || true

if [[ -z "${WHATSAPP_BRIDGE_TOKEN:-}" ]]; then
    if [[ ! -s "${TOKEN_FILE}" ]]; then
        token_tmp="$(mktemp "${CONFIG_DIR}/.bridge-token.XXXXXX")"
        umask 077
        python -c 'import secrets; print(secrets.token_hex(32))' > "${token_tmp}"
        chmod 600 "${token_tmp}" || true
        ln "${token_tmp}" "${TOKEN_FILE}" 2>/dev/null || true
        rm -f "${token_tmp}"
    fi
    export WHATSAPP_BRIDGE_TOKEN
    WHATSAPP_BRIDGE_TOKEN="$(tr -d '\r\n' < "${TOKEN_FILE}")"
fi

export WHATSAPP_BRIDGE_PORT="${WHATSAPP_BRIDGE_PORT:-8765}"
export WHATSAPP_API_URL="${WHATSAPP_API_URL:-http://127.0.0.1:${WHATSAPP_BRIDGE_PORT}/api}"
export WHATSAPP_DB_PATH="${WHATSAPP_DB_PATH:-${CONFIG_DIR}/messages.db}"
export WHATSMEOW_DB_PATH="${WHATSMEOW_DB_PATH:-${CONFIG_DIR}/whatsapp.db}"
export WHATSAPP_MEDIA_ROOTS="${WHATSAPP_MEDIA_ROOTS:-${CONFIG_DIR}/outbox}"
export FORWARD_SELF="${FORWARD_SELF:-false}"
