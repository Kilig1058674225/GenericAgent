"""Reusable local verification checks for GenericAgent development."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
SECRET_KEY_MARKERS = ("api_key", "apikey", "secret", "token", "password", "cookie", "authorization")
LIKELY_SECRET_PATTERNS = (
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|secret|token|password|cookie|authorization)\b"
            r"\s*[:=]\s*['\"]([A-Za-z0-9._~+/=-]{16,})['\"]?"
        ),
    ),
    (
        "env_secret_assignment",
        re.compile(
            r"(?im)^\s*(?:export\s+)?[A-Za-z_]*(api[_-]?key|apikey|secret|token|password|cookie|authorization)[A-Za-z_]*"
            r"\s*=\s*([A-Za-z0-9._~+/=-]{16,})\s*$"
        ),
    ),
    ("openai_style_key", re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
)
PLACEHOLDER_MARKERS = ("<your", "your-", "dummy", "placeholder", "example", "xxxxx", "redacted", "changeme")


def _is_secret_key(key: Any) -> bool:
    text = str(key).strip().lower().replace("-", "_")
    return any(marker in text for marker in SECRET_KEY_MARKERS)


def _is_usable_secret(value: str) -> bool:
    text = value.strip()
    if len(text) < 8:
        return False
    lowered = text.lower()
    if not text or text == "[REDACTED]":
        return False
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return False
    return True


def _value_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if _is_usable_secret(value) else []
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_value_strings(item))
        return strings
    if isinstance(value, (list, tuple, set)):
        strings: list[str] = []
        for item in value:
            strings.extend(_value_strings(item))
        return strings
    return []


def _collect_secret_values_from_config(value: Any, key_is_secret: bool = False) -> list[str]:
    if key_is_secret:
        return _value_strings(value)
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            strings.extend(_collect_secret_values_from_config(item, _is_secret_key(key)))
        return strings
    if isinstance(value, (list, tuple, set)):
        strings: list[str] = []
        for item in value:
            strings.extend(_collect_secret_values_from_config(item, False))
        return strings
    return []


def collect_configured_secret_values(mykeys: dict[str, Any] | None = None, environ: dict[str, str] | None = None) -> list[str]:
    """Collect configured secret values without exposing them in output."""
    values: set[str] = set()
    if mykeys is None:
        try:
            from llmcore import reload_mykeys

            mykeys = reload_mykeys()[0]
        except Exception:
            mykeys = {}
    for key, value in (mykeys or {}).items():
        values.update(_collect_secret_values_from_config(value, _is_secret_key(key)))
    for key, value in (environ or os.environ).items():
        if _is_secret_key(key):
            values.update(_value_strings(value))
    return sorted(values)


def git_tracked_files(project_dir: str | os.PathLike[str] = PROJECT_ROOT) -> list[Path]:
    return git_candidate_files(project_dir, include_untracked=False)


def git_candidate_files(project_dir: str | os.PathLike[str] = PROJECT_ROOT, *, include_untracked: bool = True) -> list[Path]:
    root = Path(project_dir)
    args = ["git", "ls-files", "-z", "--cached"]
    if include_untracked:
        args.extend(["--others", "--exclude-standard"])
    result = subprocess.run(
        args,
        cwd=root,
        capture_output=True,
        timeout=20,
    )
    if result.returncode != 0:
        return []
    names = [name for name in result.stdout.decode("utf-8", errors="replace").split("\0") if name]
    return [root / name for name in names]


def scan_files_for_values(
    values: list[str],
    files: list[Path],
    project_dir: str | os.PathLike[str] = PROJECT_ROOT,
) -> list[dict[str, str]]:
    root = Path(project_dir).resolve()
    matches: list[dict[str, str]] = []
    encoded_values = [(value, value.encode("utf-8")) for value in values if value]
    if not encoded_values:
        return matches
    for path in files:
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue
        for value, needle in encoded_values:
            if needle in data:
                try:
                    rel = str(Path(path).resolve().relative_to(root))
                except ValueError:
                    rel = str(path)
                matches.append(
                    {
                        "path": rel,
                        "secret_id": hashlib.sha256(value.encode("utf-8")).hexdigest()[:10],
                    }
                )
    return matches


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _match_secret_text(match: re.Match[str]) -> str:
    for item in reversed(match.groups()):
        if item:
            return item
    return match.group(0)


def scan_files_for_likely_secrets(
    files: list[Path],
    project_dir: str | os.PathLike[str] = PROJECT_ROOT,
) -> list[dict[str, str]]:
    root = Path(project_dir).resolve()
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, int, str]] = set()
    for path in files:
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for kind, pattern in LIKELY_SECRET_PATTERNS:
            for match in pattern.finditer(text):
                secret_text = _match_secret_text(match)
                if not _is_usable_secret(secret_text):
                    continue
                try:
                    rel = str(Path(path).resolve().relative_to(root))
                except ValueError:
                    rel = str(path)
                line = _line_number(text, match.start())
                secret_id = hashlib.sha256(secret_text.encode("utf-8")).hexdigest()[:10]
                key = (rel, line, secret_id)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    {
                        "path": rel,
                        "line": str(line),
                        "kind": kind,
                        "secret_id": secret_id,
                    }
                )
    return matches


def scan_candidate_files_for_configured_secrets(project_dir: str | os.PathLike[str] = PROJECT_ROOT) -> list[dict[str, str]]:
    return scan_files_for_values(
        collect_configured_secret_values(),
        git_candidate_files(project_dir),
        project_dir,
    )


def scan_candidate_files_for_likely_secrets(project_dir: str | os.PathLike[str] = PROJECT_ROOT) -> list[dict[str, str]]:
    return scan_files_for_likely_secrets(
        git_candidate_files(project_dir),
        project_dir,
    )


def scan_tracked_files_for_configured_secrets(project_dir: str | os.PathLike[str] = PROJECT_ROOT) -> list[dict[str, str]]:
    return scan_files_for_values(
        collect_configured_secret_values(),
        git_tracked_files(project_dir),
        project_dir,
    )


def scan_tracked_files_for_likely_secrets(project_dir: str | os.PathLike[str] = PROJECT_ROOT) -> list[dict[str, str]]:
    return scan_files_for_likely_secrets(
        git_tracked_files(project_dir),
        project_dir,
    )
