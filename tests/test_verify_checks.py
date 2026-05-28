import subprocess
import tempfile
import unittest
from pathlib import Path

from verify_checks import collect_configured_secret_values, git_candidate_files, scan_files_for_likely_secrets, scan_files_for_values


class VerifyChecksTests(unittest.TestCase):
    def test_collect_configured_secret_values_uses_secret_fields_only(self):
        configured_secret = "sk-" + "realisticsecret1234567890"
        nested_secret = "Bearer " + "nestedsecret123"
        env_secret = "sk-" + "envsecret1234567890"
        values = collect_configured_secret_values(
            mykeys={
                "native_oai_config": {
                    "apikey": configured_secret,
                    "model": "qwen",
                    "apibase": "https://api.example/v1",
                    "nested": {"authorization": nested_secret},
                },
                "plain": {"value": "not-a-secret"},
            },
            environ={"GENERICAGENT_API_KEY": env_secret, "GENERICAGENT_MODEL": "qwen"},
        )

        self.assertIn(configured_secret, values)
        self.assertIn(nested_secret, values)
        self.assertIn(env_secret, values)
        self.assertNotIn("qwen", values)
        self.assertNotIn("https://api.example/v1", values)

    def test_scan_files_for_values_reports_path_without_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            leaked = root / "tracked.txt"
            safe = root / "safe.txt"
            secret = "sk-" + "realisticsecret1234567890"
            leaked.write_text(f"value={secret}", encoding="utf-8")
            safe.write_text("nothing here", encoding="utf-8")

            matches = scan_files_for_values([secret], [leaked, safe], root)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["path"], "tracked.txt")
        self.assertNotIn(secret, str(matches))

    def test_scan_files_for_likely_secrets_reports_location_without_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            leaked = root / "tracked.txt"
            safe = root / "safe.txt"
            secret = "sk-" + "leakedsecret1234567890"
            bearer = "Bearer " + "abcdefghijklmnop"
            leaked.write_text(f"apikey = '{secret}'\nheader = '{bearer}'\n", encoding="utf-8")
            safe.write_text("apikey = 'placeholder-token-value'\n", encoding="utf-8")

            matches = scan_files_for_likely_secrets([leaked, safe], root)

        self.assertEqual([match["path"] for match in matches], ["tracked.txt", "tracked.txt"])
        self.assertEqual([match["line"] for match in matches], ["1", "2"])
        self.assertEqual([match["kind"] for match in matches], ["secret_assignment", "bearer_token"])
        self.assertNotIn(secret, str(matches))
        self.assertNotIn(bearer, str(matches))

    def test_git_candidate_files_can_include_untracked_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=root, capture_output=True, check=True)
            tracked = root / "tracked.txt"
            untracked = root / "untracked.txt"
            ignored = root / "ignored.txt"
            (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            tracked.write_text("tracked", encoding="utf-8")
            untracked.write_text("untracked", encoding="utf-8")
            ignored.write_text("ignored", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt", ".gitignore"], cwd=root, capture_output=True, check=True)

            cached_only = {path.name for path in git_candidate_files(root, include_untracked=False)}
            candidates = {path.name for path in git_candidate_files(root, include_untracked=True)}

        self.assertIn("tracked.txt", cached_only)
        self.assertNotIn("untracked.txt", cached_only)
        self.assertIn("tracked.txt", candidates)
        self.assertIn("untracked.txt", candidates)
        self.assertNotIn("ignored.txt", candidates)


if __name__ == "__main__":
    unittest.main()
