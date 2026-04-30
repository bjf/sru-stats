"""Per-bug YAML cache I/O for the sru-stats tools.

Reads the cache directory from $NEO_CONFIG_FILE -> tracking-bugs-cache.
Atomic writes via tmp-file + os.replace. No Launchpad, no rendering.
"""
import os
from pathlib import Path

import yaml


class CacheConfigError(RuntimeError):
    """NEO_CONFIG_FILE is missing or doesn't define tracking-bugs-cache."""


class CacheDirMissingError(RuntimeError):
    """The configured tracking-bugs-cache directory doesn't exist."""


_DEFAULT_CFG = str(Path(__file__).resolve().parent.parent / "neo.cfg")


def cache_dir() -> str:
    """Resolve the cache directory from $NEO_CONFIG_FILE every call.

    Falls back to <repo>/neo.cfg (the file shipped alongside the tools) when
    the env var is unset. No module-level memoization — re-resolving is
    cheap (one tiny YAML read) and lets per-test monkeypatch of
    $NEO_CONFIG_FILE work transparently.
    """
    cfg_path = os.environ.get("NEO_CONFIG_FILE") or _DEFAULT_CFG
    if not os.path.exists(cfg_path):
        raise CacheConfigError(
            f"neo.cfg not found at {cfg_path!r}. "
            f"Either create it (with a 'tracking-bugs-cache: <path>' entry) "
            f"or set $NEO_CONFIG_FILE to point at one."
        )
    with open(cfg_path) as f:
        data = yaml.safe_load(f.read()) or {}
    path = data.get("tracking-bugs-cache")
    if not path:
        raise CacheConfigError(
            f"{cfg_path} does not define 'tracking-bugs-cache'."
        )
    if not os.path.isdir(path):
        raise CacheDirMissingError(
            f"tracking-bugs-cache directory does not exist: {path}"
        )
    return str(path)


def _path(bug_id) -> Path:
    return Path(cache_dir()) / str(bug_id)


def exists(bug_id) -> bool:
    return _path(bug_id).is_file()


def load(bug_id):
    with open(_path(bug_id)) as f:
        return yaml.safe_load(f.read())


def save(bug_id, data) -> None:
    target = _path(bug_id)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=True)
        os.replace(str(tmp), str(target))
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def mtime(bug_id):
    p = _path(bug_id)
    return p.stat().st_mtime if p.is_file() else None
