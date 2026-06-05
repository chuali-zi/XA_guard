"""单元测试 — xa_guard.aibom.offline_fetch (离线包缓存解析器)。

覆盖：
  (a) add() 后 resolve(name+version) -> available=True，sha256 正确，路径存在
  (b) resolve() 缺失包  -> available=False，有明确 error，绝不触网
  (c) sha256 不匹配（文件被篡改 或 expected_sha256 错误） -> available=False，含 mismatch error
  (d) 通过 url 键解析
  (e) index.json 中含路径穿越文件名 -> 被拒绝
  (f) index.json 不存在（空存储） -> 所有 resolve 均安全失败
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


from xa_guard.aibom.offline_fetch import OfflinePackageStore, _sha256_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(directory: Path, name: str, content: bytes = b"hello world") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_bytes(content)
    return p


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# (a) add() then resolve by name+version
# ---------------------------------------------------------------------------

class TestAddAndResolveByNameVersion:
    def test_available_true_with_correct_sha256(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "requests-2.31.0.tar.gz", b"fake-tarball-data")

        add_result = store.add(
            src,
            name="requests",
            version="2.31.0",
            source_url="https://files.pythonhosted.org/requests-2.31.0.tar.gz",
        )
        assert add_result.available is True
        assert add_result.sha256 == _sha256_bytes(b"fake-tarball-data")
        assert add_result.path is not None
        assert add_result.path.exists()

        result = store.resolve(name="requests", version="2.31.0")
        assert result.available is True
        assert result.sha256 == _sha256_bytes(b"fake-tarball-data")
        assert result.path is not None
        assert result.path.exists()
        assert result.key == "requests==2.31.0"
        assert result.errors == []

    def test_path_is_inside_packages_subdir(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "mypkg-1.0.tar.gz", b"data")
        store.add(src, name="mypkg", version="1.0")

        result = store.resolve(name="mypkg", version="1.0")
        assert result.available is True
        packages_dir = (tmp_path / "cache" / "packages").resolve()
        assert result.path is not None
        assert str(result.path.resolve()).startswith(str(packages_dir))

    def test_source_url_propagated(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "pkg-0.1.tar.gz", b"x")
        store.add(src, name="pkg", version="0.1", source_url="https://example.com/pkg.tar.gz")

        result = store.resolve(name="pkg", version="0.1")
        assert result.source == "https://example.com/pkg.tar.gz"


# ---------------------------------------------------------------------------
# (b) resolve() absent package — fail closed, no network
# ---------------------------------------------------------------------------

class TestResolveMissingPackage:
    def test_absent_name_version_returns_not_available(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        result = store.resolve(name="nonexistent", version="9.9.9")
        assert result.available is False
        assert result.path is None
        assert result.sha256 is None
        assert len(result.errors) > 0
        assert "nonexistent" in result.errors[0] or "not found" in result.errors[0]

    def test_error_message_mentions_tried_keys(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        result = store.resolve(name="requests", version="2.99.0")
        assert result.available is False
        combined = " ".join(result.errors)
        assert "requests==2.99.0" in combined or "not found" in combined

    def test_no_args_returns_error(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        result = store.resolve()
        assert result.available is False
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# (c) SHA-256 mismatch
# ---------------------------------------------------------------------------

class TestSha256Mismatch:
    def test_corrupted_cached_file_returns_not_available(self, tmp_path: Path) -> None:
        """After add(), corrupt the cached file — resolve should detect mismatch."""
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "good-1.0.tar.gz", b"original data")
        store.add(src, name="good", version="1.0")

        # Corrupt the cached file
        cached = tmp_path / "cache" / "packages" / "good-1.0.tar.gz"
        cached.write_bytes(b"corrupted content")

        result = store.resolve(name="good", version="1.0")
        assert result.available is False
        combined = " ".join(result.errors)
        assert "mismatch" in combined.lower()

    def test_wrong_expected_sha256_returns_not_available(self, tmp_path: Path) -> None:
        """Caller passes a wrong expected_sha256 — resolve should fail."""
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "pkg-2.0.tar.gz", b"real data")
        store.add(src, name="pkg", version="2.0")

        result = store.resolve(
            name="pkg",
            version="2.0",
            expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )
        assert result.available is False
        combined = " ".join(result.errors)
        assert "mismatch" in combined.lower()

    def test_correct_expected_sha256_passes(self, tmp_path: Path) -> None:
        content = b"exact match data"
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "pkg-3.0.tar.gz", content)
        store.add(src, name="pkg", version="3.0")

        good_sha = _sha256_bytes(content)
        result = store.resolve(name="pkg", version="3.0", expected_sha256=good_sha)
        assert result.available is True
        assert result.sha256 == good_sha


# ---------------------------------------------------------------------------
# (d) Resolve by URL key
# ---------------------------------------------------------------------------

class TestResolveByUrl:
    def test_add_with_url_and_resolve_by_url(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        plugin_url = "https://evil.example.com/plugin.tar.gz"
        src = _make_file(tmp_path / "src", "plugin.tar.gz", b"plugin bytes")
        store.add(src, url=plugin_url, source_url=plugin_url)

        result = store.resolve(url=plugin_url)
        assert result.available is True
        assert result.key == f"url:{plugin_url}"
        assert result.sha256 == _sha256_bytes(b"plugin bytes")
        assert result.path is not None and result.path.exists()

    def test_wrong_url_misses(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "plugin.tar.gz", b"data")
        store.add(src, url="https://good.example.com/plugin.tar.gz")

        result = store.resolve(url="https://other.example.com/plugin.tar.gz")
        assert result.available is False

    def test_add_url_only_no_name(self, tmp_path: Path) -> None:
        """URL-only entries should be retrievable without name/version."""
        store = OfflinePackageStore(tmp_path / "cache")
        url = "https://cdn.example.com/widget-0.5.whl"
        src = _make_file(tmp_path / "src", "widget-0.5.whl", b"wheel data")
        add_r = store.add(src, url=url)
        assert add_r.available is True

        result = store.resolve(url=url)
        assert result.available is True


# ---------------------------------------------------------------------------
# (e) Path traversal guard
# ---------------------------------------------------------------------------

class TestPathTraversalGuard:
    def _inject_traversal_entry(self, cache_root: Path, key: str, filename: str) -> None:
        """Directly write an entry with a malicious filename into index.json."""
        index_path = cache_root / "index.json"
        packages_dir = cache_root / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        data: dict = {"packages": {key: {"filename": filename, "sha256": "", "source_url": ""}}}
        index_path.write_text(json.dumps(data), encoding="utf-8")

    def test_dotdot_filename_rejected(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        self._inject_traversal_entry(cache, "evil==1.0", "../../../etc/passwd")
        store = OfflinePackageStore(cache)
        result = store.resolve(name="evil", version="1.0")
        assert result.available is False
        combined = " ".join(result.errors)
        assert "traversal" in combined.lower() or "unsafe" in combined.lower()

    def test_absolute_path_filename_rejected(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        self._inject_traversal_entry(cache, "evil==2.0", "/etc/shadow")
        store = OfflinePackageStore(cache)
        result = store.resolve(name="evil", version="2.0")
        assert result.available is False

    def test_subdirectory_filename_rejected(self, tmp_path: Path) -> None:
        """A filename with a directory component 'subdir/file.tar.gz' must be rejected
        as a traversal attempt — not silently flattened."""
        cache = tmp_path / "cache"
        self._inject_traversal_entry(cache, "trick==1.0", "subdir/file.tar.gz")
        store = OfflinePackageStore(cache)
        result = store.resolve(name="trick", version="1.0")
        assert result.available is False
        combined = " ".join(result.errors)
        assert "traversal" in combined.lower() or "unsafe" in combined.lower()

    def test_legitimate_filename_still_works(self, tmp_path: Path) -> None:
        """A clean filename with no traversal should pass through normally."""
        store = OfflinePackageStore(tmp_path / "cache")
        src = _make_file(tmp_path / "src", "safe-1.0.tar.gz", b"safe data")
        store.add(src, name="safe", version="1.0")

        result = store.resolve(name="safe", version="1.0")
        assert result.available is True


# ---------------------------------------------------------------------------
# (f) Missing index.json — empty store, all resolves fail closed
# ---------------------------------------------------------------------------

class TestMissingIndexJson:
    def test_fresh_cache_dir_no_index_resolves_fail(self, tmp_path: Path) -> None:
        cache = tmp_path / "empty_cache"
        cache.mkdir()
        store = OfflinePackageStore(cache)

        result = store.resolve(name="anything", version="1.0")
        assert result.available is False
        assert result.path is None

    def test_completely_absent_cache_dir_resolves_fail(self, tmp_path: Path) -> None:
        """Cache root itself doesn't exist yet — should not crash, just fail closed."""
        store = OfflinePackageStore(tmp_path / "nonexistent_cache")
        result = store.resolve(name="something", version="0.1")
        assert result.available is False

    def test_add_creates_index_and_packages_dir(self, tmp_path: Path) -> None:
        cache = tmp_path / "new_cache"
        # Do NOT create the dir — add() should create it
        store = OfflinePackageStore(cache)
        src = _make_file(tmp_path / "src", "first-1.0.tar.gz", b"data")
        result = store.add(src, name="first", version="1.0")
        assert result.available is True
        assert (cache / "index.json").exists()
        assert (cache / "packages").is_dir()

    def test_resolve_after_index_created(self, tmp_path: Path) -> None:
        cache = tmp_path / "new_cache2"
        store = OfflinePackageStore(cache)
        src = _make_file(tmp_path / "src", "pkg-1.0.tar.gz", b"content")
        store.add(src, name="pkg", version="1.0")

        result = store.resolve(name="pkg", version="1.0")
        assert result.available is True


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestSha256Helper:
    def test_sha256_file_matches_hashlib(self, tmp_path: Path) -> None:
        data = b"some deterministic content for sha test"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256_file(f) == expected

    def test_sha256_file_large_file_streams(self, tmp_path: Path) -> None:
        """Verify streaming works for files larger than one chunk."""
        data = b"X" * (1024 * 1024 * 3)  # 3 MiB
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256_file(f) == expected


# ---------------------------------------------------------------------------
# Index atomicity / multi-key test
# ---------------------------------------------------------------------------

class TestIndexAtomicity:
    def test_multiple_adds_accumulate_in_index(self, tmp_path: Path) -> None:
        store = OfflinePackageStore(tmp_path / "cache")
        for i in range(5):
            src = _make_file(tmp_path / "src", f"pkg{i}-1.0.tar.gz", f"data{i}".encode())
            store.add(src, name=f"pkg{i}", version="1.0")

        for i in range(5):
            result = store.resolve(name=f"pkg{i}", version="1.0")
            assert result.available is True, f"pkg{i} should be available"

    def test_add_both_name_version_and_url(self, tmp_path: Path) -> None:
        """A package added with both name+version and url should be resolvable via both."""
        store = OfflinePackageStore(tmp_path / "cache")
        url = "https://cdn.example.com/combo-1.5.tar.gz"
        src = _make_file(tmp_path / "src", "combo-1.5.tar.gz", b"combo data")
        store.add(src, name="combo", version="1.5", url=url)

        by_name = store.resolve(name="combo", version="1.5")
        assert by_name.available is True

        by_url = store.resolve(url=url)
        assert by_url.available is True
