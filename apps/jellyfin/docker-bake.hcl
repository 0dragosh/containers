target "docker-metadata-action" {}

variable "VERSION" {
  // renovate: datasource=github-releases depName=jellyfin/jellyfin versioning=semver
  default = "v12.0-rc2"
}

variable "JELLYFIN_IMAGE_DIGEST" {
  default = "sha256:2d1a69be5aa2695d0c2df90ebeb76bbcc6efc0a798cb09bfa65906680e1d785a"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/jellyfin/jellyfin"
}

target "image" {
  inherits = ["docker-metadata-action"]
  args = {
    JELLYFIN_IMAGE = "docker.io/jellyfin/jellyfin:${replace(VERSION, "v", "")}@${JELLYFIN_IMAGE_DIGEST}"
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
