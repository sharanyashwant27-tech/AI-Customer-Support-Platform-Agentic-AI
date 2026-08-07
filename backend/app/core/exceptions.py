"""Shared exceptions for the platform."""

from typing import Any


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "app_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401, error_code="auth_error")


class AuthorizationError(AppException):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=403, error_code="forbidden")


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404, error_code="not_found")


class ValidationError(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message, status_code=422, error_code="validation_error", details=details
        )


class AgentError(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message, status_code=500, error_code="agent_error", details=details
        )


class LLMProviderError(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message, status_code=502, error_code="llm_provider_error", details=details
        )


class VectorStoreError(AppException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message, status_code=502, error_code="vector_store_error", details=details
        )
