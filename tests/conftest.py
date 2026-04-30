import os
import shutil
from pathlib import Path
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.live tests unless `-m live` was passed.

    Without this hook, the `live` marker would only work as a *selector*
    (-m live), not as an *opt-in gate*. We want live tests to be skipped
    unless explicitly requested.
    """
    # If the user explicitly selected the `live` mark, run those tests.
    markexpr = config.getoption("markexpr") or config.getini("addopts")
    if "live" in (markexpr or ""):
        return
    skip_live = pytest.mark.skip(reason="live test (use -m live to enable)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


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
