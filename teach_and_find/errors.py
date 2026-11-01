"""Project-owned errors shared by domain rules and infrastructure adapters."""


class AssistantError(ValueError):
    """Stable error code for operator-facing adapters."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
