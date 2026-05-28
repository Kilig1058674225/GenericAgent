"""Local safety policy and audit helpers for GenericAgent tool dispatch."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
AUDIT_DIR = PROJECT_ROOT / "temp" / "runs"
AUDIT_EVENT_LIMIT = 1000
PROTECTED_INTERNAL_ROOTS = (
    PROJECT_ROOT / ".git",
    PROJECT_ROOT / ".venv",
    PROJECT_ROOT / ".pytest_cache",
    PROJECT_ROOT / "__pycache__",
    PROJECT_ROOT / "genericagent.egg-info",
    PROJECT_ROOT / "temp" / "runs",
    PROJECT_ROOT / "temp" / "snapshots",
    PROJECT_ROOT / "temp" / "model_responses",
)

DECISION_ALLOW = "allow"
DECISION_CONFIRM = "require_confirmation"
DECISION_BLOCK = "block"

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"

MODE_OFF = "off"
MODE_OBSERVE = "observe"
MODE_ENFORCE = "enforce"

PAYMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_])("
    r"buy|purchase|checkout|pay|payment|stripe|paypal|alipay|wechatpay|"
    r"order\s+now|place\s+order|subscribe|subscription|invoice|billing"
    r")(?![A-Za-z0-9_])|"
    r"(付款|支付|购买|下单|结账|订阅|账单)",
    re.IGNORECASE,
)
MESSAGING_RE = re.compile(
    r"(?<![A-Za-z0-9_])("
    r"send\s+(email|mail|message|sms|dm)|post\s+to|tweet|publish|"
    r"telegram|discord|wechat|wecom|dingtalk|slack|lark|feishu"
    r")(?![A-Za-z0-9_])|"
    r"(发送|发信|发邮件|群发|发布|推送)",
    re.IGNORECASE,
)
DESTRUCTIVE_RE = re.compile(
    r"("
    r"rm\s+-rf|remove-item\b.*\b-recurse\b|rmdir\s+/s|del\s+/[sq]|"
    r"format\s+[a-z]:|shutdown\b|reboot\b|"
    r"git\s+reset\s+--hard|git\s+checkout\s+--|"
    r"drop\s+database|truncate\s+table"
    r")",
    re.IGNORECASE | re.DOTALL,
)
SECRET_PATH_RE = re.compile(
    r"("
    r"(^|[\\/])\.env($|[\\/])|(^|[\\/])\.ssh($|[\\/])|"
    r"mykey\.py|auth\.json|credentials?\.json|keychain|cookie|token|"
    r"id_rsa|id_ed25519|\.pem$|\.p12$|\.pfx$"
    r")",
    re.IGNORECASE,
)

SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|password|cookie|authorization)\b\s*[:=]\s*['\"]?[^'\"\s,;]{8,}"),
]


@dataclass(frozen=True)
class PolicyDecision:
    tool_name: str
    category: str
    risk: str
    decision: str
    mode: str
    reason: str

    @property
    def blocks_execution(self) -> bool:
        if self.mode == MODE_OFF:
            return False
        if self.decision == DECISION_BLOCK and self.risk == RISK_CRITICAL:
            return True
        return self.mode == MODE_ENFORCE and self.decision in {DECISION_BLOCK, DECISION_CONFIRM}

    @property
    def needs_confirmation(self) -> bool:
        return self.mode == MODE_ENFORCE and self.decision == DECISION_CONFIRM

    def public_dict(self) -> dict[str, str]:
        return asdict(self)


def get_policy_mode() -> str:
    mode = os.environ.get("GA_POLICY_MODE", MODE_OBSERVE).strip().lower()
    if mode not in {MODE_OFF, MODE_OBSERVE, MODE_ENFORCE}:
        return MODE_OBSERVE
    return mode


def _stringify_args(args: Any) -> str:
    try:
        return json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(args)


def _contains_payment(text: str) -> bool:
    return bool(PAYMENT_RE.search(text))


def _contains_messaging(text: str) -> bool:
    return bool(MESSAGING_RE.search(text))


def _contains_destructive_command(text: str) -> bool:
    return bool(DESTRUCTIVE_RE.search(text))


def _path_from_args(tool_name: str, args: dict[str, Any], base_dir: str | os.PathLike[str] | None = None) -> Path | None:
    if tool_name not in {"file_read", "file_write", "file_patch"}:
        return None
    path = args.get("path")
    if not path:
        return None
    raw = Path(str(path))
    if not raw.is_absolute():
        raw = Path(base_dir or PROJECT_ROOT / "temp") / raw
    try:
        return raw.resolve()
    except Exception:
        return raw.absolute()


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_sensitive_path(path: Path | None) -> bool:
    return bool(path and SECRET_PATH_RE.search(str(path)))


def _protected_internal_path(path: Path | None) -> str | None:
    if path is None:
        return None
    for root in PROTECTED_INTERNAL_ROOTS:
        try:
            resolved_root = root.resolve()
        except Exception:
            resolved_root = root.absolute()
        if path == resolved_root or _is_inside(path, resolved_root):
            try:
                return resolved_root.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                return str(resolved_root)
    return None


def _tool_base_dir(handler: Any | None) -> Path:
    cwd = getattr(handler, "cwd", None) if handler is not None else None
    if cwd:
        try:
            return Path(cwd).resolve()
        except Exception:
            return Path(cwd).absolute()
    return PROJECT_ROOT / "temp"


def _is_allowed_workspace_path(path: Path | None) -> bool:
    if path is None:
        return False
    allowed_roots = [PROJECT_ROOT, PROJECT_ROOT / "temp", PROJECT_ROOT / "memory"]
    return any(_is_inside(path, root.resolve()) for root in allowed_roots)


def classify_tool_call(tool_name: str, args: dict[str, Any] | None, handler: Any | None = None) -> PolicyDecision:
    """Classify a tool call before execution.

    The default mode is observe: risky calls execute, but every decision is auditable.
    Set GA_POLICY_MODE=enforce to deny blocks and pause confirmation-grade calls.
    """
    mode = get_policy_mode()
    args = dict(args or {})
    text = _stringify_args(args)

    if mode == MODE_OFF:
        return PolicyDecision(tool_name, "disabled", RISK_LOW, DECISION_ALLOW, mode, "policy disabled")

    if _contains_payment(text):
        if os.environ.get("GA_ALLOW_PAYMENT_ACTIONS") == "1":
            return PolicyDecision(tool_name, "payment_or_purchase", RISK_HIGH, DECISION_CONFIRM, mode, "payment-like action needs explicit confirmation")
        return PolicyDecision(tool_name, "payment_or_purchase", RISK_CRITICAL, DECISION_BLOCK, mode, "payment or purchase action is disabled by default")

    if _contains_messaging(text):
        return PolicyDecision(tool_name, "messaging", RISK_HIGH, DECISION_CONFIRM, mode, "external messaging or publishing needs confirmation")

    path = _path_from_args(tool_name, args, _tool_base_dir(handler))
    if _is_sensitive_path(path):
        return PolicyDecision(tool_name, "credential_access", RISK_HIGH, DECISION_CONFIRM, mode, "credential-like path needs confirmation")
    protected_internal = _protected_internal_path(path)

    if tool_name == "file_read":
        if protected_internal:
            return PolicyDecision(tool_name, "internal_state", RISK_HIGH, DECISION_CONFIRM, mode, f"read of protected internal path: {protected_internal}")
        if path and _is_allowed_workspace_path(path):
            return PolicyDecision(tool_name, "file_read", RISK_LOW, DECISION_ALLOW, mode, "read inside local workspace")
        return PolicyDecision(tool_name, "file_read", RISK_MEDIUM, DECISION_CONFIRM, mode, "read outside local workspace")

    if tool_name in {"file_write", "file_patch"}:
        if protected_internal:
            return PolicyDecision(tool_name, "internal_state", RISK_CRITICAL, DECISION_BLOCK, mode, f"write to protected internal path: {protected_internal}")
        if path and _is_allowed_workspace_path(path):
            return PolicyDecision(tool_name, "file_write", RISK_MEDIUM, DECISION_ALLOW, mode, "write inside local workspace")
        return PolicyDecision(tool_name, "file_write", RISK_HIGH, DECISION_CONFIRM, mode, "write outside local workspace")

    if tool_name == "code_run":
        code_type = str(args.get("type", "python")).lower()
        if _contains_destructive_command(text):
            return PolicyDecision(tool_name, "command_execution", RISK_CRITICAL, DECISION_BLOCK, mode, "destructive command pattern")
        if code_type in {"powershell", "ps1", "pwsh", "bash", "sh", "shell"}:
            return PolicyDecision(tool_name, "command_execution", RISK_HIGH, DECISION_CONFIRM, mode, "shell execution needs confirmation")
        return PolicyDecision(tool_name, "command_execution", RISK_HIGH, DECISION_CONFIRM, mode, "code execution needs confirmation")

    if tool_name == "web_execute_js":
        return PolicyDecision(tool_name, "browser_control", RISK_HIGH, DECISION_CONFIRM, mode, "browser JavaScript control needs confirmation")

    if tool_name == "web_scan":
        return PolicyDecision(tool_name, "network_access", RISK_LOW, DECISION_ALLOW, mode, "read-only browser scan")

    if tool_name in {"ask_user", "update_working_checkpoint", "start_long_term_update", "no_tool"}:
        return PolicyDecision(tool_name, "local_state", RISK_LOW, DECISION_ALLOW, mode, "low-risk local tool")

    if tool_name == "bad_json":
        return PolicyDecision(tool_name, "model_repair", RISK_LOW, DECISION_ALLOW, mode, "model JSON repair flow")

    return PolicyDecision(tool_name, "unknown_tool", RISK_MEDIUM, DECISION_CONFIRM, mode, "unknown tool requires confirmation")


def _env_secret_values() -> list[str]:
    values = []
    for key, value in os.environ.items():
        key_l = key.lower()
        if any(marker in key_l for marker in ("key", "token", "secret", "password", "cookie", "auth")) and value and len(value) >= 8:
            values.append(value)
    return values


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    for secret in _env_secret_values():
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def redact_data(data: Any) -> Any:
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if re.search(r"(?i)(api[_-]?key|apikey|secret|token|password|cookie|authorization)", str(key)):
                result[key] = "[REDACTED]" if value else value
            else:
                result[key] = redact_data(value)
        return result
    if isinstance(data, list):
        return [redact_data(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_data(item) for item in data)
    return data


def get_audit_dir() -> Path:
    override = os.environ.get("GA_AUDIT_DIR")
    return Path(override).expanduser() if override else AUDIT_DIR


def audit_log_path(now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    return get_audit_dir() / f"audit-{now.strftime('%Y%m%d')}.jsonl"


def _clip_data(data: Any, max_string: int = AUDIT_EVENT_LIMIT) -> Any:
    if isinstance(data, str):
        if len(data) <= max_string:
            return data
        head = max_string // 2
        tail = max_string - head
        return f"{data[:head]}\n...[truncated {len(data) - max_string} chars]...\n{data[-tail:]}"
    if isinstance(data, dict):
        return {str(key): _clip_data(value, max_string=max_string) for key, value in data.items()}
    if isinstance(data, list):
        return [_clip_data(item, max_string=max_string) for item in data]
    if isinstance(data, tuple):
        return tuple(_clip_data(item, max_string=max_string) for item in data)
    return data


def write_audit_event(event: str, payload: dict[str, Any] | None = None, *, now: datetime | None = None) -> Path | None:
    """Append a sanitized generic audit event to temp/runs/*.jsonl."""
    try:
        event_time = now or datetime.now(timezone.utc)
        audit_dir = get_audit_dir()
        audit_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": event_time.isoformat(),
            "event": event,
        }
        if payload:
            record.update(redact_data(_clip_data(payload)))
        path = audit_log_path(event_time)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"timestamp": "", "event": "audit_parse_error", "path": str(path), "line": redact_text(line[:500])})
    except OSError:
        return []
    return events


def iter_audit_events(limit: int = 20, event: str | None = None) -> list[dict[str, Any]]:
    """Return newest audit events first."""
    limit = max(1, int(limit or 20))
    events: list[dict[str, Any]] = []
    for path in sorted(get_audit_dir().glob("audit-*.jsonl"), reverse=True):
        for item in reversed(_read_jsonl(path)):
            if event and item.get("event") != event:
                continue
            item = dict(item)
            item.setdefault("_path", str(path))
            events.append(item)
            if len(events) >= limit:
                return events
    return events


def write_policy_audit(
    decision: PolicyDecision,
    args: dict[str, Any] | None,
    *,
    index: int = 0,
    tool_num: int = 1,
    executed: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Append a sanitized policy event to temp/runs/*.jsonl.

    Audit failures should never break agent execution.
    """
    payload = {
        "tool_name": decision.tool_name,
        "category": decision.category,
        "risk": decision.risk,
        "decision": decision.decision,
        "mode": decision.mode,
        "reason": decision.reason,
        "index": index,
        "tool_num": tool_num,
        "executed": executed,
        "args": redact_data(args or {}),
    }
    if extra:
        payload["extra"] = redact_data(extra)
    return write_audit_event("policy_decision", payload)
