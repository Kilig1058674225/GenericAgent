import json
import unittest

from model_profiles import (
    format_model_profile_summary,
    summarize_model_profile,
    summarize_model_profiles,
)


class ModelProfileSummaryTests(unittest.TestCase):
    def test_profile_summary_does_not_expose_secrets(self):
        cfg = {
            "name": "primary sk-secret-in-name123456",
            "model": "qwen-thinking bearer hiddenmodeltoken",
            "apikey": "sk-secret1234567890",
            "apibase": "https://user:pass@example.invalid/v1?api_key=hidden#frag",
            "api_mode": "responses",
        }

        summary = summarize_model_profile("native_oai_config_secret=hidden", cfg)
        rendered = json.dumps(summary, ensure_ascii=False) + "\n" + format_model_profile_summary(summary)

        self.assertIn("example.invalid/v1", rendered)
        self.assertIn("qwen-thinking", rendered)
        self.assertNotIn("sk-secret", rendered)
        self.assertNotIn("hiddenmodeltoken", rendered)
        self.assertNotIn("secret=hidden", rendered)
        self.assertNotIn("user:pass", rendered)
        self.assertNotIn("api_key=hidden", rendered)
        self.assertNotIn("#frag", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_summarize_model_profiles_filters_non_model_entries(self):
        profiles = summarize_model_profiles(
            {
                "native_oai_config": {"model": "qwen", "apikey": "sk-secret", "apibase": "https://api.example/v1"},
                "discord_bot_token": "token",
                "plain_settings": {"enabled": True},
            }
        )

        self.assertEqual([profile["profile"] for profile in profiles], ["native_oai_config"])


if __name__ == "__main__":
    unittest.main()
