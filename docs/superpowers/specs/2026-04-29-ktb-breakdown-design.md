# ktb-breakdown — Design

**Status:** Approved (brainstorming complete)
**Date:** 2026-04-29
**Author:** Brad Figg (with Claude)
**Test bug:** 2148901

## 1. Overview

`ktb-breakdown` is a new top-level Python script in the `sru-stats` project. It takes a single Launchpad bug-id (a kernel tracking bug, KTB) as a positional argument and prints a structured breakdown of one kernel's journey through its SRU cycle.

The report contains five sections:

1. **Header** — bug id, title, owner, cycle, series/package/version, variant, master bug.
2. **Current state** — what stage(s) the kernel is in *right now* and how long it has been there.
3. **Stage summary** — one-row-per-stage table with start, end, duration, status.
4. **Detailed timeline** — line-by-line task status changes with stage annotations (the existing `ktb-history` view).
5. **Build info** — per-component, per-arch build times (the existing `ktb-buildinfo` view).

Output is ANSI-colored text by default. `--format json` emits a single machine-readable JSON object. A future Markdown generator can consume the JSON; this design does not include a Markdown renderer.

Data comes from a local YAML cache when present, otherwise from Launchpad. Live fetches are written through to the cache. Build-info data is cached in the same per-bug file. `--refresh` forces a refetch of both timeline and build data; `--no-build-info` drops the build section and skips its fetch.

This work also performs a targeted refactor: the timeline-rendering logic that lives inside `ktb-history` today is extracted to a shared library so `ktb-breakdown` and `ktb-history` cannot drift.

## 2. Architecture

Three new modules under `lib/`, each with a single responsibility:

```
lib/
  cache.py      — YAML cache I/O (load, save, exists, mtime, path resolution from neo.cfg)
  breakdown.py  — data model: a Breakdown object built from cache or Launchpad
  render.py     — text and JSON renderers that consume a Breakdown
ktb-breakdown   — new CLI: parse args, call breakdown + cache, hand to render
ktb-history     — existing CLI, migrated to use cache.py + render.py (timeline only)
```

The existing `lib/bug.py`, `lib/lp.py`, `lib/lpbug.py`, `lib/bugzdb.py`, `lib/launchpad.py` are **untouched**. `Breakdown.from_launchpad` reuses `lib.bug.Bug.load_from_lp` for the timeline portion and a refactored copy of `ktb-buildinfo`'s `SrcPackage` logic (moved into `lib/breakdown.py` as `_fetch_build_info`) for the build-info portion. No SQLite/database access is introduced or removed by this change.

### 2.1 `lib/cache.py`

