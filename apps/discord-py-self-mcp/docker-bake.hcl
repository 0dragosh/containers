target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-tags depName=Microck/discord.py-self-mcp versioning=semver extractVersion=^v(?<version>.*)$
  default = "1.4.1"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/Microck/discord.py-self-mcp"
}

target "image" {
  inherits = ["docker-metadata-action"]
  args = {
    VERSION = "${VERSION}"
    SOURCE  = "${SOURCE}"
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
