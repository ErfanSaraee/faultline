"""Domain-level exception hierarchy for FAULTLINE."""


class FaultlineError(Exception):
    """Base exception for all domain and application errors in FAULTLINE."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EntityNotFoundError(FaultlineError):
    """Raised when a requested domain entity does not exist."""

    def __init__(self, entity_type: str, identifier: str) -> None:
        super().__init__(f"{entity_type} '{identifier}' was not found.")
        self.entity_type = entity_type
        self.identifier = identifier


class EntityConflictError(FaultlineError):
    """Raised when creating or updating an entity violates uniqueness invariants."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
