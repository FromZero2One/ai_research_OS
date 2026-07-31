"""Application exceptions — typed, not generic."""

from __future__ import annotations


class AIResearchOSError(Exception):
    """Base exception for all application errors."""


class DomainError(AIResearchOSError):
    """Base exception for business/domain rule violations.

    Subclass this per domain (e.g. ``MarketDataError``) and raise typed
    errors from services. Handlers map domain errors to HTTP responses.
    """

    http_status: int = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class DataSourceError(DomainError):
    """An upstream data source could not be reached or returned bad data.

    http_status: 502 (bad gateway — the source, not the app, is broken).
    """

    http_status: int = 502

    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        super().__init__(f"{source} data source error: {detail}")


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

    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(detail)


class AuthorizationError(AIResearchOSError):
    """Insufficient permissions."""

    def __init__(self, detail: str = "Insufficient permissions") -> None:
        super().__init__(detail)


class DuplicateError(AIResearchOSError):
    """Resource already exists."""

    def __init__(self, resource: str, key: str) -> None:
        super().__init__(f"{resource} already exists: {key}")