Knows the cache directory (read once from `neo.cfg`'s `tracking-bugs-cache:` key). Exposes:

- `load(bug_id) -> dict` — read and `yaml.safe_load` the per-bug file.
- `save(bug_id, data)` — atomic write: serialize to `<id>.tmp`, then `os.replace()` to `<id>`.
- `exists(bug_id) -> bool`.
- `mtime(bug_id) -> float | None`.
- `cache_dir() -> str`.

No Launchpad access, no rendering. If `NEO_CONFIG_FILE` is unset, the file is missing, the `tracking-bugs-cache` key is missing, or the directory does not exist, `cache.py` raises a clear, named exception (`CacheConfigError`, `CacheDirMissingError`) that the CLI converts to a user-facing message.

### 2.2 `lib/breakdown.py`

The data layer. Defines:

- `class Stage` — declarative stage rule with start/end as either a `(task_name, date_field)` pair or a `(task:status)` history-event match.
- `STAGES = [...]` — module-level list defining the 13 stages used by the summary (see §4).
- `class Breakdown` — runtime data with both raw fields and computed views.

Constructors:

- `Breakdown.from_cache(bug_id) -> Breakdown` — load the YAML file, build the object.
- `Breakdown.from_launchpad(bug_id, with_build_info=True) -> Breakdown` — call `lib.bug.Bug.load_from_lp`, optionally call `_fetch_build_info`, return populated object.

Methods:

- `to_yaml() -> str` — serialize to the existing cache schema, extended with the two new top-level keys defined in §3.
- `_compute_stages() -> list[StageRecord]` — pure function over `tasks` + `history`, returns one record per stage in `STAGES`.
- `_compute_current_state() -> list[CurrentStateRecord] | str` — see §4.

Both computed views are recomputed on every load and never written to the cache (avoid drift).

### 2.3 `lib/render.py`

Pure rendering. Exposes:

- `render_text(breakdown, sections=ALL, color=True) -> str`
- `render_json(breakdown, sections=ALL) -> str`

Internally split into `_render_header`, `_render_current_state`, `_render_summary`, `_render_timeline`, `_render_build_info`. The color constants and the `match`-based annotation logic from `ktb-history` move here. Renderers take a `Breakdown` and return a string — no I/O, no globals.

### 2.4 `ktb-breakdown` (top-level script)

Argparse, then:

1. If cached and not `--refresh`: `Breakdown.from_cache(id)`. If `build_info` is missing and `--no-build-info` was not passed, fetch build info, merge into the breakdown, `cache.save()`.
2. Otherwise: `Breakdown.from_launchpad(id, with_build_info=not args.no_build_info)`, then `cache.save()`.
3. `render_text(...)` or `render_json(...)` to stdout.

### 2.5 `ktb-history` (migrated)

Reduced to: parse args → for each bug-id, `Breakdown.from_cache(id)` → `render_text(breakdown, sections=['header','timeline'])`. Cache-only behavior preserved. The existing rendered output must remain byte-identical (modulo ANSI normalization) — verified by an integration test against bug 2086331.

## 3. Data model and cache schema

### 3.1 On-disk YAML schema (per `<cache>/<bug-id>`)

Existing top-level keys are preserved: `id`, `title`, `owner`, `cycle`, `created`, `last_message`, `last_updated`, `description`, `duplicate_of`, `heat`, `history` (list), `tasks` (dict), plus the precomputed `*_duration` fields.

`ktb-breakdown` adds two new top-level keys, both optional:

```yaml
build_info:
  build_info_fetched_at: '2026-04-29 20:35:00+00:00'
  packages:
    linux-image-foo:
      amd64:
        created:    2024-11-28 13:30:00+00:00
        dispatched: 2024-11-28 13:31:12+00:00
        built:      2024-11-28 14:05:47+00:00
        duration:   '0:35:47'
      arm64: { ... }
    linux-modules-foo: { ... }

ktb_breakdown_fetched_at: '2026-04-29 20:35:00+00:00'
```

The schema is purely additive. `ktb-history` (cache-only, timeline-only) continues to work against files with or without these new keys. `build_info_fetched_at` and `ktb_breakdown_fetched_at` are tracked separately because timeline and build data are fetched on different schedules.

In the JSON output (§5.2), `meta.fetched_at` corresponds to `ktb_breakdown_fetched_at` (when the timeline was last refreshed); `build_info.fetched_at` corresponds to `build_info.build_info_fetched_at` on disk.

### 3.2 Runtime `Breakdown` object

Holds the raw fields plus two computed views built once at construction and discarded between runs:

- `stages: list[StageRecord]` where `StageRecord = {name, start_ts, end_ts, duration, status, assignee?}`.
- `current_state: list[CurrentStateRecord] | str` where `CurrentStateRecord = {stage, entered_at, elapsed}`.

`status` is one of `pending`, `in_progress`, `done`, `skipped`. See §4 for the rules.

## 4. Stage definitions and current-state rules

### 4.1 Stage set

Thirteen stages, defined as data in `breakdown.py` (Q5 answer D — `ktb-history`'s annotation set with `ready` and `waiting` prepended from `db-update`'s stats logic):

```python
STAGES = [
    Stage('ready',                 start=('prepare-package',     'date_created'),
                                   end  =('prepare-package',     'date_confirmed')),
    Stage('waiting',               start=('prepare-package',     'date_confirmed'),
                                   end  =('prepare-package',     'date_in_progress')),
    Stage('crank',                 start=('prepare-package',     'date_in_progress'),
                                   end  =('prepare-package',     'date_fix_committed')),
    Stage('build',                 start=('prepare-package',     'date_fix_committed'),
                                   end  =('promote-to-proposed', 'date_confirmed')),
    Stage('boot-testing',          start_history='boot-testing:Triaged',
                                   end_history  ='boot-testing:Fix Released'),
    Stage('promote-to-proposed',   start=('promote-to-proposed', 'date_in_progress'),
                                   end  =('promote-to-proposed', 'date_fix_released')),
    Stage('regression-testing',    start=('regression-testing',  'date_confirmed'),
                                   end  =('regression-testing',  'date_fix_released')),
    Stage('certification-testing', start=('certification-testing','date_confirmed'),
                                   end  =('certification-testing','date_fix_released')),
    Stage('automated-testing',     start_history='automated-testing:Incomplete',
                                   end_history  ='automated-testing:Fix Released'),
    Stage('sru-review',            start_history='sru-review:Triaged',
                                   end_history  ='sru-review:Fix Released'),
    Stage('new-review',            start_history='new-review:Triaged',
                                   end_history  ='new-review:Fix Released'),
    Stage('signing',               start_history='signing-signoff:Confirmed',
                                   end_history  ='signing-signoff:Fix Released'),
    Stage('promote-to-updates',    start=('promote-to-updates',  'date_in_progress'),
                                   end  =('promote-to-updates',  'date_fix_released')),
]
```

A stage's start/end is preferentially looked up in `bug.tasks[name].date_*`. When a task transitions through a status without storing a corresponding `date_*` field (boot-testing, automated-testing, sru-review, new-review, signing), the `start_history` / `end_history` form scans `bug.history` for the matching `task:status` event. This mirrors the logic already present in `ktb-history`.

`Stage.__init__` accepts exactly one form per endpoint: either the `(task_name, date_field)` pair via `start=`/`end=`, or the `task:status` string via `start_history=`/`end_history=`. Mixing the two for a single endpoint, or passing neither, is a constructor error caught at module import.

### 4.2 Stage status rules

- `done` — both `start_ts` and `end_ts` are present.
- `in_progress` — `start_ts` present, `end_ts` absent.
- `pending` — neither present, *and* no later stage in the list has started.
- `skipped` — neither present, but a later stage has started — common for variants that legitimately bypass certain stages (snap-debs vs. debs vs. rt).

Restart handling: a stage that re-enters its start status (e.g., regression-testing entering `Triaged` twice) reports the **first** `start_ts` and the **last** `end_ts`. The summary table reports total wall-clock; the detailed timeline still shows every individual transition.

### 4.3 Current-state rules

`current_state` is computed after `stages`:

- If exactly one stage is `in_progress`: `current_state = [{stage, entered_at, elapsed}]` (a single-element list, for shape consistency with the multi case).
- If multiple stages are `in_progress` concurrently (legitimately possible — testing stages run in parallel with promote-to-proposed): `current_state` is a list of those stages, ordered by `entered_at` ascending.
- If no stage is `in_progress` and `tasks['kernel-sru-workflow'].status == 'Fix Released'`: `current_state = 'complete'`.
- If no stage is `in_progress` and the bug is not fix-released: `current_state = 'stalled'` and the renderer additionally reports `last_activity = max(history.date-changed)`.

## 5. Output formats

### 5.1 Text (`--format text`, default)

Sections in order, separated by blank lines, ANSI-colored (suppressible with `--no-color`):

```
Bug 2148901: <series>/<package>: <version>
  Owner:        <owner>             Cycle: <cycle>
  Created:      <ts>                Last updated: <ts>
  Variant:      <debs|snap-debs|rt> Master bug:   <id-or-->

Current state
  ▸ regression-testing — in progress, 2d 4h elapsed (since 2026-04-27 16:21:48)
  ▸ certification-testing — in progress, 1d 19h elapsed (since 2026-04-27 21:00:12)

Stage summary
  Stage                    Started              Ended                Duration       Status
  ─────────────────────────────────────────────────────────────────────────────────────────
  ready                    2026-04-15 09:11:02  2026-04-15 12:33:41  3:22:39        done
  waiting                  2026-04-15 12:33:41  2026-04-16 08:01:17  19:27:36       done
  crank                    ...
  ...

Detailed timeline
  <existing ktb-history line-by-line output, exactly as today>

Build info
  Component                          Arch    Created              Dispatched           Built                Duration
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  linux-image-foo                    amd64   2026-04-16 09:15:02  2026-04-16 09:16:10  2026-04-16 11:50:33  2:35:31
  ...
  first create: <ts>   last built: <ts>   total time: <duration>
```

### 5.2 JSON (`--format json`)

A single object to stdout, no ANSI:

```json
{
  "id": 2148901,
  "title": "...",
  "owner": "...",
  "cycle": "2026.04.13",
  "series": "noble",
  "package": "linux-foo",
  "version": "...",
  "variant": "debs",
  "created": "2026-04-15T09:11:02+00:00",
  "last_updated": "...",
  "current_state": [
    {"stage": "regression-testing", "entered_at": "...", "elapsed_seconds": 187283}
  ],
  "stages": [
    {"name": "ready", "started": "...", "ended": "...",
     "duration_seconds": 12159, "status": "done"}
  ],
  "timeline": [
    {"line": 1, "timestamp": "...", "task": "kernel-sru-workflow",
     "from": "New", "to": "Confirmed", "delta_seconds": null,
     "annotation": null}
  ],
  "build_info": {
    "fetched_at": "...",
    "first_create": "...", "last_built": "...", "total_seconds": 21347,
    "packages": { "linux-image-foo": { "amd64": {...} } }
  },
  "meta": {
    "source": "cache",
    "fetched_at": "2026-04-29T20:35:00+00:00",
    "schema_version": 1
  }
}
```

All durations in JSON are integer `*_seconds`; the text renderer formats them. Timestamps are ISO-8601. `meta.source` is `cache` or `launchpad`. `meta.schema_version` is `1` for this design and bumped if the JSON shape changes.

## 6. CLI surface and fetch behavior

### 6.1 CLI

```
ktb-breakdown <bug-id>
    --refresh              force LP fetch of both timeline and build info
    --no-build-info        drop the build section; skip its fetch
    --sections LIST        csv of: header,current,summary,timeline,build (default: all)
    --format FMT           text (default) | json
    --no-color             disable ANSI in text output
    -h / --help
```

Single bug-id only in this cut. Multi-bug (`nargs='+'`) is a future addition.

### 6.2 Fetch decision tree

1. **Cached and not `--refresh`** — load from cache.
   - If `build_info` present, or `--no-build-info` passed: render.
   - Else: fetch build info, merge, `cache.save()`, render.
2. **Not cached, or `--refresh`** — fetch from Launchpad.
   - Fetch timeline always.
   - Fetch build info unless `--no-build-info`.
   - `cache.save()`, render.

`--no-build-info` *never* silently triggers a fetch; it always means "drop the section *and* skip the fetch."

### 6.3 Error handling

| Failure | Behavior |
|---|---|
| `NEO_CONFIG_FILE` unset / file missing / key missing | Message names the env var and config key, exit 2 |
| Cache dir doesn't exist | Print path + suggest checking `neo.cfg`, exit 2 |
| Bug id not numeric | argparse error, exit 2 |
| Bug not in cache, no Launchpad creds | Message + path to `~/.config/bugz`, exit 3 |
| Launchpad fetch fails (404 / auth / network) | Message with bug id + reason, exit 4 |
| Build info unavailable — build PPA inaccessible (`LaunchpadTeamNameError`, e.g. esm) **or** `ktl` (kernel-team-tools) Python module not installed | Warn to stderr, render the rest, exit 0. In text output, the build section is replaced with a one-line "(build info unavailable: <reason>)" notice. In JSON output, `build_info` is omitted and a `meta.warnings: ["build_info: <reason>"]` array is added. |
| YAML cache file corrupt | Path + parse error, exit 5; do not silently refetch |
| `--format json` and any error after partial fetch | Emit `{"error": ...}` only when partial data exists; otherwise plain stderr + non-zero exit |

The build-PPA-inaccessible case is the only place an exception is intentionally swallowed; this matches `ktb-buildinfo`'s existing behavior.

Cache writes are atomic (`<id>.tmp` + `os.replace`).

## 7. Testing

All tests under a new `tests/` directory, using `pytest`.

### 7.1 Unit tests (no network)

- `tests/test_cache.py` — `load/save/exists/mtime` against `tmp_path`. Atomic write verified by simulating mid-write failure and confirming the original file is intact.
- `tests/test_breakdown.py` — `_compute_stages()` and `_compute_current_state()` over hand-crafted fixtures in `tests/fixtures/`:
  - fully completed kernel
  - mid-flight kernel
  - kernel with regression-testing restart
  - snap-debs variant that legitimately skips stages
  - newly-created bug with only `prepare-package:date_created`
- `tests/test_render.py` — text and JSON snapshot tests against a known `Breakdown`. Text snapshots strip ANSI for stability; one separate test confirms ANSI is emitted when `color=True`. JSON snapshot is exact.

### 7.2 Integration tests (real cache dir, no network)

- `tests/test_ktb_history_compat.py` — run `ktb-history 2086331` before and after the refactor; rendered output must be byte-identical (modulo ANSI normalization). Regression net for the existing tool. The pre-refactor output is captured to `tests/fixtures/ktb_history_2086331.txt` as the *first* implementation step, before any code is moved out of `ktb-history`.
- `tests/test_ktb_breakdown_cached.py` — run `ktb-breakdown 2086331` against the existing cache; assert all five sections appear and JSON validates against a tiny inline schema.

### 7.3 Live test (manual, network required)

`tests/test_live_2148901.py`, marked `@pytest.mark.live`, skipped by default. Bug 2148901 is **not currently in the cache**, which makes it the right fixture for the live path:

1. Cache file `<cache>/2148901` is created on first run.
2. Result contains a `build_info` section with at least one package.
3. Second invocation without `--refresh` makes no Launchpad API call (verified by patching the LP client and asserting it is not invoked) and produces identical output to the first invocation. (Wall-clock timing is intentionally not asserted — too disk/CI dependent.)
4. `--refresh` updates `ktb_breakdown_fetched_at` and `build_info.build_info_fetched_at`.
5. `--no-build-info` on a fresh cache produces a report with no build section and no build fetch is attempted (verified by mocking out the build fetcher and asserting it is not called).

This live test doubles as the acceptance test for the whole feature.

### 7.4 Out of scope

- Launchpad API behavior itself.
- Network-failure recovery beyond the "exits with a clear message" assertion.
- Performance beyond the "second run is fast" check.

## 8. Out of scope (explicit)

- Multi-bug input.
- Markdown / HTML output (a future generator can consume the JSON).
- Refactoring `lib/bug.py`'s DB+LP entanglement.
- Replacing `db-update` / `stats` / `ls-cycles` / `ktb-buildinfo` as standalone tools.
- Fixing the stale `tracking-bugs-cache` path in `neo.cfg` (orthogonal; will be addressed before running `ktb-breakdown` against the existing cache, but not part of this design).
- Threshold-based highlighting in the summary table (the `config.yaml` thresholds belong to `stats`).

## 9. Open questions

None at design time. Any decisions deferred to implementation are listed in §8.
