---
title: RegulatorIQ RBI Compliance API
emoji: ⚖️
colorFrom: yellow
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# RegulatorIQ API on Hugging Face Spaces

This repository contains the containerized deployment of RegulatorIQ for Hugging Face Spaces using the Docker SDK.

- **Hardware:** 2 vCPU / 16 GB RAM (Free Tier)
- **Port:** 7860
- **Liveness:** `GET /health`
- **Readiness:** `GET /ready`
- **Streaming:** `POST /ask`
