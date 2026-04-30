"""Live Launchpad acceptance test for ktb-breakdown.

This test is marked `live` and skipped by default. Run with:
    pytest tests/test_live_2148901.py -v -m live

The "no Launchpad call on cache hit" and "no build fetch with --no-build-info"
assertions use mock-based verification rather than wall-clock timing or
sentinel-injection — see spec §7.3.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LIVE_BUG = "2148901"


pytestmark = pytest.mark.live


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Tmp cache directory + neo.cfg, exposed via NEO_CONFIG_FILE."""
    cache = tmp_path / "bugs"
    cache.mkdir()
    cfg = tmp_path / "neo.cfg"
    cfg.write_text("---\ntracking-bugs-cache: " + yaml.safe_dump(str(cache)).strip() + "\n")
    monkeypatch.setenv("NEO_CONFIG_FILE", str(cfg))
    return cache


def _run(args, env=None):
    return subprocess.run(
        ["python3", *args],
        cwd=str(REPO),
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _set_cache_field(path: Path, key: str, value):
    """Round-trip-safe: load YAML, set a top-level key, dump back. No string
    surgery on the raw text."""
    data = yaml.safe_load(path.read_text())
    data[key] = value
    path.write_text(yaml.safe_dump(data, sort_keys=True, default_flow_style=False))


def test_first_run_fetches_and_writes_cache(isolated_cache):
    """First invocation against a fresh cache hits Launchpad and writes through."""
    out = _run(["ktb-breakdown", "--no-color", "--no-build-info", LIVE_BUG]).stdout
    out_clean = ANSI.sub("", out)
    assert f"Bug {LIVE_BUG}" in out_clean
    cached = isolated_cache / LIVE_BUG
    assert cached.is_file(), "live fetch must write through to the cache"
    data = yaml.safe_load(cached.read_text())
    assert data["id"] == int(LIVE_BUG)
    assert "ktb_breakdown_fetched_at" in data


def test_second_run_uses_cache_and_does_not_call_launchpad(isolated_cache):
    """Spec §7.3: second run without --refresh must NOT call Launchpad.

    Strategy: pre-populate the cache by hand (no live fetch), then run the CLI
    with a sitecustomize that monkeypatches Breakdown.from_launchpad to raise.
    If the CLI calls it, the run fails; if it correctly served from cache, the
    run succeeds.
    """
    cached = isolated_cache / LIVE_BUG
    cached.write_text(yaml.safe_dump({
        "id": int(LIVE_BUG),
        "title": f"noble/linux-fixture: {LIVE_BUG}",
        "owner": "test",
        "cycle": "2026.04.13",
        "created": "2026-04-15 09:00:00+00:00",
        "last_updated": "2026-04-15 09:00:00+00:00",
        "history": [],
        "tasks": {
            "kernel-sru-workflow": {"status": "Fix Released"},
            "prepare-package": {"date_created": "2026-04-15 09:00:00+00:00"},
        },
    }, sort_keys=True))

    sitecustomize = isolated_cache.parent / "sitecustomize.py"
    sitecustomize.write_text(
        "from lib.breakdown import Breakdown\n"
        "def _boom(*a, **kw): raise RuntimeError('Launchpad must not be contacted on cache hit')\n"
        "Breakdown.from_launchpad = classmethod(_boom)\n"
    )
    env = {"PYTHONPATH": f"{isolated_cache.parent}:{REPO}"}
    out = _run(["ktb-breakdown", "--no-color", "--no-build-info", LIVE_BUG], env=env).stdout
    assert f"Bug {LIVE_BUG}" in ANSI.sub("", out)


def test_refresh_overwrites_cache(isolated_cache):
    """--refresh must replace the cached file with a freshly-fetched copy."""
    _run(["ktb-breakdown", "--no-color", "--no-build-info", LIVE_BUG])
    cached = isolated_cache / LIVE_BUG
    _set_cache_field(cached, "title", "TO_BE_OVERWRITTEN")
    assert yaml.safe_load(cached.read_text())["title"] == "TO_BE_OVERWRITTEN"
    _run(["ktb-breakdown", "--no-color", "--no-build-info", "--refresh", LIVE_BUG])
    new = yaml.safe_load(cached.read_text())
    assert new["title"] != "TO_BE_OVERWRITTEN", "--refresh must overwrite the cached file"


def test_no_build_info_does_not_emit_build_section(isolated_cache):
    out = _run(["ktb-breakdown", "--no-color", "--no-build-info", LIVE_BUG]).stdout
    assert "Build info" not in ANSI.sub("", out), \
        "--no-build-info must drop the build section entirely"


def test_no_build_info_does_not_invoke_fetch_build_info(isolated_cache):
    """Spec §7.3: --no-build-info must not call fetch_build_info."""
    sitecustomize = isolated_cache.parent / "sitecustomize.py"
    sitecustomize.write_text(
        "import lib.breakdown as _b\n"
        "def _boom(*a, **kw): raise RuntimeError('fetch_build_info must not be called when --no-build-info')\n"
        "_b.fetch_build_info = _boom\n"
    )
    env = {"PYTHONPATH": f"{isolated_cache.parent}:{REPO}"}
    out = _run(["ktb-breakdown", "--no-color", "--no-build-info", LIVE_BUG], env=env).stdout
    assert f"Bug {LIVE_BUG}" in ANSI.sub("", out)


def test_json_shape_against_live_data(isolated_cache):
    out = _run(["ktb-breakdown", "--no-build-info", "--format", "json", LIVE_BUG]).stdout
    obj = json.loads(out)
    assert obj["id"] == int(LIVE_BUG)
    assert obj["meta"]["schema_version"] == 1
    assert obj["meta"]["source"] in ("launchpad", "cache")
    assert isinstance(obj["stages"], list) and len(obj["stages"]) == 13
