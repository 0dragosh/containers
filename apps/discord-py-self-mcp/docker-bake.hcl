target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-tags depName=Microck/discord.py-self-mcp versioning=semver extractVersion=^v(?<version>.*)$
  default = "1.4.1"
}

variable "DISCORD_PY_SELF_VERSION" {
  // renovate: datasource=github-tags depName=dolfies/discord.py-self versioning=semver extractVersion=^v(?<version>.*)$
  default = "2.1.0"
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
    VERSION                 = "${VERSION}"
    DISCORD_PY_SELF_VERSION = "${DISCORD_PY_SELF_VERSION}"
    SOURCE                  = "${SOURCE}"
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
