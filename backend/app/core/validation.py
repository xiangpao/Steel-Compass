from __future__ import annotations

from typing import Any

from .errors import CalculationInputError


def number(
    inputs: dict[str, Any],
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    default: float | None = None,
) -> float:
    raw = inputs.get(name, default)
    if raw is None:
        raise CalculationInputError(
            "missing_input", f"缺少必填参数：{name}", field=name
        )
    if isinstance(raw, bool):
        raise CalculationInputError(
            "invalid_number", f"{name} 必须是数值", field=name
        )
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_number", f"{name} 必须是数值", field=name
        ) from exc
    if minimum is not None and value < minimum:
        raise CalculationInputError(
            "below_minimum",
            f"{name} 不得小于 {minimum}",
            field=name,
            details={"minimum": minimum},
        )
    if maximum is not None and value > maximum:
        raise CalculationInputError(
            "above_maximum",
            f"{name} 不得大于 {maximum}",
            field=name,
            details={"maximum": maximum},
        )
    return value


def text(
    inputs: dict[str, Any],
    name: str,
    *,
    allowed: set[str] | None = None,
    default: str | None = None,
) -> str:
    raw = inputs.get(name, default)
    if raw is None or not str(raw).strip():
        raise CalculationInputError(
            "missing_input", f"缺少必填参数：{name}", field=name
        )
    value = str(raw).strip()
    if allowed is not None and value not in allowed:
        raise CalculationInputError(
            "unsupported_value",
            f"{name} 的值不受支持：{value}",
            field=name,
            details={"allowed": sorted(allowed)},
        )
    return value


def boolean(
    inputs: dict[str, Any], name: str, *, default: bool | None = None
) -> bool:
    raw = inputs.get(name, default)
    if raw is None:
        raise CalculationInputError(
            "missing_input", f"缺少必填参数：{name}", field=name
        )
    if not isinstance(raw, bool):
        raise CalculationInputError(
            "invalid_boolean", f"{name} 必须是布尔值", field=name
        )
    return raw
