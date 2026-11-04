"""Expected tool failures that can be returned safely to the model."""

from __future__ import annotations

from typing import Any


class ToolError(Exception):
    """Carry a stable error code, a readable explanation and a recovery hint."""

    def __init__(
        self, code: str, message: str, hint: str, *, data: dict[str, Any] | None = None
    ) -> None:
        """Initialize a recoverable tool failure.

        Args:
            code: Machine-readable error classification.
            message: Explanation of the failed operation.
            hint: Suggested correction for the next tool call.
            data: Optional bounded diagnostic data, such as process output.
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.data = data


class ToolRegistrationError(ValueError):
    """Reject an invalid toolset or a duplicate name during assembly."""
