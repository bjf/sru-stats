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
