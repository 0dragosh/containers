#!/usr/bin/env bash
set -Eeuo pipefail

source /opt/whatsapp-mcp/common-env.sh

cd "${BRIDGE_DIR}"
exec "${BRIDGE_DIR}/whatsapp-bridge" "$@" >&2
