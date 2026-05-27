import builtins
import os
import unittest
from unittest.mock import patch

import llmcore


class LlmcoreEnvConfigTests(unittest.TestCase):
    def setUp(self):
        self._old_path = llmcore._mykey_path
        self._old_mtime = llmcore._mykey_mtime
        self._old_mykeys = llmcore.__dict__.get("mykeys", None)
        self._had_mykeys = "mykeys" in llmcore.__dict__

    def tearDown(self):
        llmcore._mykey_path = self._old_path
        llmcore._mykey_mtime = self._old_mtime
        if self._had_mykeys:
            llmcore.__dict__["mykeys"] = self._old_mykeys
        else:
            llmcore.__dict__.pop("mykeys", None)

    def test_env_config_requires_key_and_model(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(llmcore._load_env_mykeys())

        with patch.dict(os.environ, {"GENERICAGENT_API_KEY": "sk-test"}, clear=True):
            self.assertIsNone(llmcore._load_env_mykeys())

    def test_env_config_builds_native_oai_profile(self):
        env = {
            "GENERICAGENT_API_KEY": "sk-test",
            "GENERICAGENT_API_BASE": "https://example.invalid/v1",
            "GENERICAGENT_MODEL": "qwen-thinking",
            "GENERICAGENT_NAME": "qwen-env",
            "GENERICAGENT_API_MODE": "responses",
            "GENERICAGENT_REASONING_EFFORT": "high",
            "GENERICAGENT_SERVICE_TIER": "priority",
            "GENERICAGENT_MAX_TOKENS": "8192",
            "GENERICAGENT_TEMPERATURE": "0.7",
            "GENERICAGENT_CONTEXT_WIN": "64000",
            "GENERICAGENT_STREAM": "false",
            "GENERICAGENT_VERIFY": "true",
            "GENERICAGENT_TIMEOUT": "8",
            "GENERICAGENT_READ_TIMEOUT": "120",
            "GENERICAGENT_MAX_RETRIES": "2",
        }

        with patch.dict(os.environ, env, clear=True):
            mykeys = llmcore._load_env_mykeys()

        cfg = mykeys["native_oai_env_config"]
        self.assertEqual(cfg["name"], "qwen-env")
        self.assertEqual(cfg["apikey"], "sk-test")
        self.assertEqual(cfg["apibase"], "https://example.invalid/v1")
        self.assertEqual(cfg["model"], "qwen-thinking")
        self.assertEqual(cfg["api_mode"], "responses")
        self.assertEqual(cfg["reasoning_effort"], "high")
        self.assertEqual(cfg["service_tier"], "priority")
        self.assertEqual(cfg["max_tokens"], 8192)
        self.assertEqual(cfg["temperature"], 0.7)
        self.assertEqual(cfg["context_win"], 64000)
        self.assertIs(cfg["stream"], False)
        self.assertIs(cfg["verify"], True)
        self.assertEqual(cfg["timeout"], 8)
        self.assertEqual(cfg["read_timeout"], 120)
        self.assertEqual(cfg["max_retries"], 2)

    def test_reload_mykeys_can_use_env_only_and_detect_changes(self):
        real_import = builtins.__import__
        real_exists = os.path.exists

        def import_without_mykey(name, *args, **kwargs):
            if name == "mykey":
                raise ImportError("No module named mykey", name="mykey")
            return real_import(name, *args, **kwargs)

        def exists_without_mykey_json(path):
            if str(path).endswith(("mykey.py", "mykey.json")):
                return False
            return real_exists(path)

        env = {
            "GENERICAGENT_API_KEY": "sk-test",
            "GENERICAGENT_API_BASE": "https://example.invalid/v1",
            "GENERICAGENT_MODEL": "qwen-a",
        }
        llmcore._mykey_path = None
        llmcore._mykey_mtime = None
        llmcore.__dict__.pop("mykeys", None)

        with (
            patch("builtins.__import__", side_effect=import_without_mykey),
            patch("os.path.exists", side_effect=exists_without_mykey_json),
            patch.dict(os.environ, env, clear=True),
        ):
            mykeys, changed = llmcore.reload_mykeys()
            cached, changed_again = llmcore.reload_mykeys()
            os.environ["GENERICAGENT_MODEL"] = "qwen-b"
            updated, changed_after_env_update = llmcore.reload_mykeys()

        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertTrue(changed_after_env_update)
        self.assertEqual(mykeys["native_oai_env_config"]["model"], "qwen-a")
        self.assertEqual(cached["native_oai_env_config"]["model"], "qwen-a")
        self.assertEqual(updated["native_oai_env_config"]["model"], "qwen-b")
        self.assertEqual(llmcore._mykey_path, llmcore._ENV_MYKEY_SOURCE)

    def test_env_source_rechecks_when_local_config_file_appears(self):
        with patch.dict(os.environ, {"GENERICAGENT_API_KEY": "sk-test", "GENERICAGENT_MODEL": "qwen-a"}, clear=True):
            llmcore._mykey_path = llmcore._ENV_MYKEY_SOURCE
            llmcore._mykey_mtime = ("env", llmcore._env_signature())

            with patch("os.path.exists", return_value=True):
                self.assertIsNone(llmcore._source_signature())


if __name__ == "__main__":
    unittest.main()
