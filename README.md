# Running a Custom Docker Validation Framework as an AzureML Parallel Job

This repo shows how to run a custom Docker-based validation framework across thousands of blob-stored data sequences using an AzureML parallel job. Your Docker image **is** the AzureML environment - the job runs inside your container, no Docker-in-Docker required.

The pattern: a CSV "dispatch table" lists the blob URIs for each validation unit, wrapped in an MLTable so the parallel job can split it automatically. Each worker downloads the data via `azureml-fsspec`, shells out to whatever test framework lives in the image, and returns a result row.

> **This is a reference sample, not production code.** Adapt it to your stack, then own it.

---

## The Problem

You have:

- A **test/validation framework** packaged in a Docker image (e.g. Julia + Python + custom tooling).
- **Thousands of data sequences** (~1 GB each), each requiring files from **three** (or more) **separate blob stores** (e.g. recordings, labels, and a third data source, such as e.g. training output).
- A need to run validations **in parallel** on AzureML compute.

Docker-in-Docker doesn't work on AzureML. And you can't point a single MLTable at data scattered across multiple storage accounts.

## The Solution

```
                    ┌─────────────────────────────────────────┐
                    │  AzureML Pipeline                       │
                    │                                         │
  ┌──────────┐      │  ┌────────────────────────────────────┐ │
  │ dispatch │────▶│  │ Parallel Job (N nodes × M workers) │ │
  │ table    │      │  │                                    │ │
  │ (CSV →   │      │  │  Custom Docker Environment         │ │
  │  MLTable)│      │  │  ┌───────────────────────────────┐ │ │
  └──────────┘      │  │  │ entry_script.py               │ │ │
                    │  │  │  1. read DataFrame row        │ │ │
                    │  │  │  2. download 3 blobs (fsspec) │ │ │
                    │  │  │  3. subprocess → validate.sh  │ │ │
                    │  │  │  4. return result row         │ │ │
                    │  │  └───────────────────────────────┘ │ │
                    │  └────────────────────────────────────┘ │
                    │                  │                      │
                    │                  ▼                      │
                    │         results (appended CSV)          │
                    └─────────────────────────────────────────┘
```

The key ideas:

1. **Your Docker image is the AzureML environment** - AzureML builds it and runs every worker inside it.
2. **A CSV "dispatch table"** lists the three blob URIs per sequence. Wrap it in an MLTable with `read_delimited`, and the parallel job splits it into mini-batches automatically.
3. **The entry script** receives each mini-batch as a pandas DataFrame, downloads the files via `azureml-fsspec`, shells out to your validation tool, and returns a result row.
4. **Results are aggregated** via `append_row_to` into a single output file.

In production, the dispatch CSV is typically an **output of an upstream pipeline step** (training run, data preprocessing, or a dataset registration job). This repo includes a static CSV for demonstration.

---

## Repo Structure

```
pipeline/
├── data/
│   ├── sample_dispatch.csv     # 3 rows × 3 URI columns (placeholder paths)
│   └── MLTable                 # Wraps the CSV as a tabular MLTable
├── environment/
│   ├── Dockerfile              # Custom env: Julia + Python + validation tooling
│   ├── requirements.txt        # Pinned Python dependencies
│   └── validate.sh             # Placeholder - replace with your framework
├── src/
│   └── entry_script.py         # init/run/shutdown - the parallel job logic
├── tests/
│   ├── test_mltable.py         # MLTable parsing and schema tests
│   ├── test_entry_script.py    # Entry script unit tests (mocked I/O)
│   └── test_pipeline_yaml.py   # Pipeline YAML structure tests
└── pipeline.yml                # AzureML pipeline definition
```

### `sample_dispatch.csv`

Each row is one validation unit. Columns are long-form `azureml://` URIs that include the full subscription/resource-group/workspace path:

| Column            | Points to              |
| ----------------- | ---------------------- |
| `sequence_path`   | Recording blob         |
| `label_path`      | Labels blob            |
| `third_data_path` | Third data source blob |

### `MLTable`

A YAML file that tells AzureML to parse the CSV with `read_delimited`. The parallel job splits this table by physical size (`mini_batch_size: "1kb"` ≈ 1–3 rows per batch).

### `Dockerfile`

Installs Julia, Python dependencies (from `requirements.txt`), and copies `validate.sh` into the image. **Replace the Julia setup and `validate.sh` with your actual framework.**

