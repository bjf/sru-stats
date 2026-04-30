"""Pure rendering of a Breakdown to text or JSON.

Text output is ANSI-colored, organized into named sections. JSON output is a
single object with a stable schema (meta.schema_version = 1).

No I/O. Renderers take a Breakdown, return a string.
"""
import json
from datetime import datetime, timezone
from typing import Sequence

import lib.colored as _colored

from lib.breakdown import Breakdown, StageRecord, CurrentStateRecord


ALL_SECTIONS = ("header", "current", "summary", "timeline", "build")
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Color helpers (centralized; honored only when color=True).

_CLR = {
    "title":     "yellow_1",
    "subdued":   "dark_khaki",
    "ok":        "sea_green_1a",
    "warn":      "magenta_1",
    "active":    "cyan",
    "build":     "yellow_2",
    "test":      "cyan",
    "sru":       "light_coral",
    "sign":      "light_goldenrod_3",
    "default":   "white",
    "duration":  "green",
}


def _stylize(text, name, color):
    if not color:
        return text
    return _colored.stylize(text, _colored.fg(_CLR[name]))


# ---------------------------------------------------------------------------
# Duration / timestamp formatting.

def _fmt_duration(seconds):
    if seconds is None:
        return "—"
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{sign}{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{sign}{hours:01d}:{minutes:02d}:{secs:02d}"


def _fmt_ts(dt):
    if dt is None:
        return "—"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_to_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).replace("Z", "+00:00")
    if s == "None" or s == "":
        return None
    if "T" not in s and " " in s:
        s = s.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Section renderers — text.

def _render_header_text(bd: Breakdown, color: bool) -> str:
    title_line = f"Bug {bd.id}: {bd.title}"
    out = [_stylize(title_line, "title", color)]
    out.append(f"  Owner:        {bd.owner or '—':<24} Cycle: {bd.cycle or '—'}")
    out.append(f"  Created:      {_fmt_ts(bd.created):<24} Last updated: {_fmt_ts(bd.last_updated)}")
    master = str(bd.master_bug_id) if bd.master_bug_id else "—"
    out.append(f"  Variant:      {bd.variant or '—':<24} Master bug:   {master}")
    return "\n".join(out)


def _render_current_state_text(bd: Breakdown, color: bool) -> str:
    out = [_stylize("Current state", "title", color)]
    cs = bd.current_state
    if cs == "complete":
        out.append(f"  {_stylize('▸ complete', 'ok', color)} — kernel-sru-workflow is Fix Released")
    elif cs == "stalled":
        out.append(f"  {_stylize('▸ stalled', 'warn', color)} — no stage in progress and not Fix Released")
    elif cs == "unknown":
        out.append("  ▸ unknown")
    else:  # list of CurrentStateRecord
        for c in cs:
            out.append(
                f"  {_stylize('▸ ' + c.stage, 'active', color)} — in progress, "
                f"{_fmt_duration(c.elapsed)} elapsed (since {_fmt_ts(c.entered_at)})"
            )
    return "\n".join(out)


def _render_summary_text(bd: Breakdown, color: bool) -> str:
    header = f"  {'Stage':<24} {'Started':<20} {'Ended':<20} {'Duration':<14} {'Status'}"
    rule = "  " + "─" * 89
    rows = [_stylize("Stage summary", "title", color), header, rule]
    status_color = {
        "done": "ok", "in_progress": "active", "pending": "subdued", "skipped": "subdued",
    }
    for s in bd.stages:
        row = (
            f"  {s.name:<24} {_fmt_ts(s.start_ts):<20} {_fmt_ts(s.end_ts):<20} "
            f"{_fmt_duration(s.duration):<14} {s.status}"
        )
        rows.append(_stylize(row, status_color.get(s.status, "default"), color))
    return "\n".join(rows)


