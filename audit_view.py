"""Shared presentation helpers for local audit events."""

from __future__ import annotations

from typing import Any


DETAIL_FIELD_ORDER = (
    "timestamp",
    "event",
    "tool_name",
    "turn",
    "decision",
    "risk",
    "mode",
    "executed",
    "category",
    "reason",
    "error",
    "exit_reason",
    "result",
    "args",
    "extra",
)

HIDDEN_DETAIL_FIELDS = {"_path"}


def _clip(value: Any, limit: int = 120) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def summarize_audit_event(event: dict[str, Any]) -> str:
    name = event.get("event", "")
    if name == "policy_decision":
        parts = [
            event.get("tool_name", "?"),
            event.get("decision", "?"),
            event.get("risk", "?"),
        ]
        if event.get("executed") is not None:
            parts.append(f"executed={event.get('executed')}")
        extra = event.get("extra") if isinstance(event.get("extra"), dict) else {}
        confirmation = extra.get("confirmation") if isinstance(extra.get("confirmation"), dict) else {}
        if confirmation.get("status"):
            parts.append(f"confirmation={confirmation.get('status')}")
        return " ".join(str(part) for part in parts if part != "")
    if name in {"tool_start", "tool_end"}:
        parts = [event.get("tool_name", "?"), f"turn={event.get('turn', '?')}"]
        if event.get("error"):
            error = event.get("error") or {}
            parts.append(f"error={error.get('type', 'Error') if isinstance(error, dict) else 'Error'}")
        result = event.get("result")
        if isinstance(result, dict) and result.get("should_exit") is not None:
            parts.append(f"exit={result.get('should_exit')}")
        return " ".join(str(part) for part in parts)
    if name == "turn_start":
        return f"turn={event.get('turn', '?')} messages={event.get('message_count', '?')}"
    if name == "turn_end":
        parts = [
            f"turn={event.get('turn', '?')}",
            f"tools={event.get('tool_count', '?')}",
        ]
        if event.get("exit_reason"):
            parts.append(f"exit={event.get('exit_reason')}")
        if event.get("error"):
            error = event.get("error") or {}
            parts.append(f"error={error.get('type', 'Error') if isinstance(error, dict) else 'Error'}")
        return " ".join(parts)
    if name == "llm_start":
        return f"turn={event.get('turn', '?')} messages={event.get('message_count', '?')} tools={event.get('tool_schema_count', '?')}"
    if name == "llm_end":
        parts = [
            f"turn={event.get('turn', '?')}",
            f"tool_calls={event.get('tool_call_count', '?')}",
        ]
        if event.get("content"):
            parts.append(_clip(event.get("content"), 70))
        return " ".join(parts)
    if name == "agent_run_start":
        parts = [f"run={event.get('run_id', '?')}"]
        if event.get("model"):
            parts.append(str(event.get("model")))
        return " ".join(parts)
    if name == "agent_run_end":
        parts = [f"run={event.get('run_id', '?')}"]
        if event.get("elapsed_ms") is not None:
            parts.append(f"{event.get('elapsed_ms')}ms")
        if event.get("exit_reason"):
            parts.append(f"exit={event.get('exit_reason')}")
        return " ".join(parts)
    if name in {"snapshot_created", "file_snapshot"}:
        target = event.get("target_rel") or event.get("path") or event.get("target_path") or "?"
        parts = [event.get("tool_name", "?"), target]
        if event.get("existed") is not None:
            parts.append(f"existed={event.get('existed')}")
        return " ".join(str(part) for part in parts)
    if name in {"snapshot_restored", "file_snapshot_restore"}:
        action = event.get("action", "restored")
        return f"{action} {event.get('snapshot_id', '?')} -> {event.get('target_path', '?')}"
    if name == "audit_parse_error":
        return f"{event.get('path', '?')} {_clip(event.get('line'), 60)}"
    return _clip(event.get("message") or event.get("summary") or "")


def audit_event_row(event: dict[str, Any]) -> dict[str, str]:
    timestamp = str(event.get("timestamp", ""))
    return {
        "time": timestamp.replace("T", " ")[:19],
        "event": str(event.get("event", "")),
        "summary": summarize_audit_event(event),
    }


def audit_event_names(events: list[dict[str, Any]]) -> list[str]:
    names = {str(event.get("event", "")).strip() for event in events}
    return sorted(name for name in names if name)


def filter_audit_events(events: list[dict[str, Any]], names: list[str] | tuple[str, ...] | set[str] | None) -> list[dict[str, Any]]:
    selected = {str(name) for name in (names or []) if str(name)}
    if not selected:
        return list(events)
    return [event for event in events if str(event.get("event", "")) in selected]


def audit_event_detail(event: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, display-safe detail payload for UI inspection."""
    from safety_policy import redact_data

    detail: dict[str, Any] = {}
    for key in DETAIL_FIELD_ORDER:
        if key in event and key not in HIDDEN_DETAIL_FIELDS:
            detail[key] = redact_data(event[key])
    for key in sorted(event):
        if key in detail or key in HIDDEN_DETAIL_FIELDS:
            continue
        detail[str(key)] = redact_data(event[key])
    return detail