### `entry_script.py`

The parallel job entry point. Key functions:

- **`init()`** - called once per worker. Minimal setup (logging).
- **`run(mini_batch)`** - for each row: downloads three files via `azureml-fsspec` → runs `validate.sh` via subprocess → returns a result DataFrame.
- **`shutdown()`** - cleans up cached filesystem clients.

The CSV stores long-form URIs (`azureml://subscriptions/.../datastores/<ds>/paths/...`), which `AzureMachineLearningFileSystem` accepts directly - no URI expansion needed.

### `pipeline.yml`

Defines the pipeline with a single parallel job step. Key settings:

- `mode: direct` - required for tabular MLTable input.
- `mini_batch_size: "1kb"` - physical size, not row count. Targets ~1 sequence per mini-batch.
- `environment.build.path: ./environment` - AzureML builds the Dockerfile automatically.
- `append_row_to` - aggregates result rows from all workers into one output file.

---

## Prerequisites

| Resource                          | Purpose                                                                                 |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| **AzureML Workspace**             | Hosts the pipeline, environment, and compute                                            |
| **AmlCompute Cluster**            | Runs the parallel workers (CPU or GPU)                                                  |
| **Azure Blob Storage Datastores** | Registered in the workspace - one per blob store                                        |
| **Managed Identity**              | The compute cluster's identity needs `Storage Blob Data Reader` on each storage account |

---

## How to Run

1. **Clone this repo** and `cd pipeline/`.

2. **Edit `sample_dispatch.csv`** - replace the placeholder URIs with your actual long-form `azureml://subscriptions/.../datastores/<your-datastore>/paths/<your-path>` entries (or plug in your own CSV).

3. **Edit `pipeline.yml`** - replace `<your-compute-cluster>` with your AmlCompute cluster name.

4. **Submit the pipeline:**

   ```bash
   az ml job create --file pipeline.yml \
       --resource-group <your-resource-group> \
       --workspace-name <your-workspace-name>
   ```

   To override parallel job settings at submission time without editing YAML:

   ```bash
   az ml job create --file pipeline.yml \
       --resource-group <your-resource-group> \
       --workspace-name <your-workspace-name> \
       --set jobs.validate.resources.instance_count=4 \
       --set jobs.validate.mini_batch_size="2kb"
   ```

---

## Local Development

The repo uses [uv](https://docs.astral.sh/uv/) for fast local dependency management. You don't need uv for CI or AzureML - it's purely a local convenience.

```bash
cd pipeline/
uv sync --extra dev    # create venv + install runtime + dev deps
uv run pytest -v       # run the test suite
```

Tests mock all Azure and subprocess calls - no workspace, credentials, or network access required.

---

## How to Adapt This

| What to change           | Where                                                | Notes                                                                                      |
| ------------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Your test framework      | `environment/Dockerfile` + `environment/validate.sh` | Replace Julia/validate.sh with your actual framework binary or script                      |
| Input data columns       | `data/sample_dispatch.csv`                           | Add/remove/rename columns to match your data sources. Update `entry_script.py` accordingly |
| Data access method       | `src/entry_script.py`                                | Uses `azureml-fsspec`; switch to `azure-storage-blob` SDK if you need lower-level control  |
| Parallelism              | `pipeline.yml`                                       | Tune `resources.instance_count`, `max_concurrency_per_instance`, `mini_batch_size`         |
| Output format            | `src/entry_script.py`                                | The `run()` return DataFrame shape feeds into `append_row_to`                              |
| Environment provisioning | `pipeline.yml`                                       | For production, pre-build the image and switch from `build.path` to `image:`               |

---

## Key Concepts

### Why a Dispatch Table?

When data lives across multiple blob stores (different storage accounts, different containers), you can't point a single MLTable at a folder and split by file count. Instead, we use a CSV where each row lists the URIs for one validation unit. The parallel job splits the _table_ by row, and the entry script handles data access per row.

### Data Access Pattern

The entry script uses `azureml-fsspec` - an AzureML-native fsspec implementation that handles credential passthrough automatically via the compute's managed identity. The CSV stores long-form URIs (`azureml://subscriptions/.../datastores/<name>/paths/<path>`), which the `AzureMachineLearningFileSystem` constructor accepts directly.

---

## License

MIT
