"""
entry_script.py — AzureML parallel job entry script.

Receives mini-batches (pandas DataFrames) from the tabular MLTable
dispatch table. Each row contains relative paths that are resolved
against read-only mounted input stores.

For each row the script:
  1. Resolves local filesystem paths from mount roots + relative paths.
  2. Invokes the validation framework (validate.sh) via subprocess.
  3. Returns a result DataFrame row with pass/fail status.
"""

import argparse
import logging
import os
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_VALIDATE_CMD = "/opt/validation/validate.sh"
_SUBPROCESS_TIMEOUT = 600

_SEQUENCES_MOUNT: str | None = None
_LABELS_MOUNT: str | None = None
_MLHC_MOUNT: str | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--sequences_mount", required=True)
    parser.add_argument("--labels_mount", required=True)
    parser.add_argument("--mlhc_mount", required=True)
    return parser


def _require_mounts() -> tuple[str, str, str]:
    if not _SEQUENCES_MOUNT or not _LABELS_MOUNT or not _MLHC_MOUNT:
        raise RuntimeError(
            "Mount paths are not initialised. Ensure init() parsed "
            "--sequences_mount, --labels_mount, and --mlhc_mount."
        )
    return _SEQUENCES_MOUNT, _LABELS_MOUNT, _MLHC_MOUNT


def _resolve_safe_path(mount_root: str, relative_path: str) -> str:
    mount_root_resolved = Path(mount_root).resolve(strict=False)
    candidate = (mount_root_resolved / relative_path).resolve(strict=False)

    if os.path.commonpath([str(candidate), str(mount_root_resolved)]) != str(
        mount_root_resolved
    ):
        raise ValueError(f"Relative path escapes mount root: {relative_path}")

    return str(candidate)


def _resolve_paths(row: pd.Series) -> tuple[str, str, str]:
    sequences_mount, labels_mount, mlhc_mount = _require_mounts()
    sequence_path = _resolve_safe_path(sequences_mount, row["sequence_filepath"])
    label_path = _resolve_safe_path(labels_mount, row["label_filepath"])
    mlhc_path = _resolve_safe_path(mlhc_mount, row["mlhc_filepath"])
    return sequence_path, label_path, mlhc_path


def init() -> None:
    global _SEQUENCES_MOUNT, _LABELS_MOUNT, _MLHC_MOUNT

    parser = _build_parser()
    args, _ = parser.parse_known_args()
    _SEQUENCES_MOUNT = args.sequences_mount
    _LABELS_MOUNT = args.labels_mount
    _MLHC_MOUNT = args.mlhc_mount

    logger.info("Worker initialised with mounted inputs.")


def run(mini_batch: pd.DataFrame) -> pd.DataFrame:
    results: list[dict[str, Any]] = []

    for _, row in mini_batch.iterrows():
        sequence_relative_path: str = row["sequence_filepath"]

        logger.info("Processing sequence folder: %s", sequence_relative_path)

        try:
            sequence_path, label_path, mlhc_path = _resolve_paths(row)

            proc = subprocess.run(
                [_VALIDATE_CMD, sequence_path, label_path, mlhc_path],
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
                    "sequence_filepath": sequence_relative_path,
                    "status": status,
                    "exit_code": proc.returncode,
                    "message": message,
                }
            )

        except Exception as exc:
            logger.error("Failed to process %s: %s", sequence_relative_path, exc)
            results.append(
                {
                    "sequence_filepath": sequence_relative_path,
                    "status": "fail",
                    "exit_code": -1,
                    "message": str(exc),
                }
            )

    return pd.DataFrame(results)


def shutdown() -> None:
    logger.info("Worker shutdown complete.")
