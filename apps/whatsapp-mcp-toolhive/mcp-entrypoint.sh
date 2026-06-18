#!/usr/bin/env bash
set -Eeuo pipefail

source /opt/whatsapp-mcp/common-env.sh

cd "${MCP_DIR}"
exec python /opt/whatsapp-mcp/readonly_main.py
