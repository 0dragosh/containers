#!/usr/bin/env bash
set -Eeuo pipefail

/opt/whatsapp-mcp/bridge-entrypoint.sh "$@" &
bridge_pid=$!

terminate() {
    kill -TERM "${bridge_pid}" 2>/dev/null || true
    wait "${bridge_pid}" 2>/dev/null || true
}

trap terminate INT TERM

/opt/whatsapp-mcp/mcp-entrypoint.sh
status=$?
terminate
exit "${status}"
