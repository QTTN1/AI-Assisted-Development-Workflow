"""Unit tests for simulator corruption."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from pipeline.config import Config
from pipeline.simulator import corrupt_batch, generate_batch, run_once


@pytest.mark.unit
def test_corrupt_batch_injects_nans_and_bad_types():
    df = generate_batch(
        20, seed=1, start_time=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    dirty = corrupt_batch(df, seed=2, row_frac=0.5)
    # At least one NaN in a numeric column (may be object dtype after mixed types)
    has_nan = dirty["distance_km"].isna().any() or dirty["prep_minutes"].isna().any()
    has_bad_type = dirty["distance_km"].astype(str).str.contains("not_a_number").any()
    assert has_nan or has_bad_type
    assert len(dirty) == len(df)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("corrupt_batch_rate", "expected_corruption"),
    [(0.0, False), (1.0, True)],
)
def test_run_once_respects_corrupt_batch_rate(
    tmp_path, corrupt_batch_rate, expected_corruption
):
    cfg = Config(batch_size=20, corrupt_batch_rate=corrupt_batch_rate)

    path = run_once(cfg=cfg, base=tmp_path)
    written = pd.read_csv(path)
    has_nan = written[["distance_km", "prep_minutes"]].isna().any().any()
    has_bad_type = written["distance_km"].astype(str).str.contains(
        "not_a_number"
    ).any()

    assert bool(has_nan or has_bad_type) is expected_corruption
