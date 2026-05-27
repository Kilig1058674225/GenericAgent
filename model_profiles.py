"""Safe, display-oriented summaries for configured LLM profiles."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|apikey|secret|token|password|cookie|authorization)\s*[:=]\s*[^,\s;]{4,}"),
)


def is_model_profile(name: str, cfg: Any) -> bool:
    if not isinstance(cfg, dict):
        return False
    name_l = str(name).lower()
    return bool(
        "model" in cfg
        or "apikey" in cfg
        or "api_key" in cfg
        or "apibase" in cfg
        or "api_base" in cfg
        or any(marker in name_l for marker in ("api", "config", "native_oai", "claude"))
    )


def _safe_text(value: Any, limit: int = 96) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _safe_api_base(value: Any) -> str:
    text = _safe_text(value, limit=180)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text.split("?", 1)[0].split("#", 1)[0]
    if not parsed.scheme or not parsed.netloc:
        return text.split("?", 1)[0].split("#", 1)[0]
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def summarize_model_profile(name: str, cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "profile": _safe_text(name),
        "name": _safe_text(cfg.get("name") or ""),
        "model": _safe_text(cfg.get("model") or ""),
        "api_base": _safe_api_base(cfg.get("apibase") or cfg.get("api_base") or ""),
        "api_mode": _safe_text(cfg.get("api_mode") or ""),
    }


def summarize_model_profiles(mykeys: dict[str, Any]) -> list[dict[str, str]]:
    summaries = []
    for name, cfg in sorted((mykeys or {}).items()):
        if isinstance(cfg, dict) and is_model_profile(name, cfg):
            summaries.append(summarize_model_profile(name, cfg))
    return summaries


def format_model_profile_summary(summary: dict[str, str]) -> str:
    parts = [summary.get("profile", "")]
    if summary.get("model"):
        parts.append(f"model={summary['model']}")
    if summary.get("name") and summary.get("name") != summary.get("model"):
        parts.append(f"name={summary['name']}")
    if summary.get("api_base"):
        parts.append(f"base={summary['api_base']}")
    if summary.get("api_mode"):
        parts.append(f"mode={summary['api_mode']}")
    return " ".join(part for part in parts if part)
