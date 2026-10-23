import logging
import re
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.models.db.memory import Memory
from backend.repositories.memory_repository import MemoryRepository
from backend.repositories.user_repository import UserRepository
from backend.services.exceptions import (
    MemoryNotFound,
    UserNotFound,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Patterns to detect sensitive information (credentials, secrets, tokens)
SENSITIVE_PATTERNS = [
    (r"(?i)\b(?:password|passwd|pwd|secret)\s*(?:is|[:=])\s*\S+", "password/secret"),
    (r"\bsk-[A-Za-z0-9_-]{20,}\b", "OpenAI API key"),
    (r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", "Anthropic API key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "GitHub token"),
    (r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}\b", "Bearer token"),
    (r"-----BEGIN\s+(?:[A-Z0-9_-]+\s+)?PRIVATE\s+KEY-----", "Private key"),
    (r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token)\s*(?:is|[:=])\s*['\"]?[a-zA-Z0-9_\-\.]{16,}['\"]?", "API token"),
]


def detect_sensitive_information(text: str) -> list[str]:
    """
    Check text for potentially sensitive credentials and secrets.
    Returns a list of detected pattern labels.
    """
    detected = []
    for pattern, label in SENSITIVE_PATTERNS:
        if re.search(pattern, text):
            detected.append(label)
    return detected


class MemoryService:
    """
    Coordinates durable long-term memory operations with strict user ownership enforcement,
    sensitive information filtering, and deterministic retrieval.
    """

    def __init__(
        self,
        db: Session,
        memory_repository: MemoryRepository | None = None,
        user_repository: UserRepository | None = None,
    ):
        self.db = db
        self.memory_repo = memory_repository or MemoryRepository(db)
        self.user_repo = user_repository or UserRepository(db)

    def _validate_user_exists(self, user_id: UUID) -> None:
        """Validate that user exists in database."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFound(f"User with ID {user_id} was not found.")

    def _validate_content_and_type(
        self,
        content: str | None = None,
        memory_type: str | None = None,
        allow_sensitive: bool = False,
    ) -> tuple[str | None, str | None]:
        """Validate content and memory_type bounds and sensitive information."""
        clean_content = None
        if content is not None:
            clean_content = content.strip()
            if not clean_content:
                raise ValidationError("Memory content cannot be empty.")
            if len(clean_content) > 5000:
                raise ValidationError("Memory content cannot exceed 5000 characters.")

            if not allow_sensitive:
                detected_sensitive = detect_sensitive_information(clean_content)
                if detected_sensitive:
                    raise ValidationError(
                        f"Memory content rejected: contains potentially sensitive information "
                        f"({', '.join(detected_sensitive)}). Avoid storing credentials in long-term memory."
                    )

        clean_type = None
        if memory_type is not None:
            clean_type = memory_type.strip()
            if not clean_type:
                raise ValidationError("Memory type cannot be empty.")
            if len(clean_type) > 50:
                raise ValidationError("Memory type cannot exceed 50 characters.")

        return clean_content, clean_type

    def create_memory(
        self,
        user_id: UUID,
        content: str,
        memory_type: str = "preference",
        allow_sensitive: bool = False,
    ) -> Memory:
        """
        Create a durable long-term memory record scoped to a user.
        Rejects sensitive data by default.
        """
        self._validate_user_exists(user_id)

        clean_content, clean_type = self._validate_content_and_type(
            content=content,
            memory_type=memory_type,
            allow_sensitive=allow_sensitive,
        )

        memory = Memory(
            id=uuid4(),
            user_id=user_id,
            content=clean_content or "",
            memory_type=clean_type or "preference",
        )

        self.memory_repo.create(memory)
        self.db.commit()
        self.db.refresh(memory)
        logger.info(
            "Created durable memory %s for user %s (type: %s)",
            memory.id,
            user_id,
            memory.memory_type,
        )
        return memory

    def get_memory(
        self,
        memory_id: UUID,
        user_id: UUID | None = None,
    ) -> Memory:
        """
        Retrieve a memory by ID with strict ownership validation.
        Prevents leaking another user's memories.
        """
        memory = self.memory_repo.get_by_id(memory_id)
        if not memory:
            raise MemoryNotFound(f"Memory with ID {memory_id} was not found.")

        # Visibility Rule: Never retrieve another user's memory
        if user_id is not None and memory.user_id != user_id:
            raise MemoryNotFound(f"Memory with ID {memory_id} was not found.")

        return memory

    def list_memories(
        self,
        user_id: UUID,
        memory_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Memory], int]:
        """
        List durable memories scoped to user.
        """
        if page < 1:
            raise ValidationError("Page number must be >= 1.")
        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be between 1 and 100.")

        self._validate_user_exists(user_id)

        skip = (page - 1) * page_size
        clean_type = memory_type.strip() if memory_type else None

        memories = self.memory_repo.list_scoped_memories(
            user_id=user_id,
            memory_type=clean_type,
            skip=skip,
            limit=page_size,
        )
        total = self.memory_repo.count_scoped_memories(
            user_id=user_id,
            memory_type=clean_type,
        )
        return memories, total

    def update_memory(
        self,
        memory_id: UUID,
        content: str | None = None,
        memory_type: str | None = None,
        user_id: UUID | None = None,
        allow_sensitive: bool = False,
    ) -> Memory:
        """
        Update durable memory content or type with ownership and validation enforcement.
        """
        if content is None and memory_type is None:
            raise ValidationError("At least one field (content or memory_type) must be provided to update.")

        memory = self.get_memory(memory_id=memory_id, user_id=user_id)

        clean_content, clean_type = self._validate_content_and_type(
            content=content,
            memory_type=memory_type,
            allow_sensitive=allow_sensitive,
        )

        self.memory_repo.update(
            memory=memory,
            content=clean_content,
            memory_type=clean_type,
        )
        self.db.commit()
        self.db.refresh(memory)
        logger.info("Updated durable memory %s", memory.id)
        return memory

    def delete_memory(
        self,
        memory_id: UUID,
        user_id: UUID | None = None,
    ) -> None:
        """
        Delete a durable memory record with strict ownership checks.
        """
        memory = self.get_memory(memory_id=memory_id, user_id=user_id)
        self.memory_repo.delete(memory)
        self.db.commit()
        logger.info("Deleted durable memory %s", memory_id)

    def get_generation_memories(
        self,
        user_id: UUID,
        limit: int = 5,
    ) -> list[Memory]:
        """
        Deterministic retrieval for RAG generation context according to strict visibility rules:
        - Never retrieve another user's memory.
        - Returns newest durable memories first.
        - SQL-based only (no vector memory).
        """
        return self.memory_repo.get_scoped_memories(
            user_id=user_id,
            limit=limit,
        )
