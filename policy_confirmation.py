"""Helpers for one-time policy confirmations in frontends."""

from __future__ import annotations

import os
from typing import Any

try:
    from safety_policy import CONFIRMATION_TOKEN_ENV
except ImportError:
    CONFIRMATION_TOKEN_ENV = "GA_POLICY_CONFIRM_TOKEN"


def extract_pending_confirmation(exit_reason: dict[str, Any] | None, *, prompt: str | None = None) -> dict[str, Any] | None:
    """Extract a frontend-safe pending confirmation from an agent exit reason."""
    if not isinstance(exit_reason, dict):
        return None
    payload = exit_reason.get("data")
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "INTERRUPT" or payload.get("intent") != "HUMAN_CONFIRMATION_REQUIRED":
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = str(data.get("confirmation_token") or "").strip()
    if not token:
        return None
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    return {
        "intent": payload.get("intent"),
        "question": str(data.get("question") or "A tool call needs confirmation."),
        "token": token,
        "token_id": token[-12:],
        "env_var": str(data.get("confirmation_env_var") or CONFIRMATION_TOKEN_ENV),
        "tool_name": str(policy.get("tool_name") or ""),
        "risk": str(policy.get("risk") or ""),
        "category": str(policy.get("category") or ""),
        "reason": str(policy.get("reason") or ""),
        "prompt": prompt or "",
    }


def apply_confirmation_token(pending: dict[str, Any], environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Add a pending confirmation token to the process environment once."""
    env = environ if environ is not None else os.environ
    token = str((pending or {}).get("token") or "").strip()
    env_var = str((pending or {}).get("env_var") or CONFIRMATION_TOKEN_ENV).strip() or CONFIRMATION_TOKEN_ENV
    if not token:
        return {"status": "error", "msg": "missing confirmation token"}
    existing = [item for item in env.get(env_var, "").split() if item]
    if token not in existing:
        existing.append(token)
    env[env_var] = " ".join(existing)
    return {"status": "success", "env_var": env_var, "token_id": token[-12:]}
