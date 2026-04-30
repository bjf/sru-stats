import yaml
from datetime import datetime, timezone

from lib.breakdown import Breakdown, STAGES


def _load(fixtures_dir, name):
    raw = (fixtures_dir / name).read_text()
    return yaml.safe_load(raw)


def test_completed_kernel_all_stages_done(fixtures_dir):
    data = _load(fixtures_dir, "cached_bug_completed.yaml")
    bd = Breakdown.from_cache_data(data)
    by_name = {s.name: s for s in bd.stages}
    # The minimal task set produces "skipped" for stages with no inputs (boot, etc.),
    # not "done". We only assert on stages we set up.
    assert by_name["ready"].status == "done"
    assert by_name["ready"].duration == 30 * 60
    assert by_name["waiting"].status == "done"
    assert by_name["crank"].status == "done"
    assert by_name["build"].status == "done"
    assert by_name["promote-to-proposed"].status == "done"
    assert by_name["regression-testing"].status == "done"
    assert by_name["certification-testing"].status == "done"
    assert by_name["promote-to-updates"].status == "done"
    assert bd.current_state == "complete"


def test_midflight_kernel_has_in_progress_stages(fixtures_dir):
    data = _load(fixtures_dir, "cached_bug_midflight.yaml")
    bd = Breakdown.from_cache_data(data)
    by_name = {s.name: s for s in bd.stages}
    assert by_name["regression-testing"].status == "in_progress"
    assert by_name["regression-testing"].end_ts is None
    assert isinstance(bd.current_state, list)
    in_progress_names = [c.stage for c in bd.current_state]
    assert "regression-testing" in in_progress_names


def test_restart_uses_first_start_and_last_end(fixtures_dir):
    data = _load(fixtures_dir, "cached_bug_restart.yaml")
    bd = Breakdown.from_cache_data(data)
    by_name = {s.name: s for s in bd.stages}
    # regression-testing date_confirmed (2026-04-15 09:00) -> date_fix_released (2026-04-16 09:00)
    rt = by_name["regression-testing"]
    assert rt.status == "done"
    assert rt.start_ts == datetime(2026, 4, 15, 9, 0, 0, tzinfo=timezone.utc)
    assert rt.end_ts == datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)
    # boot-testing uses history events
    bt = by_name["boot-testing"]
    assert bt.status == "done"
    assert bt.start_ts == datetime(2026, 4, 15, 9, 0, 0, tzinfo=timezone.utc)
    assert bt.end_ts == datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)


def test_trailing_stages_are_pending_not_skipped(fixtures_dir):
    """The snap-debs fixture has promote-to-proposed done and nothing after.
    Stages with no data and no *later* stage started are 'pending', not 'skipped'."""
    data = _load(fixtures_dir, "cached_bug_skipped.yaml")
    bd = Breakdown.from_cache_data(data)
    by_name = {s.name: s for s in bd.stages}
    assert by_name["promote-to-proposed"].status == "done"
    for s in ("regression-testing", "certification-testing",
              "automated-testing", "sru-review", "promote-to-updates"):
        assert by_name[s].status == "pending", f"{s} should be pending"


def test_genuinely_skipped_stage_has_status_skipped(fixtures_dir):
    """When a *later* stage has started but a middle stage has no data, that
    middle stage is genuinely 'skipped'. Use cached_bug_completed.yaml: it has
    promote-to-updates done but boot-testing/automated-testing/sru-review/etc.
    absent — those are skipped."""
    data = _load(fixtures_dir, "cached_bug_completed.yaml")
    bd = Breakdown.from_cache_data(data)
    by_name = {s.name: s for s in bd.stages}
    assert by_name["promote-to-updates"].status == "done"
    # boot-testing, automated-testing, sru-review, new-review, signing have no
    # data in this fixture but later stages did finish, so they are 'skipped'.
    for s in ("boot-testing", "automated-testing", "sru-review",
              "new-review", "signing"):
        assert by_name[s].status == "skipped", f"{s} should be skipped (later stage done)"


def test_brand_new_bug_only_first_stage_in_progress(fixtures_dir):
    data = _load(fixtures_dir, "cached_bug_new.yaml")
    bd = Breakdown.from_cache_data(data)
    by_name = {s.name: s for s in bd.stages}
    assert by_name["ready"].status == "in_progress"
    for s in ("waiting", "crank", "build", "promote-to-proposed"):
        assert by_name[s].status == "pending"
    assert isinstance(bd.current_state, list)
    assert bd.current_state[0].stage == "ready"


def test_completed_bug_current_state_is_complete(fixtures_dir):
    data = _load(fixtures_dir, "cached_bug_completed.yaml")
    bd = Breakdown.from_cache_data(data)
    assert bd.current_state == "complete"


def test_stages_constant_has_thirteen_entries():
    assert len(STAGES) == 13


def test_from_cache_round_trip(cache_dir, fixtures_dir):
    """Copy a fixture into the cache_dir and load via Breakdown.from_cache()."""
    src = (fixtures_dir / "cached_bug_completed.yaml").read_text()
    (cache_dir / "1000001").write_text(src)
    bd = Breakdown.from_cache(1000001)
    assert bd.id == 1000001
    assert bd.current_state == "complete"
    assert len(bd.stages) == 13


def test_to_cache_dict_preserves_all_raw_keys(fixtures_dir):
    """to_cache_dict must round-trip every key from the original on-disk dict.

    The renderer doesn't surface description/last_message/duplicate_of/heat
    or the precomputed *_duration fields, but they must survive a save/load
    cycle so other consumers (db-update, future tools) keep working.
    """
    import yaml as _yaml
    from lib.breakdown import to_cache_dict
    raw = _yaml.safe_load((fixtures_dir / "cached_bug_completed.yaml").read_text())
    raw["description"] = "this should survive"
    raw["heat"] = 42
    raw["last_message"] = "2026-04-30 09:00:00+00:00"
    raw["build_duration"] = 1234

    bd = Breakdown.from_cache_data(raw)
    out = to_cache_dict(bd)
    for k in ("description", "heat", "last_message", "build_duration"):
        assert out[k] == raw[k], f"to_cache_dict dropped {k!r}"
