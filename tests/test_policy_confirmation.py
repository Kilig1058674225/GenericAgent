import unittest

from policy_confirmation import apply_confirmation_token, extract_pending_confirmation
from safety_policy import CONFIRMATION_TOKEN_ENV


def _sample_token():
    return "ga-confirm-v1-" + "abcdef" + "1234567890"


def _exit_reason(token=None):
    token = token or _sample_token()
    return {
        "result": "EXITED",
        "data": {
            "status": "INTERRUPT",
            "intent": "HUMAN_CONFIRMATION_REQUIRED",
            "data": {
                "question": "confirm this exact call",
                "confirmation_token": token,
                "confirmation_env_var": CONFIRMATION_TOKEN_ENV,
                "policy": {
                    "tool_name": "code_run",
                    "risk": "high",
                    "category": "command_execution",
                    "reason": "code execution needs confirmation",
                },
            },
        },
    }


class PolicyConfirmationTests(unittest.TestCase):
    def test_extract_pending_confirmation_from_exit_reason(self):
        pending = extract_pending_confirmation(_exit_reason(), prompt="run code")

        self.assertIsNotNone(pending)
        self.assertEqual(pending["tool_name"], "code_run")
        self.assertEqual(pending["risk"], "high")
        self.assertEqual(pending["token_id"], "ef1234567890")
        self.assertEqual(pending["prompt"], "run code")

    def test_extract_ignores_non_confirmation_interrupts(self):
        exit_reason = {"result": "CURRENT_TASK_DONE", "data": {"ok": True}}

        self.assertIsNone(extract_pending_confirmation(exit_reason, prompt="hello"))
        self.assertIsNone(extract_pending_confirmation(None, prompt="hello"))

    def test_apply_confirmation_token_adds_and_deduplicates_env_value(self):
        env = {CONFIRMATION_TOKEN_ENV: "existing-token"}
        pending = {"token": _sample_token(), "env_var": CONFIRMATION_TOKEN_ENV}

        first = apply_confirmation_token(pending, environ=env)
        second = apply_confirmation_token(pending, environ=env)

        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "success")
        self.assertEqual(env[CONFIRMATION_TOKEN_ENV], "existing-token " + _sample_token())

    def test_apply_confirmation_token_rejects_missing_token(self):
        env = {}

        result = apply_confirmation_token({}, environ=env)

        self.assertEqual(result["status"], "error")
        self.assertEqual(env, {})


if __name__ == "__main__":
    unittest.main()
