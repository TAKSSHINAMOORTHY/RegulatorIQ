terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

variable "compartment_id" {
  type        = string
  description = "OCI Compartment OCID"
  default     = ""
}

variable "domain_name" {
  type        = string
  description = "Target domain for Caddy TLS"
  default     = "localhost"
}

# Always-Free Ampere A1.Flex or fallback E2.1.Micro
resource "oci_core_instance" "regulatoriq_vm" {
  count               = var.compartment_id != "" ? 1 : 0
  compartment_id      = var.compartment_id
  display_name        = "regulatoriq-api-prod"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  metadata = {
    user_data = base64encode(<<-EOF
      #!/bin/bash
      apt-get update && apt-get install -y docker.io docker-compose-v2
      systemctl enable --now docker
      mkdir -p /opt/regulatoriq
      # Cloud-init compose launch
    EOF
    )
  }
}
