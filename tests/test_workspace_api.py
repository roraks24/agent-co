from __future__ import annotations

from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

import agent.api as api_module
from agent.api import app


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (Path.cwd() / "tests" / ".tmp" / f"ws_{uuid4().hex}" / "generated_project").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._patch = patch("agent.workspace.WORKSPACE_ROOT", self.root)
        self._patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._patch.stop()
        shutil.rmtree(self.root.parent, ignore_errors=True)

    def test_create_folder_and_list_tree(self) -> None:
        response = self.client.post("/workspace/folder", json={"path": "src/components"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], "src/components")

        tree_response = self.client.get("/workspace/tree")
        self.assertEqual(tree_response.status_code, 200)
        tree = tree_response.json()
        self.assertEqual(tree["root"], "generated_project")
        self.assertTrue(any(node["path"] == "src" for node in tree["nodes"]))

    def test_write_and_read_file(self) -> None:
        write_response = self.client.put(
            "/workspace/file",
            json={"path": "src/app.py", "content": "print('hello')"},
        )
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(write_response.json()["path"], "src/app.py")

        read_response = self.client.get("/workspace/file", params={"path": "src/app.py"})
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["content"], "print('hello')")

    def test_rename_and_delete_path(self) -> None:
        self.client.put("/workspace/file", json={"path": "main.py", "content": "x"})

        with patch("agent.api.workspace_service.rename_path", return_value="src/main.py") as mock_rename:
            rename_response = self.client.post(
                "/workspace/rename",
                json={"from_path": "main.py", "to_path": "src/main.py"},
            )
        self.assertEqual(rename_response.status_code, 200)
        self.assertEqual(rename_response.json()["path"], "src/main.py")
        self.assertEqual(mock_rename.call_count, 1)
        rename_call = mock_rename.call_args
        self.assertEqual(rename_call.args, ("main.py", "src/main.py"))
        self.assertFalse(rename_call.kwargs.get("overwrite"))
        self.assertEqual(rename_call.kwargs.get("workspace_id"), rename_response.json()["workspace_id"])

        with patch("agent.api.workspace_service.delete_path", return_value="src/main.py") as mock_delete:
            delete_response = self.client.delete(
                "/workspace/path",
                params={"path": "src/main.py", "recursive": False},
            )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["path"], "src/main.py")
        self.assertEqual(mock_delete.call_count, 1)
        delete_call = mock_delete.call_args
        self.assertEqual(delete_call.args, ("src/main.py",))
        self.assertFalse(delete_call.kwargs.get("recursive"))
        self.assertEqual(delete_call.kwargs.get("workspace_id"), delete_response.json()["workspace_id"])

    def test_non_recursive_directory_delete_conflict(self) -> None:
        self.client.put("/workspace/file", json={"path": "src/a.py", "content": "x"})

        delete_response = self.client.delete(
            "/workspace/path",
            params={"path": "src", "recursive": False},
        )
        self.assertEqual(delete_response.status_code, 409)
        self.assertEqual(delete_response.json()["error"]["code"], "workspace_conflict")

    def test_traversal_is_rejected(self) -> None:
        response = self.client.put(
            "/workspace/file",
            json={"path": "../escape.py", "content": "x"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "workspace_validation_error")

    def test_workspace_files_returns_flat_map_and_binary_skips(self) -> None:
        (self.root / "text.txt").write_text("hello", encoding="utf-8")
        (self.root / "binary.bin").write_bytes(b"\xff\xfe\xfd")

        response = self.client.get("/workspace/files")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("text.txt", payload["files"])
        self.assertIn("binary.bin", payload["skipped_binary"])

    def test_workspace_session_create_and_delete(self) -> None:
        create_response = self.client.post("/workspace/session")
        self.assertEqual(create_response.status_code, 200)
        session_payload = create_response.json()
        workspace_id = session_payload["workspace_id"]
        self.assertTrue(workspace_id)
        self.assertIn("expires_at", session_payload)

        write_response = self.client.put(
            "/workspace/file",
            json={"path": "session.txt", "content": "scoped"},
            headers={"X-Workspace-ID": workspace_id},
        )
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(write_response.json()["workspace_id"], workspace_id)

        files_response = self.client.get("/workspace/files", headers={"X-Workspace-ID": workspace_id})
        self.assertEqual(files_response.status_code, 200)
        self.assertEqual(files_response.json()["workspace_id"], workspace_id)
        self.assertIn("session.txt", files_response.json()["files"])

        delete_response = self.client.delete(f"/workspace/session/{workspace_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])

    def test_workspace_requires_api_key_when_secure_mode_enabled(self) -> None:
        with patch.object(api_module.SECURITY_CONFIG, "require_workspace_auth", True):
            unauthorized = self.client.get("/workspace/tree")
            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(unauthorized.json()["error"]["code"], "workspace_unauthorized")

            authorized = self.client.get("/workspace/tree", headers={"X-API-KEY": "test-key"})
            self.assertEqual(authorized.status_code, 200)


if __name__ == "__main__":
    unittest.main()
