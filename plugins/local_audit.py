"""Local JSONL audit events for the built-in hook system."""

from __future__ import annotations

import time
import uuid

import plugins.hooks as hooks
from safety_policy import write_audit_event


def _handler(ctx):
    return ctx.get("handler") or ctx.get("self")


def _run_id(ctx):
    handler = _handler(ctx)
    if handler is None:
        return "unknown"
    run_id = getattr(handler, "_audit_run_id", None)
    if not run_id:
        run_id = uuid.uuid4().hex[:12]
        setattr(handler, "_audit_run_id", run_id)
    return run_id


def _model_name(client):
    backend = getattr(client, "backend", None)
    if backend is None:
        return ""
    name = getattr(backend, "name", "") or ""
    model = getattr(backend, "model", "") or ""
    return f"{type(backend).__name__}/{model or name}".rstrip("/")


def _tool_result(ret):
    if ret is None:
        return None
    return {
        "data": getattr(ret, "data", None),
        "next_prompt": getattr(ret, "next_prompt", None),
        "should_exit": getattr(ret, "should_exit", None),
    }


def _error_info(ctx):
    error = ctx.get("error")
    if not error:
        return None
    if isinstance(error, dict):
        return error
    return {"type": type(error).__name__, "message": str(error)[:1000]}


@hooks.register("agent_before")
def _agent_before(ctx):
    handler = _handler(ctx)
    if handler is not None:
        setattr(handler, "_audit_started_at", time.monotonic())
    write_audit_event(
        "agent_run_start",
        {
            "run_id": _run_id(ctx),
            "model": _model_name(ctx.get("client")),
            "max_turns": ctx.get("max_turns"),
            "verbose": ctx.get("verbose"),
            "user_input": ctx.get("user_input"),
        },
    )


@hooks.register("agent_after")
def _agent_after(ctx):
    handler = _handler(ctx)
    elapsed_ms = None
    if handler is not None and hasattr(handler, "_audit_started_at"):
        elapsed_ms = int((time.monotonic() - getattr(handler, "_audit_started_at")) * 1000)
    write_audit_event(
        "agent_run_end",
        {
            "run_id": _run_id(ctx),
            "elapsed_ms": elapsed_ms,
            "exit_reason": ctx.get("exit_reason"),
            "error": _error_info(ctx),
        },
    )


@hooks.register("turn_before")
def _turn_before(ctx):
    write_audit_event(
        "turn_start",
        {
            "run_id": _run_id(ctx),
            "turn": ctx.get("turn"),
            "message_count": len(ctx.get("messages") or []),
        },
    )


@hooks.register("turn_after")
def _turn_after(ctx):
    write_audit_event(
        "turn_end",
        {
            "run_id": _run_id(ctx),
            "turn": ctx.get("turn"),
            "tool_count": len(ctx.get("tool_calls") or []),
            "tool_result_count": len(ctx.get("tool_results") or []),
            "next_prompt": ctx.get("next_prompt"),
            "exit_reason": ctx.get("exit_reason"),
        },
    )


@hooks.register("llm_before")
def _llm_before(ctx):
    write_audit_event(
        "llm_start",
        {
            "run_id": _run_id(ctx),
            "turn": ctx.get("turn"),
            "message_count": len(ctx.get("messages") or []),
            "tool_schema_count": len(ctx.get("tools_schema") or []),
        },
    )


@hooks.register("llm_after")
def _llm_after(ctx):
    response = ctx.get("response")
    tool_calls = getattr(response, "tool_calls", None) or []
    write_audit_event(
        "llm_end",
        {
            "run_id": _run_id(ctx),
            "turn": ctx.get("turn"),
            "tool_call_count": len(tool_calls),
            "content": getattr(response, "content", ""),
        },
    )


@hooks.register("tool_before")
def _tool_before(ctx):
    write_audit_event(
        "tool_start",
        {
            "run_id": _run_id(ctx),
            "turn": getattr(_handler(ctx), "current_turn", None),
            "tool_name": ctx.get("tool_name"),
            "index": ctx.get("index"),
            "tool_num": ctx.get("tool_num"),
            "args": ctx.get("args"),
        },
    )


@hooks.register("tool_after")
def _tool_after(ctx):
    write_audit_event(
        "tool_end",
        {
            "run_id": _run_id(ctx),
            "turn": getattr(_handler(ctx), "current_turn", None),
            "tool_name": ctx.get("tool_name"),
            "index": ctx.get("index"),
            "tool_num": ctx.get("tool_num"),
            "result": _tool_result(ctx.get("ret")),
            "error": _error_info(ctx),
        },
    )
