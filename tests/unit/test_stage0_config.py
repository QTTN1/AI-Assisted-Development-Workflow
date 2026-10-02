"""Unit tests for Stage 0 — config and paths."""

from __future__ import annotations

import os

import pytest

from pipeline.config import DEFAULT_CONFIG, Config, load_config
from pipeline.paths import DATA_SUBDIRS, data_root, ensure_data_dirs, raw_dir


@pytest.mark.unit
def test_default_config_train_every_n_events():
    assert DEFAULT_CONFIG.train_every_n_events == 2000
    assert DEFAULT_CONFIG.batch_size == 50


@pytest.mark.unit
def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("TRAIN_EVERY_N_EVENTS", "10")
    monkeypatch.setenv("BATCH_SIZE", "5")
    monkeypatch.setenv("CORRUPT_BATCH_RATE", "0.75")
    cfg = load_config()
    assert cfg.train_every_n_events == 10
    assert cfg.batch_size == 5
    assert cfg.corrupt_batch_rate == 0.75


@pytest.mark.unit
def test_required_data_dir_helpers(tmp_path):
    ensure_data_dirs(tmp_path)
    assert raw_dir(tmp_path).exists()
    assert raw_dir(tmp_path).name == "raw"


@pytest.mark.unit
def test_data_root_env_override(monkeypatch, tmp_path):
    custom_root = tmp_path / "shared-data"
    monkeypatch.setenv("DATA_ROOT", str(custom_root))

    assert data_root() == custom_root
    assert raw_dir() == custom_root / "raw"
    assert data_root(tmp_path) == tmp_path / "data"
