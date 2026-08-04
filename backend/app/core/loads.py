from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from .errors import CalculationInputError
from .schemas import (
    LoadCombinationResult,
    LoadDirection,
    LoadItem,
    LoadKind,
    Quantity,
)


FACTOR_SETS: tuple[tuple[str, str, dict[str, float]], ...] = (
    (
        "ULS-活荷载控制",
        "ULS",
        {"self_weight": 1.3, "dead": 1.3, "live": 1.5, "wind": 0.9, "snow": 1.05},
    ),
    (
        "ULS-风荷载控制",
        "ULS",
        {"self_weight": 1.3, "dead": 1.3, "live": 1.05, "wind": 1.5, "snow": 1.05},
    ),
    (
        "ULS-雪荷载控制",
        "ULS",
        {"self_weight": 1.3, "dead": 1.3, "live": 1.05, "wind": 0.9, "snow": 1.5},
    ),
    (
        "ULS-上拔控制",
        "ULS",
        {"self_weight": 0.9, "dead": 0.9, "live": 0.0, "wind": 1.5, "snow": 0.0},
    ),
    (
        "SLS-标准组合",
        "SLS",
        {"self_weight": 1.0, "dead": 1.0, "live": 1.0, "wind": 1.0, "snow": 1.0},
    ),
)


@dataclass(frozen=True)
class LoadEnvelope:
    totals: dict[str, float]
    combinations: list[LoadCombinationResult]

    @property
    def governing_uls(self) -> LoadCombinationResult:
        return max(
            (item for item in self.combinations if item.limit_state == "ULS"),
            key=lambda item: abs(item.total.value),
        )

    @property
    def governing_sls(self) -> LoadCombinationResult:
        return max(
            (item for item in self.combinations if item.limit_state == "SLS"),
            key=lambda item: abs(item.total.value),
        )

    @property
    def maximum_uls(self) -> LoadCombinationResult:
        return max(
            (item for item in self.combinations if item.limit_state == "ULS"),
            key=lambda item: item.total.value,
        )

    @property
    def minimum_uls(self) -> LoadCombinationResult:
        return min(
            (item for item in self.combinations if item.limit_state == "ULS"),
            key=lambda item: item.total.value,
        )

    @property
    def maximum_sls(self) -> LoadCombinationResult:
        return max(
            (item for item in self.combinations if item.limit_state == "SLS"),
            key=lambda item: item.total.value,
        )

    @property
    def minimum_sls(self) -> LoadCombinationResult:
        return min(
            (item for item in self.combinations if item.limit_state == "SLS"),
            key=lambda item: item.total.value,
        )


def direction_sign(direction: LoadDirection) -> float:
    """Return the algebraic sign used by one-dimensional member envelopes.

    Gravity and positive axes are positive; uplift and negative axes are
    negative.  The original direction remains available on every combination,
    so callers that resolve forces in two dimensions do not have to infer it
    from the sign alone.
    """

    return -1.0 if direction in {
        LoadDirection.UPLIFT,
        LoadDirection.X_NEGATIVE,
        LoadDirection.Y_NEGATIVE,
    } else 1.0


def _build_combinations(
    grouped: dict[str, dict[LoadDirection, float]], unit: str
) -> list[LoadCombinationResult]:
    kinds = [kind.value for kind in LoadKind]
    choices: list[list[tuple[LoadDirection | None, float]]] = []
    for kind in kinds:
        values = grouped.get(kind, {})
        choices.append(list(values.items()) or [(None, 0.0)])
    branch_count = 1
    for choice in choices:
        branch_count *= len(choice)

    combinations: list[LoadCombinationResult] = []
    for selected in product(*choices):
        selected_by_kind = dict(zip(kinds, selected, strict=True))
        suffix_parts = [
            f"{kind}:{direction.value}"
            for kind, (direction, _) in selected_by_kind.items()
            if direction is not None and len(grouped.get(kind, {})) > 1
        ]
        for name, limit_state, factors in FACTOR_SETS:
            by_kind: dict[str, Quantity] = {}
            directions: dict[str, list[LoadDirection]] = {}
            for kind, (direction, magnitude) in selected_by_kind.items():
                signed = (
                    direction_sign(direction) * magnitude
                    if direction is not None
                    else 0.0
                )
                by_kind[kind] = Quantity(
                    value=signed * factors[kind], unit=unit
                )
                if direction is not None:
                    directions[kind] = [direction]
            combination_name = name
            if branch_count > 1 and suffix_parts:
                combination_name += "（" + ",".join(suffix_parts) + "）"
            combinations.append(
                LoadCombinationResult(
                    name=combination_name,
                    limit_state=limit_state,  # type: ignore[arg-type]
                    factors=factors,
                    factored_by_kind=by_kind,
                    directions_by_kind=directions,
                    total=Quantity(
                        value=sum(quantity.value for quantity in by_kind.values()),
                        unit=unit,
                    ),
                )
            )
    return combinations


def line_load_envelope(
    loads: list[LoadItem],
    *,
    tributary_width_m: float = 1.0,
    automatic_self_weight_kn_m: float = 0.0,
) -> LoadEnvelope:
    if tributary_width_m <= 0:
        raise CalculationInputError(
            "invalid_tributary_width",
            "tributary_width_m 必须大于 0",
            field="tributary_width_m",
        )
    grouped: dict[str, dict[LoadDirection, float]] = {
        kind.value: {} for kind in LoadKind
    }
    if automatic_self_weight_kn_m:
        grouped[LoadKind.SELF_WEIGHT.value][
            LoadDirection.GRAVITY
        ] = automatic_self_weight_kn_m
    for item in loads:
        if item.unit == "kN/m":
            line_value = item.value
        elif item.unit == "kN/m2":
            line_value = item.value * tributary_width_m
        else:
            raise CalculationInputError(
                "unsupported_load_unit",
                "梁、板和刚架的均布荷载只接受 kN/m 或 kN/m2",
                field="loads",
                details={"unit": item.unit},
            )
        values = grouped[item.kind.value]
        values[item.direction] = values.get(item.direction, 0.0) + line_value

    totals = {
        kind: sum(direction_sign(direction) * value for direction, value in values.items())
        for kind, values in grouped.items()
    }
    combinations = _build_combinations(grouped, "kN/m")
    return LoadEnvelope(totals=totals, combinations=combinations)


def axial_load_envelope(loads: list[LoadItem]) -> LoadEnvelope:
    grouped: dict[str, dict[LoadDirection, float]] = {
        kind.value: {} for kind in LoadKind
    }
    for item in loads:
        if item.unit != "kN":
            raise CalculationInputError(
                "unsupported_load_unit",
                "柱轴力荷载只接受 kN",
                field="loads",
                details={"unit": item.unit},
            )
        values = grouped[item.kind.value]
        values[item.direction] = values.get(item.direction, 0.0) + item.value

    totals = {
        kind: sum(direction_sign(direction) * value for direction, value in values.items())
        for kind, values in grouped.items()
    }
    combinations = _build_combinations(grouped, "kN")
    return LoadEnvelope(totals=totals, combinations=combinations)
