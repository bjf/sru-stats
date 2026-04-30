"""Data model for one kernel's SRU breakdown.

Builds a Breakdown object from either the YAML cache or live Launchpad.
Computes `stages` (one record per Stage in STAGES) and `current_state`
(in_progress stages, or 'complete' / 'stalled') as pure functions over
the raw fields.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Tuple, Union, List, Dict, Any


# A stage's start/end can be either:
#   - a (task_name, date_field) pair, looked up in tasks[name].<date_field>
#   - a "task:status" string, scanned for in history events
TaskDate = Tuple[str, str]
HistoryEvent = str


@dataclass(frozen=True)
class Stage:
    name: str
    start: Optional[TaskDate] = None
    end: Optional[TaskDate] = None
    start_history: Optional[HistoryEvent] = None
    end_history: Optional[HistoryEvent] = None

    def __post_init__(self):
        # XOR: each endpoint must be specified exactly once.
        if (self.start is None) == (self.start_history is None):
            raise ValueError(
                f"Stage {self.name!r}: must specify exactly one of start= or start_history=")
        if (self.end is None) == (self.end_history is None):
            raise ValueError(
                f"Stage {self.name!r}: must specify exactly one of end= or end_history=")


STAGES: List[Stage] = [
    Stage("ready",
          start=("prepare-package", "date_created"),
          end=("prepare-package", "date_confirmed")),
    Stage("waiting",
          start=("prepare-package", "date_confirmed"),
          end=("prepare-package", "date_in_progress")),
    Stage("crank",
          start=("prepare-package", "date_in_progress"),
          end=("prepare-package", "date_fix_committed")),
    Stage("build",
          start=("prepare-package", "date_fix_committed"),
          end=("promote-to-proposed", "date_confirmed")),
    Stage("boot-testing",
          start_history="boot-testing:Triaged",
          end_history="boot-testing:Fix Released"),
    Stage("promote-to-proposed",
          start=("promote-to-proposed", "date_in_progress"),
          end=("promote-to-proposed", "date_fix_released")),
    Stage("regression-testing",
          start=("regression-testing", "date_confirmed"),
          end=("regression-testing", "date_fix_released")),
    Stage("certification-testing",
          start=("certification-testing", "date_confirmed"),
          end=("certification-testing", "date_fix_released")),
    Stage("automated-testing",
          start_history="automated-testing:Incomplete",
          end_history="automated-testing:Fix Released"),
    Stage("sru-review",
          start_history="sru-review:Triaged",
          end_history="sru-review:Fix Released"),
    Stage("new-review",
          start_history="new-review:Triaged",
          end_history="new-review:Fix Released"),
    Stage("signing",
          start_history="signing-signoff:Confirmed",
          end_history="signing-signoff:Fix Released"),
    Stage("promote-to-updates",
          start=("promote-to-updates", "date_in_progress"),
          end=("promote-to-updates", "date_fix_released")),
]


@dataclass
class StageRecord:
    name: str
    start_ts: Optional[datetime]
    end_ts: Optional[datetime]
    duration: Optional[int]            # seconds, integer
    status: str                        # done | in_progress | pending | skipped


@dataclass
class CurrentStateRecord:
    stage: str
    entered_at: datetime
    elapsed: int                       # seconds, integer


@dataclass
class Breakdown:
    id: int
    title: str = ""
    owner: str = ""
    cycle: str = ""
    series: Optional[str] = None
    package: Optional[str] = None
    version: Optional[str] = None
    variant: str = ""
    master_bug_id: Optional[int] = None
    created: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    tasks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    build_info: Optional[Dict[str, Any]] = None       # populated by fetch_build_info
    fetched_at: Optional[datetime] = None
    source: str = "cache"                             # "cache" | "launchpad"
    warnings: List[str] = field(default_factory=list)

    # Computed views — populated lazily.
    stages: List[StageRecord] = field(default_factory=list)
    current_state: Union[List[CurrentStateRecord], str] = "unknown"

    # The original on-disk dict, preserved so re-serialization round-trips
    # every key (description, last_message, duplicate_of, heat, *_duration,
    # etc.) — not just the ones the renderer surfaces. Set by from_cache_data
    # and from_launchpad. Unused for purely-computed Breakdown instances
    # built in tests.
    _raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Compute logic — pure functions over tasks + history.

from datetime import timedelta


def _parse_ts(value):
    """Parse a timestamp from a cached bug. Cached YAML uses two flavors:
    Python str(datetime) -> '2024-11-01 10:29:57.576549+00:00', and the special
    sentinel string 'None' or actual None. Return a tz-aware datetime or None.
    """
    if value is None or value == "None" or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    s = str(value).replace("Z", "+00:00")
    if "T" not in s and " " in s:
        s = s.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _now():
    return datetime.now(timezone.utc)


def _lookup_task_date(tasks, task_name, field_name):
    task = tasks.get(task_name)
    if not task:
        return None
    return _parse_ts(task.get(field_name))


def _lookup_history_event(history, event):
    """Return (first_ts, last_ts) for the given task:status event, or (None, None)."""
    task_name, status = event.split(":", 1)
    matches = []
    for entry in history or []:
        what = entry.get("what-changed", "")
        if not what.endswith("status"):
            continue
        entry_task = what.split(":", 1)[0]
        if "/" in entry_task:
            entry_task = entry_task.split("/", 1)[1]
        if entry_task != task_name:
            continue
        if entry.get("new-value") != status:
            continue
        ts = _parse_ts(entry.get("date-changed"))
        if ts is not None:
            matches.append(ts)
    if not matches:
        return None, None
    return min(matches), max(matches)


def _stage_endpoints(stage, tasks, history):
    """Return (start_ts, end_ts) for a stage."""
    if stage.start is not None:
        start_ts = _lookup_task_date(tasks, *stage.start)
    else:
        start_ts, _ = _lookup_history_event(history, stage.start_history)
    if stage.end is not None:
        end_ts = _lookup_task_date(tasks, *stage.end)
    else:
        _, end_ts = _lookup_history_event(history, stage.end_history)
    return start_ts, end_ts


def _compute_stages(tasks, history):
    """Compute one StageRecord per stage in STAGES."""
    raw = []
    for stage in STAGES:
        start_ts, end_ts = _stage_endpoints(stage, tasks, history)
        raw.append((stage, start_ts, end_ts))

    # Status pass: a stage with no data is 'skipped' if any later stage has
    # started, otherwise 'pending'.
    later_started = [False] * len(raw)
    for i in range(len(raw) - 1, -1, -1):
        _, s, _ = raw[i]
        later_started[i] = (s is not None) or (i + 1 < len(raw) and later_started[i + 1])

    out = []
    for i, (stage, start_ts, end_ts) in enumerate(raw):
        if start_ts and end_ts:
            status = "done"
            duration = int((end_ts - start_ts).total_seconds())
        elif start_ts and not end_ts:
            status = "in_progress"
            duration = None
        elif not start_ts and not end_ts:
            later = i + 1 < len(raw) and later_started[i + 1]
            status = "skipped" if later else "pending"
            duration = None
        else:
            status = "done"
            duration = 0
        out.append(StageRecord(
            name=stage.name,
            start_ts=start_ts,
            end_ts=end_ts,
            duration=duration,
            status=status,
        ))
    return out


def _compute_current_state(stages_records, tasks, history):
    in_progress = [r for r in stages_records if r.status == "in_progress"]
    if in_progress:
        in_progress.sort(key=lambda r: r.start_ts)
        now = _now()
        return [
            CurrentStateRecord(
                stage=r.name,
                entered_at=r.start_ts,
                elapsed=int((now - r.start_ts).total_seconds()),
            )
            for r in in_progress
        ]
    workflow = (tasks or {}).get("kernel-sru-workflow", {})
    if workflow.get("status") == "Fix Released":
        return "complete"
    return "stalled"


def _from_cache_data(cls, data):
    bd = cls(id=int(data.get("id", 0)))
    bd.title = data.get("title", "") or ""
    bd.owner = data.get("owner", "") or ""
    bd.cycle = data.get("cycle", "") or ""
    bd.series = data.get("series")
    bd.package = data.get("package")
    bd.version = data.get("version")
    bd.variant = data.get("variant", "") or ""
    bd.master_bug_id = data.get("master_bug_id")
    bd.created = _parse_ts(data.get("created"))
    bd.last_updated = _parse_ts(data.get("last_updated"))
    bd.tasks = data.get("tasks") or {}
    bd.history = data.get("history") or []
    bd.build_info = data.get("build_info")
    bd.fetched_at = _parse_ts(data.get("ktb_breakdown_fetched_at"))
    bd.source = "cache"
    bd._raw = dict(data)
    bd.stages = _compute_stages(bd.tasks, bd.history)
    bd.current_state = _compute_current_state(bd.stages, bd.tasks, bd.history)
    return bd


Breakdown.from_cache_data = classmethod(_from_cache_data)


from . import cache as _cache_module


def _from_cache(cls, bug_id):
    return cls.from_cache_data(_cache_module.load(bug_id))


Breakdown.from_cache = classmethod(_from_cache)


# ---------------------------------------------------------------------------
# Live Launchpad path.

_EPOCH = datetime(2009, 3, 2, 0, 0, tzinfo=timezone.utc)


def _epoch_to_str(value):
    """lib.bug stores date_* as seconds-since-epoch ints. Convert to a string
    matching the on-disk schema."""
    if not value:
        return None
    if isinstance(value, str):
        return value
    return str(_EPOCH + timedelta(seconds=int(value)))


def _ts_to_str(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(_EPOCH + timedelta(seconds=int(value)))
    return str(value)


def _activity_to_history(activity_entries):
    """Convert lpbug.activity entries to the cached YAML 'history' shape."""
    out = []
    for a in activity_entries:
        out.append({
            "date-changed": str(a.datechanged),
            "what-changed": a.whatchanged,
            "old-value": a.oldvalue,
            "new-value": a.newvalue,
            "message": getattr(a, "message", None),
            "who": a.person.display_name if getattr(a, "person", None) else None,
        })
    return out


def _tasks_to_dict(tasks):
    out = {}
    for name, t in (tasks or {}).items():
        out[name] = {
            "id": getattr(t, "id", None),
            "name": getattr(t, "name", name),
            "assignee": getattr(t, "assignee", "") or "",
            "status": getattr(t, "status", "") or "",
            "importance": getattr(t, "importance", "") or "",
            "owner": getattr(t, "owner", "") or "",
            "owner_display_name": getattr(t, "owner_display_name", "") or "",
            "title": getattr(t, "title", "") or "",
            "milestone": getattr(t, "milestone", "") or "",
            "is_complete": getattr(t, "is_complete", False),
            "date_created":       _epoch_to_str(getattr(t, "date_created", 0)),
            "date_confirmed":     _epoch_to_str(getattr(t, "date_confirmed", 0)),
            "date_assigned":      _epoch_to_str(getattr(t, "date_assigned", 0)),
            "date_triaged":       _epoch_to_str(getattr(t, "date_triaged", 0)),
            "date_in_progress":   _epoch_to_str(getattr(t, "date_in_progress", 0)),
            "date_closed":        _epoch_to_str(getattr(t, "date_closed", 0)),
            "date_fix_committed": _epoch_to_str(getattr(t, "date_fix_committed", 0)),
            "date_fix_released":  _epoch_to_str(getattr(t, "date_fix_released", 0)),
            "date_incomplete":    _epoch_to_str(getattr(t, "date_incomplete", 0)),
            "date_left_closed":   _epoch_to_str(getattr(t, "date_left_closed", 0)),
            "date_left_new":      _epoch_to_str(getattr(t, "date_left_new", 0)),
        }
    return out


def _bug_to_dict(bug, lpbug=None):
    """Convert a lib.bug.Bug populated via load_from_lp into the on-disk YAML schema.

    `lpbug` is the underlying launchpadlib bug object — used to extract the
    activity list into `history`. lib.bug.Bug doesn't stash this on the
    instance, so callers must pass it explicitly.
    """
    return {
        "id": int(bug.id),
        "title": bug.title or "",
        "owner": bug.owner or "",
        "cycle": bug.cycle or "",
        "series": bug.series,
        "package": bug.package,
        "version": bug.version,
        "variant": bug.variant or "",
        "master_bug_id": bug.master_bug_id or None,
        "created": _ts_to_str(bug.created),
        "last_message": _ts_to_str(bug.last_message),
        "last_updated": _ts_to_str(bug.last_updated),
        "duplicate_of": bug.duplicate or None,
        "description": bug.description or "",
        "history": _activity_to_history(lpbug.activity) if lpbug is not None else [],
        "tasks": _tasks_to_dict(bug.tasks),
    }


class BuildInfoUnavailable(Exception):
    """Raised when build info cannot be fetched. Wraps every underlying
    failure (missing ktl, inaccessible PPA, no series/package, network)
    so callers have a single exception type to handle."""


def _from_launchpad(cls, bug_id, with_build_info=True, lp=None):
    """Fetch a bug from Launchpad, build a Breakdown.

    Build-info fetch is attempted only when `with_build_info=True`. If the
    `ktl` module is unavailable, the build PPA is inaccessible, or any
    per-PPA fetch raises, `bd.warnings` records the reason and
    `bd.build_info` is left None.
    """
    from lib.bug import Bug
    from lib.launchpad import Launchpad
    if lp is None:
        lp = Launchpad("bugz")
    lpbug = lp.service.bugs[int(bug_id)]
    bug = Bug().load_from_lp(int(bug_id), lp=lp)
    data = _bug_to_dict(bug, lpbug=lpbug)
    bd = cls.from_cache_data(data)
    bd.source = "launchpad"
    bd.fetched_at = _now()
    if with_build_info:
        try:
            bd.build_info = fetch_build_info(bd)
        except BuildInfoUnavailable as e:
            bd.warnings.append(f"build_info: {e}")
    return bd


Breakdown.from_launchpad = classmethod(_from_launchpad)


def fetch_build_info(bd):
    """Fetch per-component build info from Launchpad. Requires the `ktl` module.

    Raises BuildInfoUnavailable when ktl is missing, no accessible build PPA
    is configured, or the bug has no series/package yet.
    """
    if not bd.series or not bd.package:
        raise BuildInfoUnavailable("bug has no series/package yet")
    try:
        # lib.lp imports ktl.kernel_series at the top of the file. If ktl is
        # not installed, the import fails and we report it as unavailable.
        from lib.lp import KTB, LP
    except ImportError:
        raise BuildInfoUnavailable("ktl module not installed")
    except Exception as e:
        raise BuildInfoUnavailable(f"lib.lp import failed: {e}")

    try:
        ktb = KTB(int(bd.id))
        pv = ktb.packages_and_versions
        info = {}
        launchpad = LP().launchpad
        skipped_ppas = []
        for pkg_name, version in pv.items():
            for ppa in ktb.build_ppas:
                team_name, ppa_name = ppa
                # esm PPAs are private to engineers; the Launchpad client used
                # here can't see them. Skip and try the next PPA in the routing
                # list — esm only blocks build info if every PPA is esm.
                if "esm" in team_name:
                    skipped_ppas.append(team_name)
                    continue
                team = launchpad.people[team_name]
                ppa_obj = team.getPPAByName(name=ppa_name)
                ubuntu = launchpad.distributions("ubuntu")
                lp_series = ubuntu.getSeries(name_or_version=ktb.series)
                psrc = ppa_obj.getPublishedSources(
                    distro_series=lp_series, source_name=pkg_name,
                    exact_match=True, order_by_date=True,
                )
                matched = None
                for p in psrc:
                    if p.source_package_version == version:
                        matched = p
                        break
                if matched is None:
                    continue
                builds = matched.getBuilds()
                pkg_record = info.setdefault(pkg_name, {})
                for build in builds:
                    duration = build.datebuilt - build.datecreated if (build.datebuilt and build.datecreated) else None
                    pkg_record[build.arch_tag] = {
                        "arch": build.arch_tag,
                        "created": str(build.datecreated) if build.datecreated else None,
                        "dispatched": str(build.date_first_dispatched) if build.date_first_dispatched else None,
                        "built": str(build.datebuilt) if build.datebuilt else None,
                        "duration": str(duration).split(".", 1)[0] if duration else None,
                    }
                break  # first matching, accessible PPA wins
        if not info:
            if skipped_ppas:
                raise BuildInfoUnavailable(
                    f"all build PPAs were inaccessible: {', '.join(skipped_ppas)}"
                )
            raise BuildInfoUnavailable("no published sources matched")
        return {
            "build_info_fetched_at": str(_now()),
            "packages": info,
        }
    except BuildInfoUnavailable:
        raise
    except Exception as e:
        raise BuildInfoUnavailable(str(e))


def to_cache_dict(bd):
    """Serialize a Breakdown back to the on-disk YAML schema.

    Preserves every key from the original on-disk dict (`bd._raw`) so that
    keys the renderer doesn't surface — description, last_message,
    duplicate_of, heat, *_duration — survive a round trip. The two
    ktb-breakdown-managed keys (build_info, ktb_breakdown_fetched_at) are
    overwritten with the live values from the Breakdown.
    """
    out = dict(bd._raw) if bd._raw else {}
    out["id"] = int(bd.id)
    if bd.title:
        out.setdefault("title", bd.title)
    if bd.fetched_at is not None:
        out["ktb_breakdown_fetched_at"] = str(bd.fetched_at)
    if bd.build_info is not None:
        out["build_info"] = bd.build_info
    return out
