from __future__ import annotations

from typing import Any


class CalculationInputError(ValueError):
    """A user-correctable calculation input error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}

    def __reduce__(self):
        # Keyword-only fields must survive pickling across worker processes.
        return (
            _rebuild_input_error,
            (type(self), self.code, self.message, self.field, self.details),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "details": self.details,
        }


def _rebuild_input_error(
    cls: type[CalculationInputError],
    code: str,
    message: str,
    field: str | None,
    details: dict[str, Any],
) -> CalculationInputError:
    return cls(code, message, field=field, details=details)
