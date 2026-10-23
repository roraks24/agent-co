from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend import __version__


# ============================================================
# ENUMS
# ============================================================

class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class IngestionStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ============================================================
# PAGINATION
# ============================================================

class Pagination(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
        description="Current page number (1-indexed)",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Total number of items",
    )
    total_pages: int = Field(
        default=0,
        ge=0,
        description="Total number of pages",
    )


class PaginationParams(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
        description="Page number",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Page size",
    )


# ============================================================
# CHAT
# ============================================================

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The user's question",
    )
    conversation_id: Optional[UUID] = Field(
        default=None,
        description="Optional existing conversation thread ID to continue",
    )
    user_id: Optional[UUID] = Field(
        default=None,
        description="Optional user ID for scoping and memory",
    )
    custom_keys: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional user-provided external API keys and provider configuration",
    )


class ChatResponse(BaseModel):
    answer: str
    conversation_id: Optional[UUID] = None


# ============================================================
# DOCUMENT UPLOAD
# ============================================================

class DocumentUploadResponse(BaseModel):
    document: "DocumentResponse"
    ingestion_job: "IngestionJobResponse"
    chunk_count: int = Field(
        ge=0,
        description="Number of chunks created during ingestion",
    )


# ============================================================
# ERRORS
# ============================================================

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None
    field: Optional[str] = None


class APIErrorResponse(BaseModel):
    error: ErrorDetail


# ============================================================
# HEALTH / READINESS
# ============================================================

class HealthResponse(BaseModel):
    status: str
    version: str = __version__


class ReadyResponse(BaseModel):
    status: str
    models_loaded: bool
    vector_store_initialized: bool
    database_connected: bool = True
    documents_indexed: int = Field(
        description="Number of indexed documents/files",
    )
    chunks_indexed: int = Field(
        default=0,
        description="Number of indexed chunks",
    )
    details: Optional[dict] = None


# ============================================================
# DOCUMENT SCHEMAS
# ============================================================

class RenameDocumentRequest(BaseModel):
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-facing document display name",
    )


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    conversation_id: Optional[UUID] = None

    @field_validator("conversation_id", mode="before")
    @classmethod
    def validate_conversation_id(cls, v):
        if v is None:
            return None
        if isinstance(v, (UUID, str)):
            return v
        return None

    filename: str
    original_filename: str
    display_name: str

    file_type: str
    mime_type: str

    file_size: int
    page_count: int
    chunk_count: int

    status: DocumentStatus
    failure_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    pagination: Pagination


# ============================================================
# CONVERSATION SCHEMAS
# ============================================================

class CreateConversationRequest(BaseModel):
    user_id: Optional[UUID] = Field(
        default=None,
        description="Deprecated: Identity is resolved securely from JWT token",
    )
    title: str = Field(
        default="New Chat",
        min_length=1,
        max_length=255,
        description="Conversation title",
    )


class RenameConversationRequest(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Updated conversation title",
    )


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID

    title: str

    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    pagination: Pagination


# ============================================================
# MESSAGE SCHEMAS
# ============================================================

class CreateMessageRequest(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Message content",
    )


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID

    role: MessageRole
    content: str

    created_at: datetime


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    pagination: Pagination


# ============================================================
# INGESTION JOB SCHEMAS
# ============================================================

class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID

    status: IngestionStatus

    error_message: Optional[str] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


# ============================================================
# MEMORY SCHEMAS
# ============================================================

class CreateMemoryRequest(BaseModel):
    user_id: Optional[UUID] = Field(
        default=None,
        description="Deprecated: Identity is resolved securely from JWT token",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Durable memory content to retain",
    )
    memory_type: str = Field(
        default="preference",
        min_length=1,
        max_length=50,
        description="Type classification (e.g. preference, fact, instruction, profile)",
    )


class UpdateMemoryRequest(BaseModel):
    content: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=5000,
        description="Updated durable memory content",
    )
    memory_type: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Updated type classification",
    )


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID

    content: str
    memory_type: str

    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    pagination: Pagination


# ============================================================
# USER & AUTHENTICATION SCHEMAS
# ============================================================

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    name: Optional[str] = Field(None, max_length=100, description="User full name")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    user: UserResponse