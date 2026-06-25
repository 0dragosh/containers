# syntax=docker/dockerfile:1

ARG VERSION=1.6.5
ARG SOURCE=https://github.com/aplaceforallmystuff/mcp-arr
ARG SOURCE_REV=768120d945cc6b56ad651e018ba61943f80631cc
ARG NODE_IMAGE=docker.io/library/node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd

FROM ${NODE_IMAGE} AS builder
ARG VERSION
ARG SOURCE
ARG SOURCE_REV
WORKDIR /src
RUN apk add --no-cache git \
    && git clone --depth 1 --branch "v${VERSION}" "${SOURCE}" . \
    && test "$(git rev-parse HEAD)" = "${SOURCE_REV}"
RUN npm ci \
    && npm run build

FROM ${NODE_IMAGE}
USER 1000:1000
WORKDIR /home/node
COPY --from=builder /src/package.json /src/package-lock.json ./
RUN cp package.json package.json.tmp \
    && cp package-lock.json package-lock.json.tmp \
    && mv package.json.tmp package.json \
    && mv package-lock.json.tmp package-lock.json \
    && npm ci --omit=dev \
    && npm cache clean --force
COPY --from=builder /src/dist ./dist
RUN cp -R dist dist.tmp \
    && rm -rf dist \
    && mv dist.tmp dist

ENTRYPOINT ["node", "dist/index.js"]
