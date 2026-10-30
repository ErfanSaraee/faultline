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


class UnsupportedAdapterError(FaultlineError):
    """Raised when an agent adapter type is not registered or supported."""

    def __init__(self, adapter_type: str) -> None:
        super().__init__(
            f"Agent adapter type '{adapter_type}' is not registered.")
        self.adapter_type = adapter_type
