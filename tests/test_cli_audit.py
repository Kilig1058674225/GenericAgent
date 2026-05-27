import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ga_cli.cli import cmd_audit
from safety_policy import write_audit_event


class CliAuditTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
