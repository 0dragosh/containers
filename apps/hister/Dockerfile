# syntax=docker/dockerfile:1

ARG HISTER_IMAGE=ghcr.io/asciimoo/hister:v0.15.0@sha256:e7b88f7e72171a29b6ec6d8579f2fe9ff74eb352b8b93d331f7aa68b02bdcbf1
ARG YT_DLP_VERSION=2025.03.31-r0

FROM ${HISTER_IMAGE}
ARG YT_DLP_VERSION
USER root
RUN apk add --no-cache "yt-dlp=${YT_DLP_VERSION}" \
    && ln -sf /usr/bin/yt-dlp /usr/local/bin/yt-dlp
USER 65532:65532
