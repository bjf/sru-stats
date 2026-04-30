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
