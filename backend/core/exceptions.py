"""Application exceptions — typed, not generic."""

from __future__ import annotations


class AIResearchOSError(Exception):
    """Base exception for all application errors."""


class NotFoundError(AIResearchOSError):
    """Resource not found."""

    def __init__(self, resource: str, id: str) -> None:
        self.resource = resource
        self.id = id
        super().__init__(f"{resource} not found: {id}")


class ValidationError(AIResearchOSError):
    """Input validation failed."""


class ConfigurationError(AIResearchOSError):
    """System configuration is invalid."""


class ExternalServiceError(AIResearchOSError):
    """An external service (LLM, market data, vector store) returned an error."""

    def __init__(self, service: str, detail: str) -> None:
        self.service = service
        super().__init__(f"{service} error: {detail}")


class DocumentParsingError(AIResearchOSError):
    """Failed to parse a document."""


class AuthenticationError(AIResearchOSError):
    """Authentication failed."""


class AuthorizationError(AIResearchOSError):
    """Insufficient permissions."""


class DuplicateError(AIResearchOSError):
    """Resource already exists."""
