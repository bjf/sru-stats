import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from lib.breakdown import Breakdown
from lib.render import render_text, render_json, ALL_SECTIONS


def _bd(fixtures_dir, name):
    return Breakdown.from_cache_data(yaml.safe_load((fixtures_dir / name).read_text()))


def test_text_default_contains_all_section_headings(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    out = render_text(bd, sections=ALL_SECTIONS, color=False)
    assert "Bug 1000001" in out
    assert "Current state" in out
    assert "Stage summary" in out
    assert "Detailed timeline" in out
    # No build_info on the fixture, so:
    assert "Build info" in out
    assert "(no build info)" in out


def test_text_can_skip_sections(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    out = render_text(bd, sections=["header"], color=False)
    assert "Bug 1000001" in out
    assert "Stage summary" not in out
    assert "Detailed timeline" not in out


def test_text_color_emits_ansi(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    out = render_text(bd, sections=["header"], color=True)
    assert "\x1b[" in out


def test_text_no_color_emits_no_ansi(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    out = render_text(bd, sections=ALL_SECTIONS, color=False)
    assert "\x1b[" not in out


def test_json_shape(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_midflight.yaml")
    out = render_json(bd, sections=ALL_SECTIONS)
    obj = json.loads(out)
    assert obj["id"] == 1000002
    assert obj["meta"]["schema_version"] == 1
    assert obj["meta"]["source"] == "cache"
    # current_state is a list of in-progress stages
    assert isinstance(obj["current_state"], list)
    assert obj["current_state"][0]["stage"] == "regression-testing"
    # stages is a list of 13
    assert len(obj["stages"]) == 13
    # All durations are integers (or null)
    for s in obj["stages"]:
        assert s["duration_seconds"] is None or isinstance(s["duration_seconds"], int)
    # Timeline is a list (may be empty)
    assert isinstance(obj["timeline"], list)


def test_json_completed_current_state_is_string(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    obj = json.loads(render_json(bd, sections=ALL_SECTIONS))
    assert obj["current_state"] == "complete"


def test_json_omits_build_info_when_absent(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    obj = json.loads(render_json(bd, sections=ALL_SECTIONS))
    assert obj.get("build_info") in (None, {}, {"packages": {}})


def test_json_warnings_appear_in_meta(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_completed.yaml")
    bd.warnings.append("build_info: ktl module not installed")
    obj = json.loads(render_json(bd, sections=ALL_SECTIONS))
    assert "build_info: ktl module not installed" in obj["meta"]["warnings"]


def test_text_timeline_renders_history_rows_and_annotations(fixtures_dir):
    """Drive the timeline renderer with a fixture that has real history rows.

    cached_bug_restart.yaml has 6 status-change rows (4 regression-testing,
    2 boot-testing). We expect:
      - a row per status change
      - 'regression-testing started' on the first Triaged
      - 'regression-testing restarted' on the second Triaged
      - 'regression-testing finished' on the Fix Released row
      - 'boot-testing started' / 'boot-testing finished'
    """
    bd = _bd(fixtures_dir, "cached_bug_restart.yaml")
    out = render_text(bd, sections=["timeline"], color=False)
    # All 6 history rows make it through.
    assert out.count("->") == 6
    assert "regression-testing started" in out
    assert "regression-testing restarted" in out
    assert "regression-testing finished" in out
    assert "boot-testing started" in out
    assert "boot-testing finished" in out


def test_json_timeline_emits_iso_timestamps_and_integer_deltas(fixtures_dir):
    bd = _bd(fixtures_dir, "cached_bug_restart.yaml")
    obj = json.loads(render_json(bd, sections=["timeline"]))
    tl = obj["timeline"]
    assert len(tl) == 6
    # First row has no predecessor → delta is null.
    assert tl[0]["delta_seconds"] is None
    # Subsequent rows have integer deltas.
    for row in tl[1:]:
        assert isinstance(row["delta_seconds"], int)
    # Timestamps are ISO-8601 with explicit timezone.
    for row in tl:
        assert row["timestamp"] is not None and "T" in row["timestamp"]
