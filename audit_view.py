"""Shared presentation helpers for local audit events."""

from __future__ import annotations

from typing import Any


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
        return " ".join(str(part) for part in parts if part != "")
    if name in {"tool_start", "tool_end"}:
        parts = [event.get("tool_name", "?"), f"turn={event.get('turn', '?')}"]
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
    if name == "snapshot_created":
        return f"{event.get('tool_name', '?')} {event.get('path', '?')}"
    if name == "snapshot_restored":
        return f"{event.get('snapshot_id', '?')} -> {event.get('target_path', '?')}"
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
