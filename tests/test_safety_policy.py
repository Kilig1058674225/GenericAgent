import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import safety_policy
from agent_loop import BaseHandler, StepOutcome, exhaust
from safety_policy import (
    DECISION_ALLOW,
    DECISION_BLOCK,
    DECISION_CONFIRM,
    MODE_ENFORCE,
    MODE_OBSERVE,
    classify_tool_call,
    iter_audit_events,
    redact_data,
    write_audit_event,
    write_policy_audit,
)


class DummyHandler(BaseHandler):
    def __init__(self, cwd):
        self.cwd = str(cwd)
        self.executed = False

    def do_code_run(self, args, response):
        self.executed = True
        yield "ran\n"
        return StepOutcome({"ok": True}, next_prompt="\n")


class SafetyPolicyTests(unittest.TestCase):
    def test_safe_workspace_read_is_allowed(self):
        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_OBSERVE}, clear=False):
            decision = classify_tool_call("file_read", {"path": "notes.txt"}, handler=DummyHandler(safety_policy.PROJECT_ROOT / "temp"))

        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertEqual(decision.risk, "low")
        self.assertFalse(decision.blocks_execution)

    def test_sensitive_path_requires_confirmation(self):
        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_ENFORCE}, clear=False):
            decision = classify_tool_call("file_read", {"path": "mykey.py"}, handler=DummyHandler(safety_policy.PROJECT_ROOT))

        self.assertEqual(decision.decision, DECISION_CONFIRM)
        self.assertTrue(decision.blocks_execution)
        self.assertTrue(decision.needs_confirmation)

    def test_payment_like_action_is_blocked_by_default(self):
        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_ENFORCE}, clear=False):
            decision = classify_tool_call("web_execute_js", {"script": "click checkout and pay"}, handler=None)

        self.assertEqual(decision.decision, DECISION_BLOCK)
        self.assertEqual(decision.category, "payment_or_purchase")
        self.assertTrue(decision.blocks_execution)

    def test_chinese_payment_terms_are_detected(self):
        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_ENFORCE}, clear=False):
            decision = classify_tool_call("web_execute_js", {"script": "点击支付按钮并下单"}, handler=None)

        self.assertEqual(decision.decision, DECISION_BLOCK)
        self.assertEqual(decision.category, "payment_or_purchase")

    def test_destructive_command_is_block_in_enforce_but_observed_only_in_observe(self):
        args = {"type": "powershell", "code": "git reset --hard"}

        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_OBSERVE}, clear=False):
            observed = classify_tool_call("code_run", args, handler=None)
        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_ENFORCE}, clear=False):
            enforced = classify_tool_call("code_run", args, handler=None)

        self.assertEqual(observed.decision, DECISION_BLOCK)
        self.assertFalse(observed.blocks_execution)
        self.assertEqual(enforced.decision, DECISION_BLOCK)
        self.assertTrue(enforced.blocks_execution)

    def test_redaction_handles_secret_keys_and_values(self):
        raw_secret = "sk-testsecret1234567890"
        data = {
            "apikey": raw_secret,
            "nested": {"header": "Authorization: Bearer abcdefghijklmnop"},
            "text": f"token={raw_secret}",
        }

        redacted = redact_data(data)
        rendered = json.dumps(redacted, ensure_ascii=False)

        self.assertNotIn(raw_secret, rendered)
        self.assertNotIn("abcdefghijklmnop", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_audit_log_is_jsonl_and_redacted(self):
        raw_secret = "sk-auditsecret1234567890"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"GA_AUDIT_DIR": tmpdir}, clear=False):
                decision = classify_tool_call("web_scan", {"apikey": raw_secret}, handler=None)
                path = write_policy_audit(decision, {"apikey": raw_secret, "query": "hello"}, executed=True)
                self.assertIsNotNone(path)
                content = Path(path).read_text(encoding="utf-8")

        self.assertNotIn(raw_secret, content)
        event = json.loads(content.strip())
        self.assertEqual(event["event"], "policy_decision")
        self.assertEqual(event["args"]["apikey"], "[REDACTED]")

    def test_generic_audit_events_are_filtered_newest_first_and_clipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"GA_AUDIT_DIR": tmpdir}, clear=False):
                write_audit_event("first", {"message": "old"})
                write_audit_event("second", {"message": "x" * 1500})
                write_audit_event("second", {"message": "new"})
                newest = iter_audit_events(limit=2)
                filtered = iter_audit_events(limit=5, event="second")

        self.assertEqual([item["event"] for item in newest], ["second", "second"])
        self.assertEqual([item["message"] for item in filtered][:1], ["new"])
        self.assertIn("[truncated", filtered[1]["message"])

    def test_dispatch_executes_in_observe_mode(self):
        handler = DummyHandler(safety_policy.PROJECT_ROOT / "temp")
        response = SimpleNamespace(content="")

        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_OBSERVE}, clear=False):
            outcome = exhaust(handler.dispatch("code_run", {"type": "python", "code": "print(1)"}, response))

        self.assertTrue(handler.executed)
        self.assertEqual(outcome.data, {"ok": True})

    def test_dispatch_pauses_confirmation_in_enforce_mode(self):
        handler = DummyHandler(safety_policy.PROJECT_ROOT / "temp")
        response = SimpleNamespace(content="")

        with patch.dict(os.environ, {"GA_POLICY_MODE": MODE_ENFORCE}, clear=False):
            outcome = exhaust(handler.dispatch("code_run", {"type": "python", "code": "print(1)"}, response))

        self.assertFalse(handler.executed)
        self.assertTrue(outcome.should_exit)
        self.assertEqual(outcome.data["status"], "INTERRUPT")
        self.assertEqual(outcome.data["intent"], "HUMAN_CONFIRMATION_REQUIRED")

    def test_local_audit_plugin_writes_hook_events(self):
        from plugins import local_audit

        handler = DummyHandler(safety_policy.PROJECT_ROOT / "temp")
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"GA_AUDIT_DIR": tmpdir}, clear=False):
                local_audit._agent_before({"handler": handler, "user_input": "hello", "max_turns": 1})
                local_audit._tool_before({"handler": handler, "tool_name": "file_read", "args": {"path": "notes.txt"}})
                events = iter_audit_events(limit=5)

        names = [event["event"] for event in events]
        self.assertIn("agent_run_start", names)
        self.assertIn("tool_start", names)


if __name__ == "__main__":
    unittest.main()
