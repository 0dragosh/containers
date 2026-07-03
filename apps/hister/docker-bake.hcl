target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-releases depName=asciimoo/hister versioning=semver
  default = "v0.16.0"
}

variable "HISTER_IMAGE_DIGEST" {
  default = "sha256:e7b88f7e72171a29b6ec6d8579f2fe9ff74eb352b8b93d331f7aa68b02bdcbf1"
}

variable "YT_DLP_VERSION" {
  // renovate: datasource=pypi depName=yt-dlp versioning=pep440
  default = "2026.6.9"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/asciimoo/hister"
}

target "image" {
  inherits = ["docker-metadata-action"]
  args = {
    HISTER_IMAGE   = "ghcr.io/asciimoo/hister:${VERSION}@${HISTER_IMAGE_DIGEST}"
    YT_DLP_VERSION = "${YT_DLP_VERSION}"
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
