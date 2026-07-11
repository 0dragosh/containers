target "docker-metadata-action" {}

variable "VERSION" {
  default = "0.5.0"
}

variable "UPSTREAM_VERSION" {
  // renovate: datasource=github-releases depName=verygoodplugins/whatsapp-mcp versioning=semver
  default = "0.4.1"
}

variable "WHATSMEOW_VERSION" {
  // renovate: datasource=go depName=go.mau.fi/whatsmeow versioning=semver
  default = "v0.0.0-20260709092057-73fe7355f59f"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/verygoodplugins/whatsapp-mcp"
}

target "image" {
  inherits = ["docker-metadata-action"]
  args = {
    VERSION            = "${VERSION}"
    UPSTREAM_VERSION   = "${UPSTREAM_VERSION}"
    WHATSMEOW_VERSION = "${WHATSMEOW_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source" = "${SOURCE}"
  }
}

target "image-local" {
  inherits = ["image"]
  output = ["type=docker"]
}

target "image-all" {
  inherits = ["image"]
  platforms = [
    "linux/amd64",
    "linux/arm64"
  ]
}
