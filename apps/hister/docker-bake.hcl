target "docker-metadata-action" {}

variable "VERSION" {
  default = "latest"
}

group "default" {
  targets = ["image-local"]
}

variable "SOURCE" {
  default = "https://github.com/asciimoo/hister"
}

target "image" {
  inherits = ["docker-metadata-action"]
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
