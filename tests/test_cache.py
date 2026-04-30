import os
import yaml
import pytest

from lib import cache


def test_cache_dir_reads_from_neo_config(cache_dir):
    assert cache.cache_dir() == str(cache_dir)


def test_load_returns_parsed_yaml(cache_dir):
    (cache_dir / "1234").write_text("---\nid: 1234\ntitle: hello\n")
    data = cache.load(1234)
    assert data["id"] == 1234
    assert data["title"] == "hello"


def test_load_accepts_string_or_int_bug_id(cache_dir):
    (cache_dir / "1234").write_text("---\nid: 1234\n")
    assert cache.load("1234")["id"] == 1234


def test_exists_true_when_file_present(cache_dir):
    (cache_dir / "1234").write_text("---\n")
    assert cache.exists(1234) is True


def test_exists_false_when_missing(cache_dir):
    assert cache.exists(9999) is False


def test_save_writes_yaml(cache_dir):
    cache.save(5678, {"id": 5678, "title": "saved"})
    raw = (cache_dir / "5678").read_text()
    parsed = yaml.safe_load(raw)
    assert parsed["id"] == 5678
    assert parsed["title"] == "saved"


def test_save_is_atomic(cache_dir, monkeypatch):
    """If the rename step fails, the original file must be intact."""
    (cache_dir / "5678").write_text("---\nid: original\n")
    real_replace = os.replace

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write failure")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(RuntimeError):
        cache.save(5678, {"id": "overwritten"})

    parsed = yaml.safe_load((cache_dir / "5678").read_text())
    assert parsed["id"] == "original"
    # The temp file must have been cleaned up.
    assert not (cache_dir / "5678.tmp").exists()

    # Sanity: real os.replace works again afterward.
    monkeypatch.setattr(os, "replace", real_replace)
    cache.save(5678, {"id": "final"})
    assert yaml.safe_load((cache_dir / "5678").read_text())["id"] == "final"


def test_mtime_returns_none_when_missing(cache_dir):
    assert cache.mtime(9999) is None


def test_mtime_returns_float_when_present(cache_dir):
    (cache_dir / "1234").write_text("---\n")
    assert isinstance(cache.mtime(1234), float)


def test_missing_neo_config_file_raises(monkeypatch):
    monkeypatch.delenv("NEO_CONFIG_FILE", raising=False)
    with pytest.raises(cache.CacheConfigError):
        cache.cache_dir()


def test_missing_cache_key_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "neo.cfg"
    cfg.write_text("---\nother-key: x\n")
    monkeypatch.setenv("NEO_CONFIG_FILE", str(cfg))
    with pytest.raises(cache.CacheConfigError):
        cache.cache_dir()


def test_missing_cache_dir_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "neo.cfg"
    cfg.write_text(f"---\ntracking-bugs-cache: {tmp_path}/does-not-exist\n")
    monkeypatch.setenv("NEO_CONFIG_FILE", str(cfg))
    with pytest.raises(cache.CacheDirMissingError):
        cache.cache_dir()
