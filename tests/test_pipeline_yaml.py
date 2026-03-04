"""Tests for pipeline.yml structure and required keys."""

from pathlib import Path

import yaml
import pytest


@pytest.fixture()
def pipeline_yaml() -> dict:
    """Load pipeline.yml as a dict."""
    path = Path("pipeline.yml")
    return yaml.safe_load(path.read_text())


class TestTopLevel:
    """Verify top-level pipeline YAML structure."""

    def test_has_schema(self, pipeline_yaml: dict) -> None:
        assert "$schema" in pipeline_yaml

    def test_type_is_pipeline(self, pipeline_yaml: dict) -> None:
        assert pipeline_yaml["type"] == "pipeline"

    def test_has_jobs(self, pipeline_yaml: dict) -> None:
        assert "jobs" in pipeline_yaml


class TestValidateJob:
    """Verify the 'validate' parallel job configuration."""

    @pytest.fixture()
    def job(self, pipeline_yaml: dict) -> dict:
        return pipeline_yaml["jobs"]["validate"]

    def test_type_is_parallel(self, job: dict) -> None:
        assert job["type"] == "parallel"

    def test_dispatch_table_mode_is_direct(self, job: dict) -> None:
        assert job["inputs"]["dispatch_table"]["mode"] == "direct"

    def test_mounted_inputs_are_uri_folders(self, job: dict) -> None:
        assert job["inputs"]["sequences_store"]["type"] == "uri_folder"
        assert job["inputs"]["labels_store"]["type"] == "uri_folder"
        assert job["inputs"]["mlhc_data"]["type"] == "uri_folder"

    def test_mounted_inputs_use_ro_mount(self, job: dict) -> None:
        assert job["inputs"]["sequences_store"]["mode"] == "ro_mount"
        assert job["inputs"]["labels_store"]["mode"] == "ro_mount"
        assert job["inputs"]["mlhc_data"]["mode"] == "ro_mount"

    def test_has_append_row_to(self, job: dict) -> None:
        assert "append_row_to" in job["task"]

    def test_entry_script_is_entry_script_py(self, job: dict) -> None:
        assert job["task"]["entry_script"] == "entry_script.py"

    def test_program_arguments_include_mount_flags(self, job: dict) -> None:
        arguments = job["task"]["program_arguments"]
        assert "--sequences_mount" in arguments
        assert "--labels_mount" in arguments
        assert "--mlhc_mount" in arguments

    def test_mini_batch_size_is_string(self, job: dict) -> None:
        assert isinstance(job["mini_batch_size"], str)
