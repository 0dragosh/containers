# syntax=docker/dockerfile:1

ARG VERSION=1.4.1
ARG DISCORD_PY_SELF_VERSION=2.1.0
ARG SOURCE=https://github.com/Microck/discord.py-self-mcp
ARG PYTHON_IMAGE=docker.io/library/python:3.14-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
ARG VERSION
ARG DISCORD_PY_SELF_VERSION
ARG SOURCE
WORKDIR /src
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "v${VERSION}" "${SOURCE}" .
RUN sed -i "s/discord.py-self\\[voice\\]==2.0.1/discord.py-self[voice]==${DISCORD_PY_SELF_VERSION}/g" pyproject.toml requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venv/bin/python -m pip install --no-cache-dir .

FROM ${PYTHON_IMAGE}

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 discord-py-self-mcp \
    && useradd --system --uid 1000 --gid 1000 --home-dir /tmp discord-py-self-mcp \
    && mkdir -p /opt/discord-py-self-mcp \
    && chown -R 1000:1000 /opt/discord-py-self-mcp

COPY --from=builder --chown=1000:1000 /opt/venv /opt/venv

ENV HOME=/tmp \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 1000:1000
WORKDIR /opt/discord-py-self-mcp
ENTRYPOINT ["discord-py-self-mcp"]
