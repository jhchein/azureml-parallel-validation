"""Tests for the parallel job entry script (run function)."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import entry_script
from entry_script import init, run, shutdown


@pytest.fixture(autouse=True)
def _reset_mounts() -> None:
    entry_script._SEQUENCES_MOUNT = None
    entry_script._LABELS_MOUNT = None
    entry_script._MLHC_MOUNT = None
    yield
    entry_script._SEQUENCES_MOUNT = None
    entry_script._LABELS_MOUNT = None
    entry_script._MLHC_MOUNT = None


@pytest.fixture()
def mini_batch() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sequence_filepath": [
                "sequence_001/recording_folder",
                "sequence_002/recording_folder",
            ],
            "label_filepath": [
                "labels/sequence_001/labels.json",
                "labels/sequence_002/labels.json",
            ],
            "mlhc_filepath": [
                "sequences_mlhc_data/sequence_001.parquet",
                "sequences_mlhc_data/sequence_002.parquet",
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


EXPECTED_OUTPUT_COLUMNS = ["sequence_filepath", "status", "exit_code", "message"]


class TestInit:
    @patch("entry_script._build_parser")
    def test_init_sets_mount_paths(self, mock_build_parser: MagicMock) -> None:
        parser = MagicMock()
        parser.parse_known_args.return_value = (
            MagicMock(
                sequences_mount="/mnt/sequences",
                labels_mount="/mnt/labels",
                mlhc_mount="/mnt/mlhc",
            ),
            [],
        )
        mock_build_parser.return_value = parser

        init()

        assert entry_script._SEQUENCES_MOUNT == "/mnt/sequences"
        assert entry_script._LABELS_MOUNT == "/mnt/labels"
        assert entry_script._MLHC_MOUNT == "/mnt/mlhc"


class TestRunSuccess:
    @pytest.fixture(autouse=True)
    def _set_mounts(self) -> None:
        entry_script._SEQUENCES_MOUNT = "/mnt/sequences"
        entry_script._LABELS_MOUNT = "/mnt/labels"
        entry_script._MLHC_MOUNT = "/mnt/mlhc"

    @patch("entry_script.subprocess.run")
    def test_returns_correct_columns(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process()

        result = run(mini_batch)

        assert list(result.columns) == EXPECTED_OUTPUT_COLUMNS

    @patch("entry_script.subprocess.run")
    def test_row_count_matches_input(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process()

        result = run(mini_batch)

        assert len(result) == len(mini_batch)

    @patch("entry_script.subprocess.run")
    def test_pass_status_on_success(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process(stdout="all good")

        result = run(mini_batch)

        assert all(result["status"] == "pass")
        assert all(result["exit_code"] == 0)
        assert all(result["message"] == "all good")

    @patch("entry_script.subprocess.run")
    def test_subprocess_receives_resolved_mount_paths(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process()

        run(mini_batch)

        first_call = mock_subprocess.call_args_list[0][0][0]
        assert first_call[1].endswith(
            os.path.join("sequences", "sequence_001", "recording_folder")
        )
        assert first_call[2].endswith(
            os.path.join("labels", "labels", "sequence_001", "labels.json")
        )
        assert first_call[3].endswith(
            os.path.join("mlhc", "sequences_mlhc_data", "sequence_001.parquet")
        )


class TestRunFailure:
    @pytest.fixture(autouse=True)
    def _set_mounts(self) -> None:
        entry_script._SEQUENCES_MOUNT = "/mnt/sequences"
        entry_script._LABELS_MOUNT = "/mnt/labels"
        entry_script._MLHC_MOUNT = "/mnt/mlhc"

    @patch("entry_script.subprocess.run")
    def test_fail_status_on_nonzero_exit(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process(
            returncode=1, stderr="validation error"
        )

        result = run(mini_batch)

        assert all(result["status"] == "fail")
        assert all(result["exit_code"] == 1)
        assert all(result["message"] == "validation error")


class TestRunException:
    @patch("entry_script.subprocess.run")
    def test_missing_mounts_produce_fail_rows(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process()

        result = run(mini_batch)

        assert len(result) == len(mini_batch)
        assert all(result["status"] == "fail")
        assert all(result["exit_code"] == -1)
        assert all("not initialised" in m for m in result["message"])


class TestPathTraversalDefense:
    @pytest.fixture(autouse=True)
    def _set_mounts(self) -> None:
        entry_script._SEQUENCES_MOUNT = "/mnt/sequences"
        entry_script._LABELS_MOUNT = "/mnt/labels"
        entry_script._MLHC_MOUNT = "/mnt/mlhc"

    @patch("entry_script.subprocess.run")
    def test_relative_path_escape_is_blocked(
        self,
        mock_subprocess: MagicMock,
    ) -> None:
        mock_subprocess.return_value = _make_completed_process()

        mini_batch = pd.DataFrame(
            {
                "sequence_filepath": ["../../escape/sequence_folder"],
                "label_filepath": ["labels/sequence_001/labels.json"],
                "mlhc_filepath": ["sequences_mlhc_data/sequence_001.parquet"],
            }
        )

        result = run(mini_batch)

        assert len(result) == 1
        assert result.loc[0, "status"] == "fail"
        assert result.loc[0, "exit_code"] == -1
        assert "escapes mount root" in result.loc[0, "message"]
        mock_subprocess.assert_not_called()


class TestRunTimeout:
    @pytest.fixture(autouse=True)
    def _set_mounts(self) -> None:
        entry_script._SEQUENCES_MOUNT = "/mnt/sequences"
        entry_script._LABELS_MOUNT = "/mnt/labels"
        entry_script._MLHC_MOUNT = "/mnt/mlhc"

    @patch("entry_script.subprocess.run")
    def test_timeout_produces_fail_row(
        self,
        mock_subprocess: MagicMock,
        mini_batch: pd.DataFrame,
    ) -> None:
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd="validate.sh", timeout=600
        )

        result = run(mini_batch)

        assert len(result) == len(mini_batch)
        assert all(result["status"] == "fail")
        assert all(result["exit_code"] == -1)
        assert all("timed out" in m.lower() for m in result["message"])


class TestShutdown:
    def test_shutdown_runs(self) -> None:
        shutdown()
