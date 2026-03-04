# Pivot to FUSE Mounts and Argparse with Path Traversal Defense

**Status:** Accepted
**Date:** 2026-03-04

## Context

The initial implementation used `azureml-fsspec` to interpret absolute AzureML datastore URIs embedded directly in the routing MLTable. The worker script downloaded entire blobs to local ephemeral storage before running validation.

Feedback indicated that the primary input data ("sequences") is not a single file, but a heavily populated folder per validation unit. Crucially, the validation script typically reads only ~10% of this data. A pre-fetch architecture via fsspec would result in downloading massive amounts of unused data, causing high I/O latency and inefficient storage ballooning on cluster nodes.

Furthermore, relying directly on absolute datastore URIs embedded row-by-row means security validations against path escapement are incredibly abstract.

## Decision

1. **Adopt AzureML FUSE mounts**: Strip `azureml-fsspec` from runtime dependencies. Pass all three root datastores as `uri_folder` pipeline inputs with `mode: ro_mount`. AzureML efficiently streams these blob directories on-demand behind the scenes.
2. **Propagate paths via `argparse`**: Use the parallel job's `program_arguments` config to pass mount paths (`--sequences_mount`, `--labels_mount`, `--mlhc_mount`) to the underlying Python worker `entry_script.py`. Let `init()` capture and preserve them as global variables for the worker lifecycle.
3. **Dispatch via Relative Paths**: Ensure the `sample_dispatch.csv` MLTable only contains _relative_ paths (e.g., `seq_001/`, `labels/seq_001.json`).
4. **Implement Path Traversal Guardrails**: Because the worker will receive a relative path from the user-provided MLTable and join it against a pipeline-defined mounted root directory, we are exposed to path-traversing directory escapes (`../`). Add `_resolve_safe_path()` which uses `os.path.commonpath([candidate, base]) == base` to verify the resulting absolute path remains isolated within the intended mount target.

## Consequences

- Dependency list slims down (no longer tracking `azureml-fsspec` overhead).
- Latency and storage footprints are significantly reduced for subset-read validation scripts.
- We must maintain Python compatibility across Windows (`\\`) and Linux (`/`) within tests since path joining mechanisms differ by OS.
- Any change to the structure of expected datastores now requires updating pipeline bindings (`pipeline.yml`) along with the relative mapping layer, rather than just changing the CSV fields, because inputs are mapped globally instead of per-row.
