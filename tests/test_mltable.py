"""Tests for MLTable parsing and dispatch CSV schema."""

import pandas as pd
import pytest
from mltable import load


@pytest.fixture()
def dispatch_df() -> pd.DataFrame:
    """Load the MLTable from pipeline/data/ and return as DataFrame."""
    tbl = load("data")
    return tbl.to_pandas_dataframe()


EXPECTED_COLUMNS = ["sequence_path", "label_path", "third_data_path"]


class TestMLTableSchema:
    """Verify the MLTable parses the dispatch CSV correctly."""

    def test_loads_as_dataframe(self, dispatch_df: pd.DataFrame) -> None:
        assert isinstance(dispatch_df, pd.DataFrame)

    def test_column_names(self, dispatch_df: pd.DataFrame) -> None:
        assert list(dispatch_df.columns) == EXPECTED_COLUMNS

    def test_row_count_matches_csv(self, dispatch_df: pd.DataFrame) -> None:
        # sample_dispatch.csv has 3 data rows
        csv_df = pd.read_csv("data/sample_dispatch.csv")
        assert len(dispatch_df) == len(csv_df)

    def test_all_cells_are_non_empty_strings(self, dispatch_df: pd.DataFrame) -> None:
        for col in EXPECTED_COLUMNS:
            for val in dispatch_df[col]:
                assert isinstance(val, str)
                assert len(val.strip()) > 0
