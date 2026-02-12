"""Tests for the parallel job entry script (run function)."""

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# The entry script lives outside the tests package, so we import by path.
# Adjust if your sys.path configuration differs.
from entry_script import run, init, shutdown, _parse_long_uri, _fs_cache

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_fs_cache() -> None:
    """Prevent stale AzureMachineLearningFileSystem mocks leaking between tests."""
    _fs_cache.clear()


SAMPLE_URI_PREFIX = (
    "azureml://subscriptions/00000000-0000-0000-0000-000000000000"
    "/resourcegroups/rg/workspaces/ws/datastores"
)


@pytest.fixture()
def mini_batch() -> pd.DataFrame:
    """A two-row mini-batch DataFrame with long-form URIs."""
    return pd.DataFrame(
        {
            "sequence_path": [
                f"{SAMPLE_URI_PREFIX}/recordings/paths/seq_001/recording.bin",
                f"{SAMPLE_URI_PREFIX}/recordings/paths/seq_002/recording.bin",
            ],
            "label_path": [
                f"{SAMPLE_URI_PREFIX}/labels/paths/seq_001/labels.csv",
                f"{SAMPLE_URI_PREFIX}/labels/paths/seq_002/labels.csv",
            ],
            "third_data_path": [
                f"{SAMPLE_URI_PREFIX}/thirddata/paths/seq_001/metadata.dat",
                f"{SAMPLE_URI_PREFIX}/thirddata/paths/seq_002/metadata.dat",
            ],
        }
    )


def _make_completed_process(
    returncode: int = 0,
    stdout: str = "ok",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


EXPECTED_OUTPUT_COLUMNS = ["sequence_path", "status", "exit_code", "message"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunSuccess:
    """Validation subprocess returns exit code 0."""

    @patch("entry_script.subprocess.run")
    @patch("entry_script.AzureMachineLearningFileSystem")
    def test_returns_correct_columns(
        self,
        mock_fs_cls: MagicMock,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_fs_cls.return_value.download = MagicMock()
        mock_subprocess.return_value = _make_completed_process()

        result = run(mini_batch)

        assert list(result.columns) == EXPECTED_OUTPUT_COLUMNS

    @patch("entry_script.subprocess.run")
    @patch("entry_script.AzureMachineLearningFileSystem")
    def test_row_count_matches_input(
        self,
        mock_fs_cls: MagicMock,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_fs_cls.return_value.download = MagicMock()
        mock_subprocess.return_value = _make_completed_process()

        result = run(mini_batch)

        assert len(result) == len(mini_batch)

    @patch("entry_script.subprocess.run")
    @patch("entry_script.AzureMachineLearningFileSystem")
    def test_pass_status_on_success(
        self,
        mock_fs_cls: MagicMock,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_fs_cls.return_value.download = MagicMock()
        mock_subprocess.return_value = _make_completed_process(stdout="all good")

        result = run(mini_batch)

        assert all(result["status"] == "pass")
        assert all(result["exit_code"] == 0)
        assert all(result["message"] == "all good")


class TestRunFailure:
    """Validation subprocess returns non-zero exit code."""

    @patch("entry_script.subprocess.run")
    @patch("entry_script.AzureMachineLearningFileSystem")
    def test_fail_status_on_nonzero_exit(
        self,
        mock_fs_cls: MagicMock,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_fs_cls.return_value.download = MagicMock()
        mock_subprocess.return_value = _make_completed_process(
            returncode=1, stderr="validation error"
        )

        result = run(mini_batch)

        assert all(result["status"] == "fail")
        assert all(result["exit_code"] == 1)
        assert all(result["message"] == "validation error")


class TestRunException:
    """Download or subprocess raises an exception."""

    @patch("entry_script.AzureMachineLearningFileSystem")
    def test_exception_produces_fail_row(
        self,
        mock_fs_cls: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_fs_cls.return_value.download = MagicMock(
            side_effect=ConnectionError("blob unreachable")
        )

        result = run(mini_batch)

        assert len(result) == len(mini_batch)
        assert all(result["status"] == "fail")
        assert all(result["exit_code"] == -1)
        assert all("blob unreachable" in m for m in result["message"])


class TestInitShutdown:
    """init() and shutdown() execute without error."""

    def test_init_runs(self) -> None:
        init()

    def test_shutdown_clears_cache(self) -> None:
        shutdown()


# ---------------------------------------------------------------------------
# URI parsing
# ---------------------------------------------------------------------------


class TestParseLongUri:
    """Unit tests for _parse_long_uri."""

    def test_valid_uri_splits_correctly(self) -> None:
        uri = (
            "azureml://subscriptions/00000000-0000-0000-0000-000000000000"
            "/resourcegroups/rg/workspaces/ws"
            "/datastores/recordings/paths/seq_001/recording.bin"
        )
        fs_uri, file_path = _parse_long_uri(uri)

        assert fs_uri == (
            "azureml://subscriptions/00000000-0000-0000-0000-000000000000"
            "/resourcegroups/rg/workspaces/ws"
            "/datastores/recordings"
        )
        assert file_path == "seq_001/recording.bin"

    def test_nested_path(self) -> None:
        uri = (
            "azureml://subscriptions/sub/resourcegroups/rg"
            "/workspaces/ws/datastores/ds/paths/a/b/c/file.csv"
        )
        fs_uri, file_path = _parse_long_uri(uri)

        assert fs_uri.endswith("/datastores/ds")
        assert file_path == "a/b/c/file.csv"

    def test_missing_paths_segment_raises(self) -> None:
        bad_uri = (
            "azureml://subscriptions/sub/resourcegroups/rg/workspaces/ws/datastores/ds"
        )
        with pytest.raises(ValueError, match="/paths/"):
            _parse_long_uri(bad_uri)


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class TestRunTimeout:
    """subprocess.TimeoutExpired produces a fail row."""

    @patch("entry_script.subprocess.run")
    @patch("entry_script.AzureMachineLearningFileSystem")
    def test_timeout_produces_fail_row(
        self,
        mock_fs_cls: MagicMock,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_fs_cls.return_value.download = MagicMock()
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd="validate.sh", timeout=600
        )

        result = run(mini_batch)

        assert len(result) == len(mini_batch)
        assert all(result["status"] == "fail")
        assert all(result["exit_code"] == -1)
        assert all("timed out" in m.lower() for m in result["message"])
