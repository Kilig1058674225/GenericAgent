"""Local skill registry for GenericAgent memory/SOP files."""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
MEMORY_DIR = PROJECT_ROOT / "memory"
REGISTRY_PATH = MEMORY_DIR / "skill_registry.json"
SUPPORTED_SUFFIXES = {".md", ".py"}
SKIP_NAMES = {
    "global_mem.txt",
    "global_mem_insight.txt",
    "file_access_stats.json",
    "skill_registry.json",
}


@dataclass
class SkillRecord:
    id: str
    title: str
    description: str
    source_path: str
    kind: str
    required_permissions: list[str]
    dependencies: list[str]
    last_verified: str | None = None
    success_count: int = 0
    failure_count: int = 0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def registry_path() -> Path:
    override = os.environ.get("GA_SKILL_REGISTRY")
    return Path(override).expanduser() if override else REGISTRY_PATH


def skill_root() -> Path:
    override = os.environ.get("GA_SKILL_ROOT")
    return Path(override).expanduser() if override else MEMORY_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def skill_id_for_path(path: Path) -> str:
    rel = _rel(path).lower()
    if rel.endswith("/skill.md"):
        rel = rel[: -len("/skill.md")]
    else:
        rel = re.sub(r"\.(md|py)$", "", rel)
    rel = re.sub(r"[^a-z0-9]+", "-", rel).strip("-")
    return rel or "skill"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_markdown_title(text: str, fallback: str) -> tuple[str, str]:
    title = fallback
    description = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip() or fallback
            continue
        if not description and not stripped.startswith((">", "```")):
            description = stripped[:240]
            break
    return title, description


def _extract_python_title(path: Path, text: str) -> tuple[str, str]:
    fallback = path.stem.replace("_", " ").title()
    try:
        doc = ast.get_docstring(ast.parse(text)) or ""
    except SyntaxError:
        doc = ""
    lines = [line.strip() for line in doc.splitlines() if line.strip()]
    if not lines:
        return fallback, ""
    return lines[0][:120], (lines[1] if len(lines) > 1 else "")[:240]


def _infer_permissions(path: Path, text: str) -> list[str]:
    haystack = f"{path.as_posix()}\n{text}".lower()
    checks = {
        "file_read": ("file_read", "open(", "read_text"),
        "file_write": ("file_write", "file_patch", "write_text", "open("),
        "command_execution": ("code_run", "subprocess", "powershell", "bash", "cmd.exe"),
        "browser_control": ("web_execute_js", "tmwebdriver", "cdp", "execute_js"),
        "network_access": ("web_scan", "requests.", "urlopen", "http://", "https://"),
        "credential_access": ("keychain", "credential", "cookie", "token", "mykey", "secret"),
        "mobile_control": ("adb", "android", "ljqctrl"),
        "messaging": ("telegram", "discord", "wechat", "wecom", "dingtalk", "slack", "feishu", "lark"),
    }
    result = []
    for permission, needles in checks.items():
        if any(needle in haystack for needle in needles):
            result.append(permission)
    return sorted(set(result))


def _infer_dependencies(text: str) -> list[str]:
    deps = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                deps.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            deps.add(node.module.split(".")[0])
    return sorted(deps)


def _candidate_paths(root: Path | None = None) -> list[Path]:
    root = root or skill_root()
    if not root.exists():
        return []
    paths = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in SKIP_NAMES:
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES and path.name.lower() != "skill.md":
            continue
        if "__pycache__" in path.parts:
            continue
        paths.append(path)
    return sorted(paths, key=lambda p: _rel(p).lower())


def discover_skills(root: Path | None = None) -> list[SkillRecord]:
    root = root or skill_root()
    records = []
    for path in _candidate_paths(root):
        text = _read_text(path)
        fallback = path.stem.replace("_", " ").title()
        if path.suffix.lower() == ".py":
            title, description = _extract_python_title(path, text)
            dependencies = _infer_dependencies(text)
            kind = "script"
        else:
            title, description = _extract_markdown_title(text, fallback)
            dependencies = []
            kind = "sop" if "sop" in path.stem.lower() else "document"
        records.append(
            SkillRecord(
                id=skill_id_for_path(path),
                title=title,
                description=description,
                source_path=_rel(path),
                kind=kind,
                required_permissions=_infer_permissions(path, text),
                dependencies=dependencies,
            )
        )
    return records


def load_registry(path: Path | None = None) -> dict[str, Any]:
    path = path or registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "updated_at": None, "skills": []}
    data.setdefault("version", 1)
    data.setdefault("updated_at", None)
    data.setdefault("skills", [])
    return data


def save_registry(data: dict[str, Any], path: Path | None = None) -> Path:
    path = path or registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["updated_at"] = _now()
    data.setdefault("version", 1)
    data.setdefault("skills", [])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _record_by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in data.get("skills", []) if item.get("id")}


def sync_registry(path: Path | None = None, *, root: Path | None = None) -> dict[str, Any]:
    data = load_registry(path)
    existing = _record_by_id(data)
    synced = []
    for discovered in discover_skills(root=root):
        item = discovered.to_dict()
        old = existing.get(discovered.id, {})
        for key in ("enabled", "success_count", "failure_count", "last_verified"):
            if key in old:
                item[key] = old[key]
        synced.append(item)
    data["skills"] = synced
    save_registry(data, path)
    return data


def list_skills(path: Path | None = None, *, include_disabled: bool = True) -> list[dict[str, Any]]:
    data = load_registry(path)
    skills = data.get("skills", [])
    if include_disabled:
        return skills
    return [item for item in skills if item.get("enabled", True)]


def set_skill_enabled(skill_id: str, enabled: bool, path: Path | None = None) -> dict[str, Any]:
    data = load_registry(path)
    for item in data.get("skills", []):
        if item.get("id") == skill_id:
            item["enabled"] = bool(enabled)
            save_registry(data, path)
            return item
    raise KeyError(f"Skill not found: {skill_id}")


def validate_registry(path: Path | None = None) -> dict[str, Any]:
    data = load_registry(path)
    now = _now()
    seen = set()
    errors = []
    warnings = []
    for item in data.get("skills", []):
        item_errors = []
        skill_id = item.get("id")
        if not skill_id:
            errors.append("skill without id")
            continue
        if skill_id in seen:
            item_errors.append(f"duplicate skill id: {skill_id}")
        seen.add(skill_id)
        source = item.get("source_path")
        if not source:
            item_errors.append(f"{skill_id}: missing source_path")
            errors.extend(item_errors)
            item["last_verified"] = now
            item["failure_count"] = int(item.get("failure_count", 0)) + 1
            continue
        source_path = (PROJECT_ROOT / source).resolve()
        if not source_path.exists():
            item_errors.append(f"{skill_id}: source missing: {source}")
        if item.get("enabled", True) and not item.get("title"):
            warnings.append(f"{skill_id}: enabled skill has no title")
        item["last_verified"] = now
        if item_errors:
            errors.extend(item_errors)
            item["failure_count"] = int(item.get("failure_count", 0)) + 1
        else:
            item["success_count"] = int(item.get("success_count", 0)) + 1
    save_registry(data, path)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "skills": len(data.get("skills", [])),
        "enabled": len([item for item in data.get("skills", []) if item.get("enabled", True)]),
    }