def _render_timeline_text(bd: Breakdown, color: bool) -> str:
    """Detailed line-by-line timeline. Mirrors ktb-history's annotated output.

    Operates on `datetime` objects throughout so timestamps with or without
    microseconds, and with or without an explicit tz suffix, all parse via
    the tolerant _parse_to_dt helper.
    """
    out = [_stylize("Detailed timeline", "title", color)]
    if not bd.history:
        out.append("  (no history)")
        return "\n".join(out)

    lineno = 0
    prev_dt = None
    annotation_state = _AnnotationState()
    for activity in bd.history:
        what = activity.get("what-changed", "")
        if not what.endswith("status"):
            continue
        lineno += 1
        task = what.split(":", 1)[0]
        if "/" in task:
            task = task.split("/", 1)[1]
        dt = _parse_to_dt(activity.get("date-changed"))
        ts_str = _fmt_ts(dt)
        old = activity.get("old-value", "")
        new = activity.get("new-value", "")
        delta = ""
        if prev_dt is not None and dt is not None:
            delta = _fmt_duration(int((dt - prev_dt).total_seconds()))
        prev_dt = dt
        ann = annotation_state.annotate(task, new, dt)
        line = f"  {lineno:>3}  {ts_str}    {task:<28}    {old:<15} -> {new:<15}    {delta:>14}    {ann}"
        out.append(line)
    return "\n".join(out)


class _AnnotationState:
    def __init__(self):
        self.starts = {}

    def annotate(self, task, new_status, dt):
        key = f"{task}:{new_status}"
        ANNOTATIONS_START = {
            "prepare-package:In Progress":           "crank",
            "boot-testing:Triaged":                  "boot-testing",
            "promote-to-proposed:In Progress":       "promote-to-proposed",
            "promote-to-updates:In Progress":        "promote-to-updates",
            "regression-testing:Triaged":            "regression-testing",
            "regression-testing:Incomplete":         "regression-testing",
            "certification-testing:Confirmed":       "certification-testing",
            "certification-testing:Opinion":         "certification-testing",
            "certification-testing:In Progress":     "certification-testing",
            "automated-testing:Incomplete":          "automated-testing",
            "sru-review:Triaged":                    "sru-review",
            "sru-review:Confirmed":                  "sru-review",
            "new-review:Triaged":                    "new-review",
            "signing-signoff:Confirmed":             "signing",
        }
        ANNOTATIONS_END = {
            "prepare-package:Fix Committed":         ("crank", "build started"),
            "boot-testing:Fix Released":             ("boot-testing", None),
            "promote-to-proposed:Fix Released":      ("promote-to-proposed", None),
            "promote-to-updates:Fix Released":       ("promote-to-updates", None),
            "regression-testing:Fix Released":       ("regression-testing", None),
            "certification-testing:Fix Released":    ("certification-testing", None),
            "automated-testing:Fix Released":        ("automated-testing", None),
            "sru-review:Fix Released":               ("sru-review", None),
            "new-review:Fix Released":               ("new-review", None),
            "signing-signoff:Fix Released":          ("signing", None),
        }
        if key in ANNOTATIONS_START:
            label = ANNOTATIONS_START[key]
            verb = "restarted" if label in self.starts else "started"
            self.starts[label] = dt
            return f"{label} {verb}"
        if key in ANNOTATIONS_END:
            label, follow = ANNOTATIONS_END[key]
            start = self.starts.get(label)
            dur = ""
            if start is not None and dt is not None:
                dur = " (" + _fmt_duration(int((dt - start).total_seconds())) + ")"
            tail = f"; {follow}" if follow else ""
            return f"{label} finished{dur}{tail}"
        return ""


def _render_build_info_text(bd: Breakdown, color: bool) -> str:
    out = [_stylize("Build info", "title", color)]
    bi = bd.build_info or {}
    if not bi or not bi.get("packages"):
        out.append("  (no build info)")
        return "\n".join(out)
    rows = [
        f"  {'Component':<36} {'Arch':<8} {'Created':<20} {'Dispatched':<20} {'Built':<20} {'Duration':>12}",
        "  " + "─" * 119,
    ]
    first_create = None
    last_built = None
    for pkg in sorted(bi["packages"]):
        for arch, rec in sorted(bi["packages"][pkg].items()):
            created = _parse_to_dt(rec.get("created"))
            built = _parse_to_dt(rec.get("built"))
            disp = _parse_to_dt(rec.get("dispatched"))
            duration = rec.get("duration", "")
            if created and (first_create is None or first_create > created):
                first_create = created
            if built and (last_built is None or last_built < built):
                last_built = built
            rows.append(
                f"  {pkg:<36} {arch:<8} {_fmt_ts(created):<20} "
                f"{_fmt_ts(disp):<20} {_fmt_ts(built):<20} {duration:>12}"
            )
    if first_create and last_built:
        total_secs = int((last_built - first_create).total_seconds())
        rows.append("")
        rows.append(
            f"  first create: {_fmt_ts(first_create)}   last built: {_fmt_ts(last_built)}   "
            f"total time: {_fmt_duration(total_secs)}"
        )
    out.extend(rows)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Public API.

