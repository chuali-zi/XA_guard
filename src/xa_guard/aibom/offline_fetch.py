"""离线包缓存解析器 — 赛题方向 3 (AIBOM 模块)。

在政企/气隙(air-gapped)安全中台中，插件安装绝不允许在运行时直接从公网拉取包。
运营方预先把所需制品镜像到本地 OFFLINE MIRROR；本模块负责将"远程包引用"
严格解析到本地缓存路径。缓存未命中时 **立即失败（fail-closed）**，
绝对不发起任何网络请求。

缓存目录布局：
    <root>/
        index.json          — 查找索引（见 INDEX_SCHEMA 注释）
        packages/           — 实际制品文件 + 可选 .sig 文件

index.json 结构：
    {
        "packages": {
            "<name>==<version>":  {"filename": "...", "sha256": "<hex>", "source_url": "...", "signature": "..."},
            "name:<name>":        {"filename": "...", "sha256": "<hex>", "source_url": "..."},
            "url:<url>":          {"filename": "...", "sha256": "<hex>", "source_url": "..."}
        }
    }
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

_CHUNK = 1024 * 1024  # 1 MiB streaming read


@dataclass
class FetchResult:
    """解析结果。available=False 时 path/sha256 为 None，errors 说明原因。"""

    available: bool
    path: Path | None = None
    sha256: str | None = None
    source: str = ""       # resolved source_url or original ref
    key: str = ""          # the index key that was matched
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Stream-hash a file with SHA-256 (no full-load into memory)."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _safe_filename(name: str) -> str:
    """Strip all path separators/components — keep only the bare filename."""
    return Path(name).name


def _guard_traversal(packages_dir: Path, filename: str) -> Path | None:
    """
    Return the resolved path only if it sits strictly inside packages_dir
    AND the stored filename is already a bare name (no directory components).

    Rejects any filename that contains path separators (``/`` or ``\\``)
    or that starts with a dot-dot segment, preventing path-traversal attacks
    regardless of OS-level path normalisation.
    """
    if not filename:
        return None

    # Reject any filename that contains a directory separator.
    # This is intentionally stricter than just taking Path.name: a mirrored
    # index should never store filenames with directory components at all.
    if "/" in filename or "\\" in filename:
        return None

    # Also reject filenames that start with "." (covers ".." as well as hidden
    # files masquerading as traversal payloads on all platforms).
    if filename.startswith("."):
        return None

    candidate = (packages_dir / filename).resolve()
    root = packages_dir.resolve()
    # Must resolve to a direct child of packages_dir (not deeper)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _load_index(index_path: Path) -> dict[str, Any]:
    """Load index.json; return empty structure if file is absent or malformed."""
    if not index_path.exists():
        return {"packages": {}}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"packages": {}}
    if not isinstance(data, dict) or "packages" not in data:
        return {"packages": {}}
    if not isinstance(data["packages"], dict):
        return {"packages": {}}
    return data


def _save_index_atomic(index_path: Path, data: dict[str, Any]) -> None:
    """Write index.json atomically via a sibling temp file + os.replace."""
    tmp = index_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, index_path)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class OfflinePackageStore:
    """
    严格离线的包缓存存储。

    resolve() 从本地 index.json 查找制品，验证 sha256 后返回本地路径。
    add()     供运营方/测试向缓存注册新制品。
    任何情况下均不发起网络请求。
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._index_path = self._root / "index.json"
        self._packages_dir = self._root / "packages"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        name: str | None = None,
        version: str | None = None,
        url: str | None = None,
        expected_sha256: str | None = None,
    ) -> FetchResult:
        """
        解析请求到缓存中的本地路径。

        查找顺序：
          1. ``<name>==<version>``  （name + version 均提供时）
          2. ``url:<url>``          （url 提供时）
          3. ``name:<name>``        （仅 name 时，模糊匹配任意版本）

        任何未命中、文件缺失、sha256 不匹配 → available=False，errors 说明原因。
        """
        index = _load_index(self._index_path)
        packages: dict[str, Any] = index.get("packages", {})

        # Build ordered candidate keys
        candidate_keys: list[str] = []
        if name and version:
            candidate_keys.append(f"{name}=={version}")
        if url:
            candidate_keys.append(f"url:{url}")
        if name:
            candidate_keys.append(f"name:{name}")

        if not candidate_keys:
            return FetchResult(
                available=False,
                errors=["resolve() requires at least one of: name, version, url"],
            )

        # Try each candidate key in order
        for key in candidate_keys:
            entry = packages.get(key)
            if entry is None:
                continue
            return self._verify_entry(key, entry, expected_sha256)

        # Nothing matched — fail closed
        tried = ", ".join(candidate_keys)
        return FetchResult(
            available=False,
            key="",
            source=url or (f"{name}=={version}" if version else name or ""),
            errors=[f"package not found in offline cache; tried keys: [{tried}]"],
        )

    def add(
        self,
        local_file: str | Path,
        *,
        name: str | None = None,
        version: str | None = None,
        url: str | None = None,
        source_url: str = "",
    ) -> FetchResult:
        """
        将本地文件注册到缓存并更新 index.json。

        - 复制文件到 packages/ 子目录。
        - 计算 sha256。
        - 原子写入 index.json。
        - 至少需要 name 或 url 之一，否则无法生成 index 键。
        """
        src = Path(local_file)
        if not src.exists():
            return FetchResult(
                available=False,
                errors=[f"source file not found: {src}"],
            )
        if not src.is_file():
            return FetchResult(
                available=False,
                errors=[f"source path is not a regular file: {src}"],
            )
        if name is None and url is None:
            return FetchResult(
                available=False,
                errors=["add() requires at least one of: name, url"],
            )

        self._packages_dir.mkdir(parents=True, exist_ok=True)

        dest_filename = src.name
        dest = self._packages_dir / dest_filename
        shutil.copy2(str(src), str(dest))

        digest = _sha256_file(dest)

        index = _load_index(self._index_path)
        packages: dict[str, Any] = index.setdefault("packages", {})

        # Build all applicable keys for this entry
        keys_to_set: list[str] = []
        if name and version:
            keys_to_set.append(f"{name}=={version}")
        if url:
            keys_to_set.append(f"url:{url}")
        if name and not version:
            keys_to_set.append(f"name:{name}")

        entry: dict[str, Any] = {
            "filename": dest_filename,
            "sha256": digest,
            "source_url": source_url,
        }

        primary_key = keys_to_set[0] if keys_to_set else f"name:{name}"
        for k in keys_to_set:
            packages[k] = entry

        _save_index_atomic(self._index_path, index)

        return FetchResult(
            available=True,
            path=dest,
            sha256=digest,
            source=source_url,
            key=primary_key,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verify_entry(
        self,
        key: str,
        entry: dict[str, Any],
        expected_sha256: str | None,
    ) -> FetchResult:
        """
        Validate a matched index entry:
          1. Filename must not escape the packages directory (path traversal guard).
          2. Cached file must exist on disk.
          3. sha256 of cached file must match index entry.
          4. If caller supplied expected_sha256, it must also match.
        """
        filename = entry.get("filename", "")
        source_url = entry.get("source_url", "")
        indexed_sha256: str = entry.get("sha256", "")

        # --- Guard: path traversal ---
        resolved_path = _guard_traversal(self._packages_dir, filename)
        if resolved_path is None:
            return FetchResult(
                available=False,
                key=key,
                source=source_url,
                errors=[
                    f"index entry '{key}' has unsafe filename '{filename}' "
                    "(path traversal rejected)"
                ],
            )

        # --- Guard: file existence ---
        if not resolved_path.exists():
            return FetchResult(
                available=False,
                key=key,
                source=source_url,
                errors=[
                    f"cached file missing for key '{key}': {resolved_path}"
                ],
            )

        # --- Guard: sha256 integrity against index ---
        actual_sha256 = _sha256_file(resolved_path)
        if indexed_sha256 and actual_sha256 != indexed_sha256:
            return FetchResult(
                available=False,
                key=key,
                source=source_url,
                errors=[
                    f"sha256 mismatch for '{key}': "
                    f"index={indexed_sha256} actual={actual_sha256}"
                ],
            )

        # --- Guard: caller-supplied expected_sha256 ---
        if expected_sha256 and actual_sha256 != expected_sha256:
            return FetchResult(
                available=False,
                key=key,
                source=source_url,
                errors=[
                    f"sha256 mismatch for '{key}': "
                    f"expected={expected_sha256} actual={actual_sha256}"
                ],
            )

        return FetchResult(
            available=True,
            path=resolved_path,
            sha256=actual_sha256,
            source=source_url,
            key=key,
        )
