class ServiceException(Exception):
    """Base exception for service layer."""
    def __init__(self, message: str, code: str = "SERVICE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(ServiceException):
    """Entity not found."""
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(message, code=code)


class DocumentNotFound(NotFound):
    def __init__(self, message: str = "Document not found"):
        super().__init__(message, code="DOCUMENT_NOT_FOUND")


class ConversationNotFound(NotFound):
    def __init__(self, message: str = "Conversation not found"):
        super().__init__(message, code="CONVERSATION_NOT_FOUND")


class UserNotFound(NotFound):
    def __init__(self, message: str = "User not found"):
        super().__init__(message, code="USER_NOT_FOUND")


class MemoryNotFound(NotFound):
    def __init__(self, message: str = "Memory not found"):
        super().__init__(message, code="MEMORY_NOT_FOUND")


class ValidationError(ServiceException):
    """Business validation error."""
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code=code)


class Conflict(ServiceException):
    """Resource conflict (e.g. duplicate name)."""
    def __init__(self, message: str = "Resource conflict", code: str = "CONFLICT"):
        super().__init__(message, code=code)


class IngestionError(ServiceException):
    """Document ingestion or processing error."""
    def __init__(self, message: str, code: str = "INGESTION_ERROR"):
        super().__init__(message, code=code)
