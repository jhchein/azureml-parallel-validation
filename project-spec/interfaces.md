# Interfaces

Contracts only — signatures, schemas, auth claims. Not implementation.

## AzureML Parallel Job Entry Script

The parallel job runtime calls these three functions from `src/entry_script.py`:

| Function          | Signature                        | Called                              |
| ----------------- | -------------------------------- | ----------------------------------- |
| `init()`          | `() -> None`                     | Once per worker process at startup  |
| `run(mini_batch)` | `(pd.DataFrame) -> pd.DataFrame` | Once per mini-batch                 |
| `shutdown()`      | `() -> None`                     | Once per worker process at teardown |

- `shutdown()` is currently a no-op cleanup hook (logging only).

### `run()` input schema (mini-batch DataFrame)

| Column              | Type  | Description                                                       |
| ------------------- | ----- | ----------------------------------------------------------------- |
| `sequence_filepath` | `str` | Relative path (from mounted sequences store) to a sequence folder |
| `label_filepath`    | `str` | Relative path (from mounted labels store) to labels file          |
| `mlhc_filepath`     | `str` | Relative path (from mounted MLHC store) to parquet file           |

### `run()` output schema (result DataFrame)

| Column              | Type  | Description                                                     |
| ------------------- | ----- | --------------------------------------------------------------- |
| `sequence_filepath` | `str` | Input relative path (for traceability)                          |
| `status`            | `str` | `"pass"` or `"fail"`                                            |
| `exit_code`         | `int` | Subprocess exit code (`-1` on exception)                        |
| `message`           | `str` | stdout on success, stderr on failure, exception string on error |

## Validation Subprocess Contract (`validate.sh`)

```
validate.sh <sequence_folder> <labels_file> <mlhc_file>
```

- `<sequence_folder>` is a directory path, not a single file path.

- Exit code `0` → pass; non-zero → fail.
- stdout captured as result message on success; stderr on failure.
- Timeout: 600 seconds (configurable via `_SUBPROCESS_TIMEOUT`).
