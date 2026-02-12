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

    def test_has_append_row_to(self, job: dict) -> None:
        assert "append_row_to" in job["task"]

    def test_entry_script_is_entry_script_py(self, job: dict) -> None:
        assert job["task"]["entry_script"] == "entry_script.py"

    def test_mini_batch_size_is_string(self, job: dict) -> None:
        assert isinstance(job["mini_batch_size"], str)
