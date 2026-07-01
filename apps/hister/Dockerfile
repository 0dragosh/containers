# syntax=docker/dockerfile:1

ARG HISTER_IMAGE=ghcr.io/asciimoo/hister:v0.16.0@sha256:98ba061692aeb36616574defdad9938aba94dbf142463915f596693acd4f5ef4
ARG YT_DLP_VERSION=2026.6.9

FROM ${HISTER_IMAGE}
ARG YT_DLP_VERSION
USER root
RUN apk add --no-cache ca-certificates py3-pip python3 \
    && python3 -m pip install --no-cache-dir --break-system-packages "yt-dlp==${YT_DLP_VERSION}" \
    && YT_DLP_BIN="$(command -v yt-dlp)" \
    && if [ "${YT_DLP_BIN}" != "/usr/local/bin/yt-dlp" ]; then cp "${YT_DLP_BIN}" /usr/local/bin/yt-dlp; fi \
    && /usr/local/bin/yt-dlp --version
USER 65532:65532
