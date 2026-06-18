# syntax=docker/dockerfile:1

ARG VERSION
ARG UPSTREAM_VERSION
ARG WHATSMEOW_VERSION

FROM docker.io/library/golang:1.26-bookworm AS builder
ARG VERSION
ARG UPSTREAM_VERSION
ARG WHATSMEOW_VERSION
WORKDIR /src
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates gcc git libc6-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "v${UPSTREAM_VERSION}" https://github.com/verygoodplugins/whatsapp-mcp.git .
WORKDIR /src/whatsapp-bridge
RUN go get "go.mau.fi/whatsmeow@${WHATSMEOW_VERSION}" \
    && go mod tidy \
    && CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /out/whatsapp-bridge .

FROM docker.io/library/python:3.14-slim-bookworm
ARG VERSION

RUN apt-get update \
    && apt-get install --no-install-recommends -y  bash ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 whatsapp \
    && useradd --system --uid 1000 --gid 1000 --home-dir /opt/whatsapp-mcp whatsapp \
    && mkdir -p /opt/whatsapp-mcp/whatsapp-bridge /config

COPY --from=builder --chown=1000:1000 --chmod=755 /out/whatsapp-bridge /opt/whatsapp-mcp/whatsapp-bridge/whatsapp-bridge
COPY --from=builder --chown=1000:1000 /src/whatsapp-mcp-server /opt/whatsapp-mcp/whatsapp-mcp-server
COPY --chown=1000:1000 --chmod=644 common-env.sh /opt/whatsapp-mcp/common-env.sh
COPY --chown=1000:1000 --chmod=755 entrypoint.sh /opt/whatsapp-mcp/entrypoint.sh
COPY --chown=1000:1000 --chmod=755 bridge-entrypoint.sh /opt/whatsapp-mcp/bridge-entrypoint.sh
COPY --chown=1000:1000 --chmod=755 mcp-entrypoint.sh /opt/whatsapp-mcp/mcp-entrypoint.sh
COPY --chown=1000:1000 --chmod=644 readonly_main.py /opt/whatsapp-mcp/readonly_main.py

RUN python -m pip install --no-cache-dir /opt/whatsapp-mcp/whatsapp-mcp-server \
    && ln -s /config /opt/whatsapp-mcp/whatsapp-bridge/store \
    && chown -R 1000:1000 /opt/whatsapp-mcp /config

ENV PYTHONUNBUFFERED=1 \
    WHATSAPP_BRIDGE_PORT=8765 \
    WHATSAPP_API_URL=http://127.0.0.1:8765/api \
    WHATSAPP_DB_PATH=/config/messages.db \
    WHATSMEOW_DB_PATH=/config/whatsapp.db \
    WHATSAPP_MEDIA_ROOTS=/config/outbox \
    FORWARD_SELF=false

USER 1000:1000
WORKDIR /opt/whatsapp-mcp/whatsapp-mcp-server
ENTRYPOINT ["/opt/whatsapp-mcp/mcp-entrypoint.sh"]
