import os
import re
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(s):
    return ANSI.sub("", s)


def _run(args, env=None):
    return subprocess.run(
        ["python3", *args],
        cwd=str(REPO),
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.skipif(
    not (REPO / "neo.cfg").exists() or not Path("/home/ckt.sru/data/bugs/2086331").exists(),
    reason="cache/neo.cfg not available; this test runs against the real on-disk cache",
)
def test_ktb_history_2086331_smoke():
    """Regression: ktb-history must still produce a useful breakdown for 2086331.

    Checks: bug id appears in the header, the title appears, and at least
    15 timeline lines are emitted with task/transition info. We deliberately
    do NOT byte-compare: the migrated renderer is a layout evolution; the
    contract is content equivalence, not visual equivalence.
    """
    env = {"NEO_CONFIG_FILE": str(REPO / "neo.cfg")}
    out = _strip(_run(["ktb-history", "2086331"], env=env))
    assert "2086331" in out
    assert "linux-intel-iot-realtime" in out
    rows = [ln for ln in out.splitlines() if "->" in ln and any(
        t in ln for t in ("kernel-sru-workflow", "snap-prepare", "snap-release", "prepare-package")
    )]
    assert len(rows) >= 15, f"only saw {len(rows)} timeline rows in ktb-history output"
