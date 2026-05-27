import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import plugins.hooks as hooks
from agent_loop import BaseHandler, StepOutcome, agent_runner_loop, exhaust


def _tool_call(name, args=None, call_id="tool-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args or {})),
    )


class DummyResponse:
    def __init__(self, tool_calls):
        self.content = "ok"
        self.tool_calls = tool_calls


class DummyClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.last_tools = ""

    def chat(self, messages, tools):
        response = self.responses.pop(0)
        yield response.content
        return response


class AuditHandler(BaseHandler):
    def __init__(self):
        self.parent = SimpleNamespace(task_dir=None)
        self._done_hooks = []
        self.turn_callbacks = []

    def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason):
        self.turn_callbacks.append((turn, next_prompt, exit_reason))
        return next_prompt

    def do_finish_task(self, args, response):
        return StepOutcome({"ok": True}, next_prompt="")

    def do_continue_task(self, args, response):
        return StepOutcome({"ok": True}, next_prompt="continue")


class AgentLoopAuditTests(unittest.TestCase):
    def setUp(self):
        self._registry = {name: list(callbacks) for name, callbacks in hooks._registry.items()}
        hooks.clear()

    def tearDown(self):
        hooks.clear()
        hooks._registry.update(self._registry)

    def _record_hooks(self):
        events = []

        def recorder(name):
            def _callback(ctx):
                events.append((name, dict(ctx)))

            return _callback

        for name in ("turn_after", "agent_after"):
            hooks.register(name)(recorder(name))
        return events

    def test_final_task_done_emits_turn_after_before_agent_after(self):
        events = self._record_hooks()
        handler = AuditHandler()
        client = DummyClient([DummyResponse([_tool_call("finish_task")])])

        with patch("agent_loop.classify_tool_call", None), patch("agent_loop.write_policy_audit", None):
            result = exhaust(agent_runner_loop(client, "system", "do it", handler, [], max_turns=3, verbose=False))

        self.assertEqual(result["result"], "CURRENT_TASK_DONE")
        names = [name for name, _ctx in events]
        self.assertEqual(names, ["turn_after", "agent_after"])
        self.assertEqual(events[0][1]["exit_reason"]["result"], "CURRENT_TASK_DONE")
        self.assertEqual(events[0][1]["next_prompt"], "")
        self.assertEqual(events[1][1]["exit_reason"]["result"], "CURRENT_TASK_DONE")
        self.assertEqual(handler.turn_callbacks[-1][2]["result"], "CURRENT_TASK_DONE")

    def test_agent_after_reports_max_turns_exceeded(self):
        events = self._record_hooks()
        handler = AuditHandler()
        client = DummyClient([DummyResponse([_tool_call("continue_task")])])

        with patch("agent_loop.classify_tool_call", None), patch("agent_loop.write_policy_audit", None):
            result = exhaust(agent_runner_loop(client, "system", "do it", handler, [], max_turns=1, verbose=False))

        self.assertEqual(result["result"], "MAX_TURNS_EXCEEDED")
        self.assertEqual([name for name, _ctx in events], ["turn_after", "agent_after"])
        self.assertEqual(events[0][1]["exit_reason"]["result"], "MAX_TURNS_EXCEEDED")
        self.assertEqual(events[-1][1]["exit_reason"]["result"], "MAX_TURNS_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
