import os
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """A temporary cache directory wired up via NEO_CONFIG_FILE."""
    cache = tmp_path / "bugs"
    cache.mkdir()
    cfg = tmp_path / "neo.cfg"
    cfg.write_text(f"---\ntracking-bugs-cache: {cache}\n")
    monkeypatch.setenv("NEO_CONFIG_FILE", str(cfg))
    return cache


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"
