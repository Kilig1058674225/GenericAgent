import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ga_cli.cli import cmd_audit, cmd_skills, cmd_snapshots
from audit_view import audit_event_row, summarize_audit_event
from safety_policy import write_audit_event
from workspace_guard import create_file_snapshot


class CliAuditTests(unittest.TestCase):
    def test_audit_view_summarizes_events_for_cli_and_ui(self):
        event = {
            "timestamp": "2026-05-28T12:34:56+00:00",
            "event": "policy_decision",
            "tool_name": "code_run",
            "decision": "block",
            "risk": "critical",
            "executed": False,
        }

        self.assertEqual(summarize_audit_event(event), "code_run block critical executed=False")
        self.assertEqual(
            audit_event_row(event),
            {
                "time": "2026-05-28 12:34:56",
                "event": "policy_decision",
                "summary": "code_run block critical executed=False",
            },
        )

    def test_cmd_audit_outputs_text_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"GA_AUDIT_DIR": tmpdir}, clear=False):
                write_audit_event("tool_start", {"tool_name": "file_read", "turn": 2})
                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_audit(["--event", "tool_start", "-n", "1"])

        rendered = out.getvalue()
        self.assertIn("tool_start", rendered)
        self.assertIn("file_read", rendered)
        self.assertIn("turn=2", rendered)

    def test_cmd_audit_json_is_redacted(self):
        raw_secret = "sk-clisecret1234567890"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"GA_AUDIT_DIR": tmpdir}, clear=False):
                write_audit_event("agent_run_start", {"apikey": raw_secret, "user_input": "hello"})
                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_audit(["--json", "-n", "1"])

        rendered = out.getvalue()
        data = json.loads(rendered)
        self.assertEqual(data[0]["apikey"], "[REDACTED]")
        self.assertNotIn(raw_secret, rendered)

    def test_cmd_skills_sync_list_and_toggle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "memory")
            os.makedirs(root)
            with open(os.path.join(root, "demo_sop.md"), "w", encoding="utf-8") as f:
                f.write("# Demo SOP\n\nUse web_scan safely.\n")
            registry = os.path.join(tmpdir, "skill_registry.json")
            env = {"GA_SKILL_ROOT": root, "GA_SKILL_REGISTRY": registry}
            with patch.dict(os.environ, env, clear=False):
                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_skills(["sync"])
                self.assertIn("Synced 1 skill", out.getvalue())

                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_skills(["list", "--json"])
                skills = json.loads(out.getvalue())
                skill_id = skills[0]["id"]

                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_skills(["disable", skill_id])
                self.assertIn("disabled", out.getvalue())

                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_skills(["list", "--json"])
                self.assertEqual(json.loads(out.getvalue()), [])

                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_skills(["list", "--all", "--json"])
                self.assertFalse(json.loads(out.getvalue())[0]["enabled"])

    def test_cmd_snapshots_list_and_restore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "notes.txt")
            with open(target, "w", encoding="utf-8") as f:
                f.write("before")
            env = {"GA_SNAPSHOT_DIR": os.path.join(tmpdir, "snapshots"), "GA_AUDIT_DIR": os.path.join(tmpdir, "audit")}
            with patch.dict(os.environ, env, clear=False):
                snap = create_file_snapshot(target, reason="cli", tool_name="unit")
                with open(target, "w", encoding="utf-8") as f:
                    f.write("after")

                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_snapshots(["list", "-n", "1", "--json"])
                listed = json.loads(out.getvalue())

                out = io.StringIO()
                with redirect_stdout(out):
                    cmd_snapshots(["restore", snap["snapshot_id"], "--no-pre-snapshot", "--json"])
                restored = json.loads(out.getvalue())
                with open(target, encoding="utf-8") as f:
                    restored_text = f.read()

        self.assertEqual(listed[0]["id"], snap["snapshot_id"])
        self.assertEqual(restored["status"], "success")
        self.assertEqual(restored_text, "before")


if __name__ == "__main__":
    unittest.main()
