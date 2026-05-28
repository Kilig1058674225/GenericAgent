import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_loop import exhaust
from ga import GenericAgentHandler, file_patch
from workspace_guard import create_file_snapshot, list_snapshots, restore_snapshot, snapshot_index_path


class WorkspaceGuardTests(unittest.TestCase):
    def test_snapshot_restore_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "notes.txt"
            target.write_text("before", encoding="utf-8")
            env = {"GA_SNAPSHOT_DIR": str(Path(tmpdir) / "snapshots"), "GA_AUDIT_DIR": str(Path(tmpdir) / "audit")}
            with patch.dict(os.environ, env, clear=False):
                snap = create_file_snapshot(target, reason="test", tool_name="unit")
                target.write_text("after", encoding="utf-8")
                restored = restore_snapshot(snap["snapshot_id"], create_pre_restore_snapshot=False)
                restored_text = target.read_text(encoding="utf-8")

        self.assertEqual(restored["status"], "success")
        self.assertEqual(restored_text, "before")

    def test_snapshot_restore_created_file_deletes_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "created.txt"
            env = {"GA_SNAPSHOT_DIR": str(Path(tmpdir) / "snapshots"), "GA_AUDIT_DIR": str(Path(tmpdir) / "audit")}
            with patch.dict(os.environ, env, clear=False):
                snap = create_file_snapshot(target, reason="before create", tool_name="unit")
                target.write_text("created", encoding="utf-8")
                restored = restore_snapshot(snap["snapshot_id"], create_pre_restore_snapshot=False)
                exists_after_restore = target.exists()

        self.assertEqual(restored["action"], "deleted_created_file")
        self.assertFalse(exists_after_restore)

    def test_snapshot_restore_rejects_tampered_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "notes.txt"
            target.write_text("before", encoding="utf-8")
            env = {"GA_SNAPSHOT_DIR": str(Path(tmpdir) / "snapshots"), "GA_AUDIT_DIR": str(Path(tmpdir) / "audit")}
            with patch.dict(os.environ, env, clear=False):
                snap = create_file_snapshot(target, reason="test", tool_name="unit")
                record = list_snapshots(limit=1, target_path=target)[0]
                Path(record["snapshot_path"]).write_text("tampered", encoding="utf-8")
                target.write_text("after", encoding="utf-8")
                restored = restore_snapshot(snap["snapshot_id"], create_pre_restore_snapshot=False)
                restored_text = target.read_text(encoding="utf-8")

        self.assertEqual(restored["status"], "error")
        self.assertIn("hash mismatch", restored["msg"])
        self.assertEqual(restored_text, "after")

    def test_snapshot_restore_rejects_backup_outside_snapshot_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "notes.txt"
            outside_backup = Path(tmpdir) / "outside.bak"
            target.write_text("before", encoding="utf-8")
            outside_backup.write_text("before", encoding="utf-8")
            env = {"GA_SNAPSHOT_DIR": str(Path(tmpdir) / "snapshots"), "GA_AUDIT_DIR": str(Path(tmpdir) / "audit")}
            with patch.dict(os.environ, env, clear=False):
                snap = create_file_snapshot(target, reason="test", tool_name="unit")
                record = list_snapshots(limit=1, target_path=target)[0]
                record["snapshot_path"] = str(outside_backup)
                with open(snapshot_index_path(), "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                target.write_text("after", encoding="utf-8")
                restored = restore_snapshot(snap["snapshot_id"], create_pre_restore_snapshot=False)
                restored_text = target.read_text(encoding="utf-8")

        self.assertEqual(restored["status"], "error")
        self.assertIn("outside snapshot dir", restored["msg"])
        self.assertEqual(restored_text, "after")

    def test_file_patch_creates_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "patch.txt"
            target.write_text("hello old", encoding="utf-8")
            env = {"GA_SNAPSHOT_DIR": str(Path(tmpdir) / "snapshots"), "GA_AUDIT_DIR": str(Path(tmpdir) / "audit")}
            with patch.dict(os.environ, env, clear=False):
                result = file_patch(str(target), "old", "new")
                snapshots = list_snapshots(limit=1, target_path=target)
                restored = restore_snapshot(result["snapshot_id"], create_pre_restore_snapshot=False)
                restored_text = target.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(restored_text, "hello old")
        self.assertEqual(restored["status"], "success")

    def test_file_write_creates_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "write.txt"
            target.write_text("old", encoding="utf-8")
            parent = SimpleNamespace(verbose=False)
            handler = GenericAgentHandler(parent, last_history=[], cwd=tmpdir)
            response = SimpleNamespace(content="")
            env = {"GA_SNAPSHOT_DIR": str(Path(tmpdir) / "snapshots"), "GA_AUDIT_DIR": str(Path(tmpdir) / "audit")}
            with patch.dict(os.environ, env, clear=False):
                outcome = exhaust(handler.do_file_write({"path": "write.txt", "content": "new"}, response))
                restored = restore_snapshot(outcome.data["snapshot_id"], create_pre_restore_snapshot=False)
                restored_text = target.read_text(encoding="utf-8")

        self.assertEqual(outcome.data["status"], "success")
        self.assertEqual(restored["status"], "success")
        self.assertEqual(restored_text, "old")


if __name__ == "__main__":
    unittest.main()
