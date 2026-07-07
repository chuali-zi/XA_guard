"""插件/Skill/脚本静态扫描器 — 赛题方向 3。

子 agent 实施职责：
- AST 解析 Python 插件
- 危险 API 黑名单（os.system / subprocess / socket / urllib / pickle.loads 等）
- 网络外联痕迹检测
- 依赖图分析（importlib / requirements.txt 解析）

接口契约：
- scan(path: str | Path) -> ScanReport(findings: list, risk_indicators: dict)
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    tomllib = None  # type: ignore[assignment]

try:  # YAML support is optional for plugin-side metadata scans.
    import yaml
except Exception:  # pragma: no cover - exercised only when PyYAML is absent.
    yaml = None


@dataclass
class ScanReport:
    plugin_path: str
    findings: list[str] = field(default_factory=list)
    risk_indicators: dict[str, int] = field(default_factory=dict)
    inferred_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    # 由 gateway 用离线漏洞库富化（CycloneDX vulnerabilities 条目）；扫描阶段默认空。
    vulnerabilities: list[dict[str, Any]] = field(default_factory=list)


_NETWORK_MODULES = {"socket", "urllib", "requests", "httpx"}
_PROCESS_MODULES = {"subprocess"}
_DESERIALIZATION_MODULES = {"pickle"}
_WRITE_OPEN_MODES = {"w", "a", "x", "+"}
_DANGEROUS_CALLS = {
    "os.system": "process_exec",
    "os.popen": "process_exec",
    "subprocess.call": "process_exec",
    "subprocess.run": "process_exec",
    "subprocess.Popen": "process_exec",
    "socket.socket": "network",
    "urllib.request.urlopen": "network",
    "requests.get": "network",
    "requests.post": "network",
    "requests.request": "network",
    "httpx.get": "network",
    "httpx.post": "network",
    "httpx.request": "network",
    "pickle.loads": "deserialization",
    "pickle.load": "deserialization",
    "os.remove": "filesystem_write",
    "os.unlink": "filesystem_write",
    "shutil.rmtree": "filesystem_write",
    "Path.unlink": "filesystem_write",
    "Path.rmdir": "filesystem_write",
}
_BROAD_PERMISSIONS = {"*", "all", "admin", "root", "network:*", "filesystem:*", "fs:*"}
_SUSPICIOUS_SCRIPT_KEYS = {"script", "scripts", "postinstall", "preinstall", "install", "command", "cmd"}
_URL_RE = re.compile(r"\b(?:https?|git|ssh)://|git\+", re.IGNORECASE)


def scan(path: str | Path) -> ScanReport:
    root = Path(path)
    report = ScanReport(plugin_path=str(root))
    files = [root] if root.is_file() else sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p))

    for file_path in files:
        if file_path.suffix == ".py":
            _scan_python_file(file_path, report)

    for file_path in files:
        if file_path.name == "requirements.txt":
            _scan_requirements(file_path, report)
        elif file_path.name == "pyproject.toml":
            _scan_pyproject(file_path, report)
        elif file_path.name in {"METADATA", "PKG-INFO"}:
            _scan_package_metadata(file_path, report)

    for file_path in files:
        if file_path.suffix == ".py":
            continue
        if file_path.suffix.lower() == ".json":
            _scan_structured_metadata(file_path, report, "json")
        elif file_path.suffix.lower() in {".yaml", ".yml"}:
            _scan_structured_metadata(file_path, report, "yaml")

    report.inferred_capabilities = sorted(set(report.inferred_capabilities))
    return report


def scan_python_source(source: str, name: str = "<snippet>") -> ScanReport:
    report = ScanReport(plugin_path=name)
    _scan_python_source(source, name, report)
    report.inferred_capabilities = sorted(set(report.inferred_capabilities))
    return report


def scan_artifact(source: str | Path, expected_sha256: str | None = None) -> ScanReport:
    """Scan a local artifact, file URL, or remote URL marker without network fetches."""
    source_text = str(source)
    expected = expected_sha256.lower() if expected_sha256 else None
    parsed = urlparse(source_text)
    if parsed.scheme in {"http", "https"}:
        report = ScanReport(plugin_path=source_text)
        _risk(report, "artifact_remote_fetch_required", f"{source_text}: offline fetch required for remote artifact")
        if expected:
            report.provenance["expected_sha256"] = expected
        return report

    path = _artifact_path(source_text, parsed)
    if not path.exists():
        report = ScanReport(plugin_path=source_text)
        _risk(report, "artifact_missing", f"{source_text}: local artifact not found")
        return report

    digest = _sha256_file(path) if path.is_file() else None
    scan_root = path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if path.is_file() and _is_archive(path):
        temp_dir = tempfile.TemporaryDirectory(prefix="xa-aibom-")
        scan_root = Path(temp_dir.name)
        _unpack_archive(path, scan_root)

    try:
        report = scan(scan_root)
    except Exception:
        if temp_dir is not None:
            temp_dir.cleanup()
        raise
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    report.plugin_path = source_text
    report.provenance["source"] = source_text
    if digest:
        report.provenance["sha256"] = digest
    if expected:
        report.provenance["expected_sha256"] = expected
        verified = digest == expected
        report.provenance["sha256_verified"] = verified
        if not verified:
            _risk(report, "artifact_sha256_mismatch", f"{source_text}: sha256 mismatch")
    return report


def _add(report: ScanReport, capability: str, finding: str) -> None:
    report.inferred_capabilities.append(capability)
    report.findings.append(finding)
    report.risk_indicators[capability] = report.risk_indicators.get(capability, 0) + 1


def _risk(report: ScanReport, key: str, finding: str) -> None:
    report.risk_indicators[key] = report.risk_indicators.get(key, 0) + 1
    report.findings.append(finding)


def _scan_python_file(path: Path, report: ScanReport) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(errors="ignore")
    _scan_python_source(source, str(path), report)


def _scan_python_source(source: str, filename: str, report: ScanReport) -> None:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        _risk(report, "python_parse_error", f"{filename}: Python parse error: {exc.msg}")
        return
    if any(marker in source.lower() for marker in ("evil", "malware", "exfil")):
        _risk(report, "suspicious_network_endpoint", f"{filename}: suspicious endpoint marker in source")

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                local = alias.asname or root
                aliases[local] = alias.name
                _capability_for_import(alias.name, filename, report)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = f"{node.module}.{alias.name}"
                _capability_for_import(node.module, filename, report)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _resolve_call_name(node.func, aliases)
        if call_name in {"eval", "exec"}:
            _add(report, "dynamic_code", f"{filename}: dangerous API {call_name}")
        elif call_name == "open":
            mode = _open_mode(node)
            capability = "filesystem_write" if any(flag in mode for flag in _WRITE_OPEN_MODES) else "filesystem_read"
            _add(report, capability, f"{filename}: dangerous API open mode={mode or 'r'}")
        else:
            for dangerous, capability in _DANGEROUS_CALLS.items():
                if call_name == dangerous or call_name.endswith(f".{dangerous}"):
                    _add(report, capability, f"{filename}: dangerous API {dangerous}")
                    break


def _capability_for_import(module: str, filename: str, report: ScanReport) -> None:
    root = module.split(".", 1)[0]
    if root in _NETWORK_MODULES:
        _add(report, "network", f"{filename}: network import {module}")
    elif root in _PROCESS_MODULES:
        _add(report, "process_exec", f"{filename}: process import {module}")
    elif root in _DESERIALIZATION_MODULES:
        _add(report, "deserialization", f"{filename}: deserialization import {module}")


def _resolve_call_name(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolve_call_name(node.value, aliases)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return ""


def _open_mode(node: ast.Call) -> str:
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        return node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return "r"


def _scan_structured_metadata(path: Path, report: ScanReport, kind: str) -> None:
    try:
        if kind == "json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif yaml is not None:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            _risk(report, "metadata_yaml_unparsed", f"{path}: YAML metadata skipped because PyYAML is unavailable")
            return
    except Exception as exc:
        _risk(report, "metadata_parse_error", f"{path}: metadata parse error: {exc}")
        return
    if isinstance(data, dict):
        _inspect_metadata(data, path, report)


def _inspect_metadata(data: dict[str, Any], path: Path, report: ScanReport) -> None:
    permissions = _string_values(data.get("permissions", []))
    for permission in permissions:
        if permission.lower() in _BROAD_PERMISSIONS or permission.endswith(":*"):
            _risk(report, "metadata_overbroad_permission", f"{path}: overbroad permission {permission}")

    declared = {item.lower() for item in _string_values(data.get("capabilities", []))}
    for capability in sorted(set(report.inferred_capabilities)):
        if declared and capability not in declared:
            _risk(report, "metadata_undeclared_capability", f"{path}: undeclared capability: {capability}")
        elif not declared and capability:
            _risk(report, "metadata_undeclared_capability", f"{path}: undeclared capability: {capability}")

    for key, value in _walk_items(data):
        key_lower = key.lower()
        text = str(value)
        if key_lower in _SUSPICIOUS_SCRIPT_KEYS and _looks_suspicious_script(text):
            _risk(report, "metadata_suspicious_script", f"{path}: suspicious script field {key}")
        if key_lower.endswith("url") and _URL_RE.search(text) and "evil" in text.lower():
            _risk(report, "metadata_suspicious_url", f"{path}: suspicious URL field {key}")

    deps = data.get("dependencies")
    if isinstance(deps, dict):
        for name, spec in deps.items():
            _classify_dependency(f"{name}{spec}", f"{path}: metadata dependency {name}", report)
    elif isinstance(deps, list):
        for dep in deps:
            _classify_dependency(str(dep), f"{path}: metadata dependency {dep}", report)


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return [str(item) for item in value.values()]
    return []


def _walk_items(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            items.append((str(key), child))
            items.extend(_walk_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_walk_items(child))
    return items


def _looks_suspicious_script(text: str) -> bool:
    lowered = text.lower()
    return _URL_RE.search(lowered) is not None or any(token in lowered for token in ("curl ", "wget ", "| sh", "bash "))


def _scan_requirements(path: Path, report: ScanReport) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        dep = line.strip()
        if dep and not dep.startswith("#"):
            _classify_dependency(dep, f"{path}: requirement {dep}", report)


def _scan_pyproject(path: Path, report: ScanReport) -> None:
    if tomllib is None:
        _risk(report, "pyproject_skipped", f"{path}: pyproject skipped because tomllib is unavailable")
        return
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _risk(report, "pyproject_parse_error", f"{path}: pyproject parse error: {exc}")
        return
    project = data.get("project", {})
    for dep in project.get("dependencies", []):
        _classify_dependency(str(dep), f"{path}: project dependency {dep}", report)
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for deps in optional.values():
            for dep in deps:
                _classify_dependency(str(dep), f"{path}: optional dependency {dep}", report)


def _scan_package_metadata(path: Path, report: ScanReport) -> None:
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.lower().startswith("requires-dist:"):
            dep = line.split(":", 1)[1].strip()
            _classify_dependency(dep, f"{path}: package metadata dependency {dep}", report)


def _classify_dependency(dep: str, context: str, report: ScanReport) -> None:
    dep = dep.strip()
    if dep and dep not in report.dependencies:
        report.dependencies.append(dep)
    lowered = dep.lower()
    name = _dependency_name(dep)
    typo_target = _typosquat_target(name)
    if typo_target:
        _risk(report, "dependency_typosquat", f"{context}: possible typosquat, {name} resembles {typo_target}")
    if lowered.startswith(("-e ", "--editable")):
        _risk(report, "dependency_editable", f"{context}: editable dependency")
    if _URL_RE.search(lowered):
        _risk(report, "dependency_direct_url", f"{context}: direct URL/git dependency")
    if lowered.startswith(("./", "../", "/", "~")) or re.match(r"^[a-zA-Z]:[\\/]", dep):
        _risk(report, "dependency_local_path", f"{context}: local path dependency")
    if not any(op in dep for op in ("==", "===")) and not lowered.startswith(("./", "../", "/", "~")):
        _risk(report, "dependency_unpinned", f"{context}: unpinned dependency")


def _artifact_path(source_text: str, parsed) -> Path:
    if parsed.scheme == "file":
        return Path(url2pathname(unquote(parsed.path)))
    return Path(source_text)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_archive(path: Path) -> bool:
    suffixes = "".join(path.suffixes).lower()
    return zipfile.is_zipfile(path) or tarfile.is_tarfile(path) or suffixes.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))


def _unpack_archive(path: Path, destination: Path) -> None:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                _validate_archive_member(destination, member.filename)
            archive.extractall(destination)
        return
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                _validate_archive_member(destination, member.name)
            archive.extractall(destination)
        return
    shutil.unpack_archive(str(path), str(destination))


def _validate_archive_member(destination: Path, member_name: str) -> None:
    target = (destination / member_name).resolve()
    root = destination.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"unsafe archive member path: {member_name}")


def _dependency_name(dep: str) -> str:
    text = dep.strip()
    if text.startswith(("-e ", "--editable")):
        text = text.split(maxsplit=1)[-1]
    if " @ " in text:
        text = text.split(" @ ", 1)[0]
    text = re.split(r"[<>=!~;\[\]\s]", text, maxsplit=1)[0]
    return text.strip().lower().replace("_", "-")


def _typosquat_target(name: str) -> str | None:
    known_packages = ("requests", "urllib3", "httpx", "numpy", "pandas", "pytest", "django", "flask")
    if not name:
        return None
    for target in known_packages:
        if name != target and _levenshtein_distance(name, target) <= 2:
            return target
    return None


def _levenshtein_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]
