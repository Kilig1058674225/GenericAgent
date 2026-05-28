import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agentmain import GenericAgent
from safety_policy import CONFIRMATION_TOKEN_ENV


def _sample_token():
    return "ga-confirm-v1-" + "agentmain" + "123456"


def _confirmation_exit_reason():
    return {
        "result": "EXITED",
        "data": {
            "status": "INTERRUPT",
            "intent": "HUMAN_CONFIRMATION_REQUIRED",
            "data": {
                "question": "confirm code_run",
                "confirmation_token": _sample_token(),
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


class DummyHandler:
    def __init__(self, parent, history, cwd):
        self.parent = parent
        self.history_info = list(history)
        self.working = {}
        self.code_stop_signal = []


def fake_agent_runner_loop(*args, **kwargs):
    yield {"turn": 1}
    yield "paused"
    return _confirmation_exit_reason()


class AgentMainConfirmationTests(unittest.TestCase):
    def test_run_adds_pending_confirmation_to_done_item(self):
        agent = object.__new__(GenericAgent)
        agent.task_queue = queue.Queue()
        agent.history = []
        agent.handler = None
        agent.task_dir = None
        agent.is_running = False
        agent.stop_sig = False
        agent.inc_out = False
        agent.verbose = False
        agent.peer_hint = False
        agent.log_path = "test.log"
        agent.llmclient = SimpleNamespace(backend=SimpleNamespace(extra_sys_prompt=""), log_path=None)
        display_queue = queue.Queue()
        agent.task_queue.put({"query": "please run code", "source": "test", "images": [], "output": display_queue})

        with (
            patch("agentmain.GenericAgentHandler", DummyHandler),
            patch("agentmain.agent_runner_loop", fake_agent_runner_loop),
            patch("agentmain.get_system_prompt", return_value="system"),
            patch("agentmain.consume_file", return_value=None),
        ):
            thread = threading.Thread(target=agent.run, daemon=True)
            thread.start()
            done_item = None
            for _ in range(3):
                item = display_queue.get(timeout=2)
                if "done" in item:
                    done_item = item
                    break

        self.assertIsNotNone(done_item)
        self.assertEqual(done_item["exit_reason"]["result"], "EXITED")
        pending = done_item["pending_confirmation"]
        self.assertEqual(pending["tool_name"], "code_run")
        self.assertEqual(pending["token"], _sample_token())
        self.assertEqual(pending["prompt"], "please run code")


if __name__ == "__main__":
    unittest.main()
