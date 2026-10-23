from __future__ import annotations

import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

from fastapi.testclient import TestClient

from agent.api import app


class WorkspaceDownloadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (Path.cwd() / "tests" / ".tmp" / f"ws_{uuid4().hex}" / "generated_project").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._patch = patch("agent.workspace.WORKSPACE_ROOT", self.root)
        self._patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._patch.stop()
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def test_workspace_download_returns_zip(self) -> None:
        (self.root / "README.md").write_text("workspace", encoding="utf-8")
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "main.py").write_text("print('ok')", encoding="utf-8")

        response = self.client.get("/workspace/download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("generated_project.zip", response.headers["content-disposition"])

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(sorted(archive.namelist()), ["README.md", "src/main.py"])
        self.assertEqual(archive.read("README.md").decode("utf-8"), "workspace")


if __name__ == "__main__":
    unittest.main()
