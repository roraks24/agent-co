"""Persistent workspace filesystem service for Agent Co in Rorak AI."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import shutil
import zipfile
from typing import Any, Optional

from backend.core.config import WORKSPACES_DIR
from agent.source_serializer import clean_transport_escapes

DEFAULT_WORKSPACE_ID = "default"
MAX_EDITABLE_FILE_CHARS = 500_000

_ACTIVE_WORKSPACE_ID: ContextVar[str | None] = ContextVar("active_workspace_id", default=None)


class WorkspaceValidationError(ValueError):
    """Raised when workspace path or input is invalid."""


class WorkspaceConflictError(RuntimeError):
    """Raised when an operation conflicts with existing filesystem state."""


class WorkspaceBinaryFileError(ValueError):
    """Raised when a file cannot be read as text."""


@dataclass(frozen=True)
class WorkspaceTreeNode:
    name: str
    path: str
    type: str  # "file" | "directory"
    size: Optional[int] = None
    children: Optional[list["WorkspaceTreeNode"]] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "type": self.type,
        }
        if self.size is not None:
            data["size"] = self.size
        if self.children is not None:
            data["children"] = [child.to_dict() for child in self.children]
        return data


def get_active_workspace_id() -> str:
    ws_id = _ACTIVE_WORKSPACE_ID.get()
    return ws_id if ws_id else DEFAULT_WORKSPACE_ID


@contextmanager
def workspace_context(workspace_id: Optional[str]):
    token = _ACTIVE_WORKSPACE_ID.set(workspace_id if workspace_id else DEFAULT_WORKSPACE_ID)
    try:
        yield
    finally:
        _ACTIVE_WORKSPACE_ID.reset(token)


def get_workspace_dir(workspace_id: Optional[str] = None) -> Path:
    ws_id = workspace_id or get_active_workspace_id()
    # Sanitize workspace_id
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", ws_id)
    if not safe_id:
        safe_id = DEFAULT_WORKSPACE_ID
    target_dir = (WORKSPACES_DIR / safe_id).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def resolve_safe_path(rel_path: str, workspace_id: Optional[str] = None) -> Path:
    root = get_workspace_dir(workspace_id)
    clean = rel_path.strip().replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        raise WorkspaceValidationError(f"Path traversal forbidden: '{rel_path}'")
    target = (root / clean).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise WorkspaceValidationError(f"Path escape forbidden: '{rel_path}'")
    return target


def write_text_file(path: str, content: str, workspace_id: Optional[str] = None) -> str:
    target = resolve_safe_path(path, workspace_id)
    root = get_workspace_dir(workspace_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    cleaned = clean_transport_escapes(content, file_path=path)
    target.write_text(cleaned, encoding="utf-8")
    return str(target.relative_to(root)).replace(chr(92), "/")


def read_text_file(path: str, workspace_id: Optional[str] = None) -> str:
    target = resolve_safe_path(path, workspace_id)
    if not target.exists():
        raise FileNotFoundError(f"File not found: '{path}'")
    if target.is_dir():
        raise IsADirectoryError(f"Target is a directory: '{path}'")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise WorkspaceBinaryFileError(f"Cannot read binary file as text: '{path}'")


def delete_file(path: str, workspace_id: Optional[str] = None) -> bool:
    target = resolve_safe_path(path, workspace_id)
    if not target.exists():
        return False
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return True


def list_relative_files(directory: str = ".", workspace_id: Optional[str] = None) -> list[str]:
    root = get_workspace_dir(workspace_id)
    target = resolve_safe_path(directory, workspace_id)
    if not target.exists():
        return []
    results: list[str] = []
    for item in target.rglob("*"):
        if item.is_file():
            rel = str(item.relative_to(root)).replace("\\", "/")
            results.append(rel)
    return sorted(results)


def list_tree(workspace_id: Optional[str] = None) -> list[dict[str, Any]]:
    root = get_workspace_dir(workspace_id)

    def _build(cur: Path) -> list[WorkspaceTreeNode]:
        nodes: list[WorkspaceTreeNode] = []
        try:
            entries = sorted(cur.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except Exception:
            return nodes

        for entry in entries:
            # Skip hidden runtime files
            if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                continue
            rel_path = str(entry.relative_to(root)).replace("\\", "/")
            if entry.is_dir():
                children = _build(entry)
                nodes.append(WorkspaceTreeNode(name=entry.name, path=rel_path, type="directory", children=children))
            else:
                nodes.append(WorkspaceTreeNode(name=entry.name, path=rel_path, type="file", size=entry.stat().st_size))
        return nodes

    tree_nodes = _build(root)
    return [n.to_dict() for n in tree_nodes]


def create_zip_archive(workspace_id: Optional[str] = None) -> bytes:
    root = get_workspace_dir(workspace_id)
    buffer = BytesIO()

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in root.rglob("*"):
            if not item.is_file():
                continue
            rel_str = str(item.relative_to(root)).replace("\\", "/")
            parts = rel_str.split("/")
            # Exclude secrets and internal directories
            if any(p.startswith(".") for p in parts) or any(p in ("__pycache__", "node_modules") for p in parts):
                continue
            if item.name.lower() in (".env", ".env.local", "id_rsa", "credentials.json"):
                continue
            zf.write(item, arcname=rel_str)

    buffer.seek(0)
    return buffer.getvalue()