_TEXT_RENDERERS = {
    "header":   _render_header_text,
    "current":  _render_current_state_text,
    "summary":  _render_summary_text,
    "timeline": _render_timeline_text,
    "build":    _render_build_info_text,
}


def render_text(bd: Breakdown, sections: Sequence[str] = ALL_SECTIONS, color: bool = True) -> str:
    chunks = []
    for sec in sections:
        if sec not in _TEXT_RENDERERS:
            raise ValueError(f"unknown section: {sec}")
        chunks.append(_TEXT_RENDERERS[sec](bd, color))
    if bd.warnings:
        chunks.append("\n".join(f"[warn] {w}" for w in bd.warnings))
    return "\n\n".join(chunks) + "\n"


def render_json(bd: Breakdown, sections: Sequence[str] = ALL_SECTIONS) -> str:
    obj = {
        "id": bd.id,
        "title": bd.title,
        "owner": bd.owner,
        "cycle": bd.cycle,
        "series": bd.series,
        "package": bd.package,
        "version": bd.version,
        "variant": bd.variant,
        "master_bug_id": bd.master_bug_id,
        "created": _iso(bd.created),
        "last_updated": _iso(bd.last_updated),
    }
    if "current" in sections:
        cs = bd.current_state
        if isinstance(cs, list):
            obj["current_state"] = [
                {"stage": c.stage, "entered_at": _iso(c.entered_at), "elapsed_seconds": c.elapsed}
                for c in cs
            ]
        else:
            obj["current_state"] = cs
    if "summary" in sections:
        obj["stages"] = [
            {
                "name": s.name,
                "started": _iso(s.start_ts),
                "ended": _iso(s.end_ts),
                "duration_seconds": s.duration,
                "status": s.status,
            }
            for s in bd.stages
        ]
    if "timeline" in sections:
        obj["timeline"] = _timeline_json(bd)
    if "build" in sections:
        if bd.build_info and bd.build_info.get("packages"):
            obj["build_info"] = _build_info_json(bd.build_info)
    obj["meta"] = {
        "source": bd.source,
        "fetched_at": _iso(bd.fetched_at),
        "schema_version": SCHEMA_VERSION,
    }
    if bd.warnings:
        obj["meta"]["warnings"] = list(bd.warnings)
    return json.dumps(obj, indent=2, sort_keys=False)


def _timeline_json(bd: Breakdown):
    out = []
    lineno = 0
    prev_dt = None
    for activity in bd.history or []:
        what = activity.get("what-changed", "")
        if not what.endswith("status"):
            continue
        lineno += 1
        task = what.split(":", 1)[0]
        if "/" in task:
            task = task.split("/", 1)[1]
        dt = _parse_to_dt(activity.get("date-changed"))
        delta = int((dt - prev_dt).total_seconds()) if (dt and prev_dt) else None
        prev_dt = dt
        out.append({
            "line": lineno,
            "timestamp": _iso(dt),
            "task": task,
            "from": activity.get("old-value"),
            "to": activity.get("new-value"),
            "delta_seconds": delta,
        })
    return out


def _build_info_json(bi):
    fc, lb = None, None
    packages = {}
    for pkg, archs in (bi.get("packages") or {}).items():
        packages[pkg] = {}
        for arch, rec in archs.items():
            c = _parse_to_dt(rec.get("created"))
            b = _parse_to_dt(rec.get("built"))
            d = _parse_to_dt(rec.get("dispatched"))
            if c and (fc is None or fc > c):
                fc = c
            if b and (lb is None or lb < b):
                lb = b
            packages[pkg][arch] = {
                "created": _iso(c),
                "dispatched": _iso(d),
                "built": _iso(b),
                "duration_seconds": int((b - c).total_seconds()) if (b and c) else None,
            }
    return {
        "fetched_at": _iso(_parse_to_dt(bi.get("build_info_fetched_at"))),
        "first_create": _iso(fc),
        "last_built": _iso(lb),
        "total_seconds": int((lb - fc).total_seconds()) if (fc and lb) else None,
        "packages": packages,
    }
