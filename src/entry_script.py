"""
entry_script.py — AzureML parallel job entry script.

Receives mini-batches (pandas DataFrames) from the tabular MLTable
dispatch table. Each row contains three long-form azureml:// URIs
pointing to data in separate blob stores.

For each row the script:
  1. Downloads the three files via azureml-fsspec.
  2. Invokes the validation framework (validate.sh) via subprocess.
  3. Returns a result DataFrame row with pass/fail status.

Alternative: replace azureml-fsspec with the azure-storage-blob SDK
if you need lower-level control over blob access.
"""

import logging
import os
import subprocess
import tempfile
from typing import Any

import pandas as pd
from azureml.fsspec import AzureMachineLearningFileSystem

logger = logging.getLogger(__name__)

# --- Module-level state ----------------------------------------------

_fs_cache: dict[str, AzureMachineLearningFileSystem] = {}

# Path to the validation framework inside the Docker image.
# Replace with the actual binary / script path in your image.
_VALIDATE_CMD = "/opt/validation/validate.sh"

# Timeout (seconds) for the validation subprocess per sequence.
_SUBPROCESS_TIMEOUT = 600


# --- Helpers ---------------------------------------------------------


def _parse_long_uri(long_uri: str) -> tuple[str, str]:
    """Split a long-form azureml:// URI into (fs_uri, file_path).

    Long form:
        azureml://subscriptions/.../datastores/<ds>/paths/<path>

    Returns:
        fs_uri    – everything up to and including the datastore name
        file_path – the portion after ``/paths/``
    """
    marker = "/paths/"
    idx = long_uri.find(marker)
    if idx == -1:
        raise ValueError(f"URI missing '/paths/' segment: {long_uri}")
    fs_uri = long_uri[:idx]
    file_path = long_uri[idx + len(marker) :]
    return fs_uri, file_path


def _get_fs(fs_uri: str) -> AzureMachineLearningFileSystem:
    """Return a cached AzureMachineLearningFileSystem for *fs_uri*.

    Authentication is handled automatically — azureml-fsspec uses the
    compute cluster's managed identity (no keys or tokens needed).
    """
    if fs_uri not in _fs_cache:
        _fs_cache[fs_uri] = AzureMachineLearningFileSystem(fs_uri)
    return _fs_cache[fs_uri]


def _download_file(long_uri: str, dest_dir: str) -> str:
    """Download a blob via azureml-fsspec and return the local path."""
    fs_uri, remote_path = _parse_long_uri(long_uri)
    fs = _get_fs(fs_uri)

    local_name = os.path.basename(remote_path)
    local_path = os.path.join(dest_dir, local_name)

    logger.info("Downloading %s → %s", long_uri, local_path)
    fs.download(remote_path, local_path)
    return local_path


# --- Parallel job interface ------------------------------------------


def init() -> None:
    """Called once per worker process. Minimal setup."""
    logger.info("Worker initialised.")


def run(mini_batch: pd.DataFrame) -> pd.DataFrame:
    """Process one mini-batch (one or more rows from the dispatch table).

    Args:
        mini_batch: DataFrame with columns ``sequence_path``,
            ``label_path``, ``third_data_path`` — each a long-form
            ``azureml://`` URI string.

    Returns:
        DataFrame with one row per input row. Columns:
            sequence_path, status, exit_code, message
    """
    results: list[dict[str, Any]] = []

    for _, row in mini_batch.iterrows():
        seq_uri: str = row["sequence_path"]
        label_uri: str = row["label_path"]
        third_uri: str = row["third_data_path"]

        logger.info("Processing sequence: %s", seq_uri)

        try:
            # Download the three files to a temporary directory.
            # AzureML parallel jobs don't provide a per-batch scratch dir,
            # so we use tempfile for auto-cleanup and collision avoidance.
            with tempfile.TemporaryDirectory() as tmp:
                seq_path = _download_file(seq_uri, tmp)
                label_path = _download_file(label_uri, tmp)
                third_path = _download_file(third_uri, tmp)

                # Run the validation framework via subprocess.
                # We shell out (rather than calling Python directly) because
                # the framework is a CLI tool (e.g. Julia binary, shell script)
                # that lives in the Docker image.
                proc = subprocess.run(
                    [_VALIDATE_CMD, seq_path, label_path, third_path],
                    capture_output=True,
                    text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )

            status = "pass" if proc.returncode == 0 else "fail"
            message = (
                proc.stdout.strip() if proc.returncode == 0 else proc.stderr.strip()
            )

            results.append(
                {
                    "sequence_path": seq_uri,
                    "status": status,
                    "exit_code": proc.returncode,
                    "message": message,
                }
            )

        except Exception as exc:
            logger.error("Failed to process %s: %s", seq_uri, exc)
            results.append(
                {
                    "sequence_path": seq_uri,
                    "status": "fail",
                    "exit_code": -1,
                    "message": str(exc),
                }
            )

    return pd.DataFrame(results)


def shutdown() -> None:
    """Called once when the worker is done. Clean up cached FS clients."""
    _fs_cache.clear()
    logger.info("Worker shutdown complete.")
