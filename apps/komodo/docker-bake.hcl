target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-releases depName=moghtech/komodo versioning=loose
  default = "1.18.4"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/moghtech/komodo"
}

target "image" {
  inherits = ["docker-metadata-action"]
  args = {
    VERSION = "${VERSION}"
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
