from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID

from backend.core.config import BASE_DIR


def calculate_sha256(
    file_path: Path | str,
    chunk_size: int = 1024 * 1024,
) -> str:
    """
    Calculate the SHA-256 checksum of a file.

    The file is read in chunks instead of loading the entire file
    into memory at once.

    Args:
        file_path: Path to the source file.
        chunk_size: Number of bytes to read per iteration.

    Returns:
        A 64-character lowercase hexadecimal SHA-256 digest.

    Raises:
        FileNotFoundError: If the file does not exist.
        IsADirectoryError: If the path points to a directory.
        ValueError: If chunk_size is invalid.
    """
    path = Path(file_path)

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    if not path.is_file():
        raise IsADirectoryError(f"Path is not a file: {path}")

    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


def _sanitize_filename(filename: str) -> str:
    """
    Convert a client-provided filename into a safe single path component.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename cannot be empty.")

    safe_name = Path(filename).name.strip()

    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("Invalid filename.")

    return safe_name


def build_storage_key(
    document_id: UUID,
    filename: str,
) -> str:
    """
    Build the stable relative storage key for a document artifact.

    Example:
        documents/<document_id>/original/research.pdf

    The returned value is always a relative POSIX-style path.
    """
    safe_name = _sanitize_filename(filename)

    return (
        f"documents/"
        f"{document_id}/"
        f"original/"
        f"{safe_name}"
    )


def _resolve_storage_key(storage_key: str) -> Path:
    """
    Resolve a storage key to a physical path safely.

    Only paths inside the project's documents directory are allowed.
    """
    if not storage_key or not storage_key.strip():
        raise ValueError("Storage key cannot be empty.")

    relative_path = Path(storage_key)

    # Reject absolute paths such as:
    # C:\\...
    # /var/...
    if relative_path.is_absolute():
        raise ValueError("Storage key must be relative.")

    # Reject traversal components such as:
    # ../secret.txt
    # documents/../../secret.txt
    if ".." in relative_path.parts:
        raise ValueError("Storage key cannot contain path traversal.")

    documents_dir = (BASE_DIR / "documents").resolve()
    resolved_path = (BASE_DIR / relative_path).resolve()

    try:
        resolved_path.relative_to(documents_dir)
    except ValueError as exc:
        raise ValueError(
            "Storage key must resolve inside the documents directory."
        ) from exc

    return resolved_path


def save_artifact(
    source_path: Path | str,
    document_id: UUID,
    filename: str,
) -> str:
    """
    Persist an uploaded source artifact.

    Returns:
        The relative storage_key that should be stored in PostgreSQL.

    Raises:
        FileNotFoundError: If source_path does not exist.
        IsADirectoryError: If source_path is a directory.
        ValueError: If the filename/storage location is invalid.
    """
    source = Path(source_path)

    if not source.exists():
        raise FileNotFoundError(f"Source file does not exist: {source}")

    if not source.is_file():
        raise IsADirectoryError(f"Source path is not a file: {source}")

    storage_key = build_storage_key(
        document_id=document_id,
        filename=filename,
    )

    destination = _resolve_storage_key(storage_key)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copyfile(source, destination)

    return storage_key


def delete_artifact(storage_key: str) -> None:
    """
    Delete a persisted document artifact.

    Deletion is intentionally idempotent:
    if the physical file is already missing, this function succeeds.
    """
    artifact_path = _resolve_storage_key(storage_key)

    if not artifact_path.exists():
        return

    if not artifact_path.is_file():
        raise IsADirectoryError(
            f"Storage key does not point to a file: {storage_key}"
        )

    artifact_path.unlink()

    # Remove empty parent directories created for this document.
    # This cleanup is best-effort and does not affect successful
    # file deletion.
    try:
        original_dir = artifact_path.parent
        document_dir = original_dir.parent

        if original_dir.exists() and not any(original_dir.iterdir()):
            original_dir.rmdir()

        if document_dir.exists() and not any(document_dir.iterdir()):
            document_dir.rmdir()

    except OSError:
        pass