target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-tags depName=aplaceforallmystuff/mcp-arr versioning=semver extractVersion=^v(?<version>.*)$
  default = "1.6.5"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/aplaceforallmystuff/mcp-arr"
}

variable "SOURCE_REV" {
  default = "768120d945cc6b56ad651e018ba61943f80631cc"
}

target "image" {
  inherits = ["docker-metadata-action"]
  args = {
    VERSION    = "${VERSION}"
    SOURCE     = "${SOURCE}"
    SOURCE_REV = "${SOURCE_REV}"
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
