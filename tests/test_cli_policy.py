import io
import json
import os
import unittest
from contextlib import redirect_stdout

from ga_cli.cli import cmd_policy


class CliPolicyTests(unittest.TestCase):
    def test_policy_check_json_is_redacted_and_does_not_execute(self):
        raw_secret = "sk-policysecret1234567890"
        out = io.StringIO()

        with redirect_stdout(out):
            cmd_policy(
                [
                    "check",
                    "web_scan",
                    json.dumps({"apikey": raw_secret, "query": "hello"}),
                    "--mode",
                    "observe",
                    "--json",
                ]
            )

        rendered = out.getvalue()
        data = json.loads(rendered)
        self.assertEqual(data["policy"]["decision"], "allow")
        self.assertFalse(data["blocks_execution"])
        self.assertEqual(data["args"]["apikey"], "[REDACTED]")
        self.assertNotIn(raw_secret, rendered)

    def test_policy_check_mode_override_is_restored(self):
        old_mode = os.environ.get("GA_POLICY_MODE")
        os.environ["GA_POLICY_MODE"] = "observe"
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_policy(
                    [
                        "check",
                        "code_run",
                        json.dumps({"type": "python", "code": "print(1)"}),
                        "--mode",
                        "enforce",
                        "--json",
                    ]
                )

            data = json.loads(out.getvalue())
            self.assertEqual(data["policy"]["decision"], "require_confirmation")
            self.assertTrue(data["blocks_execution"])
            self.assertEqual(os.environ.get("GA_POLICY_MODE"), "observe")
        finally:
            if old_mode is None:
                os.environ.pop("GA_POLICY_MODE", None)
            else:
                os.environ["GA_POLICY_MODE"] = old_mode

    def test_policy_check_blocks_destructive_shell(self):
        out = io.StringIO()

        with redirect_stdout(out):
            cmd_policy(
                [
                    "check",
                    "code_run",
                    json.dumps({"type": "powershell", "code": "git reset --hard"}),
                    "--mode",
                    "observe",
                    "--json",
                ]
            )

        data = json.loads(out.getvalue())
        self.assertEqual(data["policy"]["decision"], "block")
        self.assertEqual(data["policy"]["risk"], "critical")
        self.assertTrue(data["blocks_execution"])


if __name__ == "__main__":
    unittest.main()
