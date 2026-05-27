import json
import tempfile
import unittest
from pathlib import Path

import skill_registry
from skill_registry import (
    discover_skills,
    list_skills,
    set_skill_enabled,
    sync_registry,
    validate_registry,
)


class SkillRegistryTests(unittest.TestCase):
    def test_discover_skills_extracts_metadata_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "demo_sop.md").write_text(
                "# Demo SOP\n\nUse web_scan then file_read to inspect pages.\n",
                encoding="utf-8",
            )
            (root / "helper.py").write_text(
                '"""Helper Script\nSecond line."""\nimport requests\n',
                encoding="utf-8",
            )

            records = discover_skills(root=root)

        by_title = {record.title: record for record in records}
        self.assertIn("Demo SOP", by_title)
        self.assertIn("Helper Script", by_title)
        self.assertIn("network_access", by_title["Demo SOP"].required_permissions)
        self.assertIn("requests", by_title["Helper Script"].dependencies)

    def test_sync_preserves_enabled_state_and_validate_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "memory"
            root.mkdir()
            registry = Path(tmpdir) / "skill_registry.json"
            skill_file = root / "demo_sop.md"
            skill_file.write_text("# Demo SOP\n\nDo useful work.\n", encoding="utf-8")

            data = sync_registry(path=registry, root=root)
            skill_id = data["skills"][0]["id"]
            set_skill_enabled(skill_id, False, path=registry)
            data = sync_registry(path=registry, root=root)
            result = validate_registry(path=registry)

            stored = json.loads(registry.read_text(encoding="utf-8"))
            listed = list_skills(path=registry)

        self.assertFalse(data["skills"][0]["enabled"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["skills"], 1)
        self.assertEqual(listed[0]["success_count"], stored["skills"][0]["success_count"])

    def test_validate_reports_missing_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = Path(tmpdir) / "skill_registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "skills": [
                            {
                                "id": "missing",
                                "title": "Missing",
                                "source_path": "memory/nope.md",
                                "enabled": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = validate_registry(path=registry)
            stored = json.loads(registry.read_text(encoding="utf-8"))

        self.assertFalse(result["ok"])
        self.assertEqual(stored["skills"][0]["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
