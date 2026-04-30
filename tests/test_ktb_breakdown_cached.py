import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _real_cache_has(bug_id):
    """Resolve the configured cache dir via lib.cache, no hardcoded path."""
    env = os.environ.copy()
    env["NEO_CONFIG_FILE"] = str(REPO / "neo.cfg")
    try:
        out = subprocess.run(
            ["python3", "-c",
             "from lib import cache; print(cache.cache_dir())"],
            cwd=str(REPO), env=env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        return (Path(out) / str(bug_id)).is_file()
    except Exception:
        return False


def _run(args, env=None):
    return subprocess.run(
        ["python3", *args],
        cwd=str(REPO),
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not _real_cache_has(2086331), reason="bug 2086331 not in configured cache")
def test_ktb_breakdown_2086331_text():
    env = {"NEO_CONFIG_FILE": str(REPO / "neo.cfg")}
    out = _run(["ktb-breakdown", "--no-build-info", "--no-color", "2086331"], env=env).stdout
    out_clean = ANSI.sub("", out)
    for heading in ("Bug 2086331", "Current state", "Stage summary", "Detailed timeline"):
        assert heading in out_clean, f"missing heading: {heading!r}"


@pytest.mark.skipif(not _real_cache_has(2086331), reason="bug 2086331 not in configured cache")
def test_ktb_breakdown_2086331_json():
    env = {"NEO_CONFIG_FILE": str(REPO / "neo.cfg")}
    out = _run(["ktb-breakdown", "--no-build-info", "--format", "json", "2086331"], env=env).stdout
    obj = json.loads(out)
    assert obj["id"] == 2086331
    assert isinstance(obj["stages"], list) and len(obj["stages"]) == 13
    assert obj["meta"]["source"] == "cache"
    assert obj["meta"]["schema_version"] == 1
