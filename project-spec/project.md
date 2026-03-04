# Project

## Overview

- **Name**: azureml-parallel-validation
- **One-liner**: Reference sample showing how to run a custom Docker-based validation framework across thousands of blob-stored data sequences as an AzureML parallel job.

## Goals

- Demonstrate the dispatch-table pattern for AzureML parallel jobs with multi-blob-store inputs.
- Provide a fully testable, adaptable starting point that others clone and customise for their own validation frameworks.
- Show correct use of managed identity, FUSE mounts (`ro_mount`), `argparse` within worker scripts, and MLTable for tabular parallel job input.

## Non-goals

- Not a production pipeline — consumers are expected to fork and adapt.
- No UI, API, or user-facing service.
- No orchestration beyond a single AzureML pipeline step (no multi-step DAGs).

## Tech Stack

- **Languages**: Python 3.10–3.12, Bash (validate.sh placeholder), Julia (placeholder in Dockerfile)
- **Frameworks**: AzureML SDK v2 (mltable), AzureML runtime deps (azureml-core, azureml-dataset-runtime with FUSE support), pandas, pytest
- **Hosting/Cloud**: Azure — AzureML Workspace, AmlCompute, Azure Blob Storage (via registered datastores)
- **CI/CD**: GitHub Actions (`.github/workflows/test.yml` — pytest on push/PR to main)
- **Local tooling**: uv (optional, for fast local dev)
