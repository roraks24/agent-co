from __future__ import annotations

import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

from agent import workspace


class WorkspaceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (Path.cwd() / "tests" / ".tmp" / f"ws_{uuid4().hex}" / "generated_project").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._patch = patch("agent.workspace.WORKSPACE_ROOT", self.root)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def test_traversal_is_rejected(self) -> None:
        with self.assertRaises(workspace.WorkspaceValidationError):
            workspace.resolve_workspace_path("../escape.txt")

    def test_write_and_read_roundtrip(self) -> None:
        workspace.write_text_file("src/app.py", "print('ok')")
        content = workspace.read_text_file("src/app.py")
        self.assertEqual(content, "print('ok')")

    def test_list_tree_and_files(self) -> None:
        workspace.write_text_file("a.txt", "a")
        workspace.write_text_file("src/main.py", "b")

        nodes = workspace.list_tree()
        top_level_paths = [node["path"] for node in nodes]
        self.assertEqual(top_level_paths, ["src", "a.txt"])

        files, skipped_binary = workspace.list_flat_text_files()
        self.assertEqual(sorted(files.keys()), ["a.txt", "src/main.py"])
        self.assertEqual(skipped_binary, [])

    def test_rename_conflict_without_overwrite(self) -> None:
        workspace.write_text_file("a.txt", "a")
        workspace.write_text_file("b.txt", "b")

        with self.assertRaises(workspace.WorkspaceConflictError):
            workspace.rename_path("a.txt", "b.txt", overwrite=False)

    def test_delete_directory_requires_recursive(self) -> None:
        workspace.write_text_file("src/a.py", "x")

        with self.assertRaises(workspace.WorkspaceConflictError):
            workspace.delete_path("src", recursive=False)

        with patch("agent.workspace.shutil.rmtree") as mock_rmtree:
            deleted = workspace.delete_path("src", recursive=True)

        self.assertEqual(deleted, "src")
        mock_rmtree.assert_called_once()

    def test_zip_contains_workspace_files(self) -> None:
        workspace.write_text_file("README.md", "hello")
        workspace.write_text_file("src/main.py", "print('zip')")

        archive_bytes = workspace.build_workspace_zip()
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))

        names = sorted(archive.namelist())
        self.assertEqual(names, ["README.md", "src/main.py"])
        self.assertEqual(archive.read("README.md").decode("utf-8"), "hello")


if __name__ == "__main__":
    unittest.main()
