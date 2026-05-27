"""File snapshots and restore helpers for safer agent writes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from safety_policy import write_audit_event
except Exception:
    write_audit_event = None


PROJECT_ROOT = Path(__file__).resolve().parent
SNAPSHOT_DIR = PROJECT_ROOT / "temp" / "snapshots"
INDEX_NAME = "snapshots.jsonl"


def snapshots_enabled() -> bool:
    return os.environ.get("GA_SNAPSHOT_MODE", "on").strip().lower() not in {"0", "off", "false", "disabled"}


def snapshot_dir() -> Path:
    override = os.environ.get("GA_SNAPSHOT_DIR")
    return Path(override).expanduser() if override else SNAPSHOT_DIR


def snapshot_index_path() -> Path:
    return snapshot_dir() / INDEX_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _append_record(record: dict[str, Any]) -> None:
    root = snapshot_dir()
    root.mkdir(parents=True, exist_ok=True)
    with open(snapshot_index_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read_records() -> list[dict[str, Any]]:
    path = snapshot_index_path()
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return records


def create_file_snapshot(target_path: str | os.PathLike[str], *, reason: str = "", tool_name: str = "") -> dict[str, Any]:
    """Snapshot a file before mutation.

    Missing targets are recorded too, so restoring the snapshot can delete a file
    that was created after the snapshot.
    """
    if not snapshots_enabled():
        return {"status": "disabled", "msg": "snapshots disabled"}

    target = Path(target_path).expanduser().resolve()
    if target.exists() and not target.is_file():
        return {"status": "error", "msg": f"snapshot target is not a file: {target}"}

    sid = _snapshot_id()
    root = snapshot_dir()
    files_dir = root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    existed = target.exists()
    snapshot_path = None
    size = None
    digest = None
    if existed:
        snapshot_path = files_dir / f"{sid}.bak"
        shutil.copy2(target, snapshot_path)
        size = target.stat().st_size
        digest = _sha256(target)

    record = {
        "id": sid,
        "timestamp": _now(),
        "target_path": str(target),
        "target_rel": _rel(target),
        "existed": existed,
        "snapshot_path": str(snapshot_path) if snapshot_path else None,
        "snapshot_rel": _rel(snapshot_path) if snapshot_path else None,
        "reason": reason,
        "tool_name": tool_name,
        "size": size,
        "sha256": digest,
    }
    _append_record(record)
    if write_audit_event:
        write_audit_event("file_snapshot", record)
    return {"status": "success", "snapshot_id": sid, "existed": existed, "target_path": str(target)}


def list_snapshots(limit: int = 20, target_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    limit = max(1, int(limit or 20))
    target = Path(target_path).expanduser().resolve() if target_path else None
    result = []
    for record in reversed(_read_records()):
        if target and Path(record.get("target_path", "")).resolve() != target:
            continue
        result.append(record)
        if len(result) >= limit:
            break
    return result


def find_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    for record in reversed(_read_records()):
        if record.get("id") == snapshot_id:
            return record
    return None


def restore_snapshot(snapshot_id: str, *, create_pre_restore_snapshot: bool = True) -> dict[str, Any]:
    record = find_snapshot(snapshot_id)
    if not record:
        return {"status": "error", "msg": f"snapshot not found: {snapshot_id}"}

    target = Path(record["target_path"]).expanduser().resolve()
    if target.exists() and not target.is_file():
        return {"status": "error", "msg": f"restore target is not a file: {target}"}

    pre_restore = None
    if create_pre_restore_snapshot and target.exists():
        pre_restore = create_file_snapshot(target, reason=f"pre_restore:{snapshot_id}", tool_name="snapshot_restore")

    if record.get("existed"):
        snapshot_path = Path(record.get("snapshot_path") or "")
        if not snapshot_path.is_file():
            return {"status": "error", "msg": f"snapshot file missing: {snapshot_path}"}
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_path, target)
        action = "restored"
    else:
        if target.exists():
            target.unlink()
        action = "deleted_created_file"

    result = {
        "status": "success",
        "snapshot_id": snapshot_id,
        "action": action,
        "target_path": str(target),
        "pre_restore_snapshot_id": pre_restore.get("snapshot_id") if isinstance(pre_restore, dict) else None,
    }
    if write_audit_event:
        write_audit_event("file_snapshot_restore", result)
    return result
