target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-releases depName=verygoodplugins/whatsapp-mcp versioning=semver
  default = "0.3.0"
}

variable "WHATSMEOW_VERSION" {
  // renovate: datasource=go depName=go.mau.fi/whatsmeow
  default = "v0.0.0-20260609091626-4e622162b959"
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
