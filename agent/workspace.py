"""Workspace filesystem service for generated project management."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import re
import shutil
import tempfile
import threading
from uuid import uuid4
import zipfile

MAX_EDITABLE_FILE_CHARS = 400_000
SESSION_TTL_SECONDS = 60 * 60
DEFAULT_WORKSPACE_ID = "default"

BASE_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_BASE_DIR = (Path(tempfile.gettempdir()) / "agent-co-workspaces").resolve()
# Backward-compatibility alias for tests and legacy patches.
WORKSPACE_ROOT = (WORKSPACE_BASE_DIR / DEFAULT_WORKSPACE_ID).resolve()

_WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ACTIVE_WORKSPACE_ID: ContextVar[str | None] = ContextVar("active_workspace_id", default=None)
_SESSIONS_LOCK = threading.RLock()


class WorkspaceValidationError(ValueError):
    """Raised when workspace input is invalid."""


class WorkspaceConflictError(RuntimeError):
    """Raised when an operation conflicts with existing filesystem state."""


class WorkspaceBinaryFileError(ValueError):
    """Raised when a file is not UTF-8 text and cannot be edited as text."""


@dataclass(frozen=True)
class WorkspaceTreeNode:
    name: str
    path: str
    type: str
    size: int | None = None
    children: list["WorkspaceTreeNode"] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "path": self.path,
            "type": self.type,
        }
        if self.size is not None:
            payload["size"] = self.size
        if self.children is not None:
            payload["children"] = [child.to_dict() for child in self.children]
        return payload


@dataclass
class WorkspaceSession:
    workspace_id: str
    path: Path
    last_accessed: datetime
    expires_at: datetime
    ttl_seconds: int

    def to_public(self) -> dict[str, str]:
        return {
            "workspace_id": self.workspace_id,
            "expires_at": self.expires_at.isoformat(),
        }


_SESSIONS: dict[str, WorkspaceSession] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_workspace_id(workspace_id: str | None) -> str:
    value = (workspace_id or "").strip()
    if not value:
        return DEFAULT_WORKSPACE_ID
    if not _WORKSPACE_ID_PATTERN.fullmatch(value):
        raise WorkspaceValidationError(
            "workspace_id must match [A-Za-z0-9_-] and be <= 128 characters."
        )
    return value


def _session_path(workspace_id: str) -> Path:
    if workspace_id == DEFAULT_WORKSPACE_ID:
        return WORKSPACE_ROOT
    return (workspace_base_dir() / workspace_id).resolve()


def _context_workspace_id() -> str | None:
    return _ACTIVE_WORKSPACE_ID.get()


def _effective_workspace_id(explicit_workspace_id: str | None) -> str:
    if explicit_workspace_id is not None and str(explicit_workspace_id).strip():
        return _normalize_workspace_id(explicit_workspace_id)
    context_workspace_id = _context_workspace_id()
    if context_workspace_id is not None and context_workspace_id.strip():
        return _normalize_workspace_id(context_workspace_id)
    return DEFAULT_WORKSPACE_ID


@contextmanager
def workspace_context(workspace_id: str | None):
    """Bind a workspace id to the current context for tool-based operations."""
    normalized = _effective_workspace_id(workspace_id)
    token = _ACTIVE_WORKSPACE_ID.set(normalized)
    try:
        ensure_session(normalized)
        yield normalized
    finally:
        _ACTIVE_WORKSPACE_ID.reset(token)


def workspace_base_dir() -> Path:
    WORKSPACE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_BASE_DIR


def _new_session(workspace_id: str, ttl_seconds: int) -> WorkspaceSession:
    now = _utc_now()
    path = _session_path(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    return WorkspaceSession(
        workspace_id=workspace_id,
        path=path,
        last_accessed=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
        ttl_seconds=ttl_seconds,
    )


def _session_expired(session: WorkspaceSession, now: datetime) -> bool:
    return now >= session.expires_at


def ensure_session(
    workspace_id: str | None = None,
    *,
    ttl_seconds: int = SESSION_TTL_SECONDS,
) -> WorkspaceSession:
    normalized = _effective_workspace_id(workspace_id)
    now = _utc_now()
    expected_path = _session_path(normalized)

    with _SESSIONS_LOCK:
        existing = _SESSIONS.get(normalized)
        if existing is not None:
            # Support test/runtime patching of WORKSPACE_ROOT by refreshing stale
            # in-memory session paths when the resolved target root changes.
            if existing.path.resolve() != expected_path.resolve():
                _SESSIONS.pop(normalized, None)
                existing = None

        if existing is not None:
            if _session_expired(existing, now):
                delete_session(normalized)
            else:
                existing.last_accessed = now
                existing.expires_at = now + timedelta(seconds=existing.ttl_seconds)
                existing.path = expected_path
                existing.path.mkdir(parents=True, exist_ok=True)
                return existing

        session = _new_session(normalized, ttl_seconds)
        _SESSIONS[normalized] = session
        return session


def create_session(*, ttl_seconds: int = SESSION_TTL_SECONDS) -> WorkspaceSession:
    with _SESSIONS_LOCK:
        while True:
            candidate = uuid4().hex
            if candidate not in _SESSIONS:
                break
    return ensure_session(candidate, ttl_seconds=ttl_seconds)


def touch_session(workspace_id: str, *, ttl_seconds: int | None = None) -> WorkspaceSession:
    normalized = _normalize_workspace_id(workspace_id)
    with _SESSIONS_LOCK:
        session = ensure_session(normalized)
        now = _utc_now()
        session.last_accessed = now
        if ttl_seconds is not None:
            session.ttl_seconds = ttl_seconds
        session.expires_at = now + timedelta(seconds=session.ttl_seconds)
        return session


def cleanup_expired_sessions() -> list[str]:
    now = _utc_now()
    expired: list[str] = []
    with _SESSIONS_LOCK:
        for workspace_id, session in list(_SESSIONS.items()):
            if _session_expired(session, now):
                expired.append(workspace_id)
        for workspace_id in expired:
            delete_session(workspace_id)
    return expired


def delete_session(workspace_id: str) -> bool:
    normalized = _normalize_workspace_id(workspace_id)
    with _SESSIONS_LOCK:
        session = _SESSIONS.pop(normalized, None)
    target = session.path if session is not None else _session_path(normalized)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        return True
    return False


def resolve_workspace_session(workspace_id: str | None = None) -> WorkspaceSession:
    cleanup_expired_sessions()
    return ensure_session(workspace_id)


def workspace_root(workspace_id: str | None = None) -> Path:
    return resolve_workspace_session(workspace_id).path


def _coerce_relative_path(path: str, *, allow_root: bool = False) -> str:
    value = (path or "").strip()
    if not value or value == ".":
        if allow_root:
            return "."
        raise WorkspaceValidationError("path must not be empty.")

    raw_path = Path(value)
    if raw_path.is_absolute():
        raise WorkspaceValidationError("Absolute paths are not allowed.")
    if raw_path.drive:
        raise WorkspaceValidationError("Drive-qualified paths are not allowed.")
    return value


def resolve_workspace_path(
    path: str,
    *,
    allow_root: bool = False,
    workspace_id: str | None = None,
) -> Path:
    """Resolve a relative path into the workspace root with traversal protection."""
    root = workspace_root(workspace_id)
    relative = _coerce_relative_path(path, allow_root=allow_root)
    candidate = root if relative == "." else (root / relative)
    resolved = candidate.resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceValidationError("Path escapes workspace root.") from exc
    return resolved


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sorted_entries(directory: Path) -> list[Path]:
    return sorted(
        directory.iterdir(),
        key=lambda entry: (entry.is_file(), entry.name.lower()),
    )


def _tree_for_path(path: Path, root: Path) -> WorkspaceTreeNode:
    rel_path = _relative_path(path, root)
    if path.is_dir():
        children = [_tree_for_path(child, root) for child in _sorted_entries(path)]
        return WorkspaceTreeNode(
            name=path.name,
            path=rel_path,
            type="directory",
            children=children,
        )
    return WorkspaceTreeNode(
        name=path.name,
        path=rel_path,
        type="file",
        size=path.stat().st_size,
    )


def list_tree(workspace_id: str | None = None) -> list[dict[str, object]]:
    root = workspace_root(workspace_id)
    nodes = [_tree_for_path(path, root).to_dict() for path in _sorted_entries(root)]
    return nodes


def list_relative_files(directory: str = ".", workspace_id: str | None = None) -> list[str]:
    target = resolve_workspace_path(directory, allow_root=True, workspace_id=workspace_id)
    if not target.exists():
        raise FileNotFoundError(f"{directory} does not exist.")
    if not target.is_dir():
        raise WorkspaceValidationError(f"{directory} is not a directory.")

    root = workspace_root(workspace_id)
    files = [path.relative_to(root).as_posix() for path in target.rglob("*") if path.is_file()]
    return sorted(files)


def list_flat_text_files(
    workspace_id: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    root = workspace_root(workspace_id)
    files: dict[str, str] = {}
    skipped_binary: list[str] = []

    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()):
        rel = path.relative_to(root).as_posix()
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped_binary.append(rel)

    return files, skipped_binary


def read_text_file(path: str, workspace_id: str | None = None) -> str:
    target = resolve_workspace_path(path, workspace_id=workspace_id)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"{path} does not exist.")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceBinaryFileError(f"{path} is binary and cannot be edited as text.") from exc


def write_text_file(path: str, content: str, workspace_id: str | None = None) -> str:
    if len(content) > MAX_EDITABLE_FILE_CHARS:
        raise WorkspaceValidationError(
            f"content exceeds {MAX_EDITABLE_FILE_CHARS} characters. Current length: {len(content)}"
        )

    root = workspace_root(workspace_id)
    target = resolve_workspace_path(path, workspace_id=workspace_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return _relative_path(target, root)


def create_folder(path: str, workspace_id: str | None = None) -> str:
    root = workspace_root(workspace_id)
    target = resolve_workspace_path(path, workspace_id=workspace_id)
    target.mkdir(parents=True, exist_ok=True)
    return _relative_path(target, root)


def delete_path(path: str, *, recursive: bool = False, workspace_id: str | None = None) -> str:
    target = resolve_workspace_path(path, workspace_id=workspace_id)
    if not target.exists():
        raise FileNotFoundError(f"{path} does not exist.")

    if target.is_dir():
        has_children = any(target.iterdir())
        if has_children and not recursive:
            raise WorkspaceConflictError(
                f"{path} is a non-empty directory. Use recursive=true to delete."
            )
        if has_children:
            shutil.rmtree(target)
        else:
            target.rmdir()
    else:
        target.unlink()
    return path.strip().replace("\\", "/")


def rename_path(
    from_path: str,
    to_path: str,
    *,
    overwrite: bool = False,
    workspace_id: str | None = None,
) -> str:
    root = workspace_root(workspace_id)
    source = resolve_workspace_path(from_path, workspace_id=workspace_id)
    target = resolve_workspace_path(to_path, workspace_id=workspace_id)

    if not source.exists():
        raise FileNotFoundError(f"{from_path} does not exist.")

    if target.exists():
        if not overwrite:
            raise WorkspaceConflictError(f"{to_path} already exists.")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return _relative_path(target, root)


def build_workspace_zip(workspace_id: str | None = None) -> bytes:
    root = workspace_root(workspace_id)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()):
            archive.write(path, arcname=path.relative_to(root).as_posix())
    return buffer.getvalue()
