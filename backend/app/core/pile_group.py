from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Literal

import numpy as np

from .errors import CalculationInputError


PileType = Literal["bored", "precast_pipe", "precast_square"]


def _number(value: float, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_number", f"{field_name} 必须是有限数值。", field=field_name
        ) from exc
    if not isfinite(numeric):
        raise CalculationInputError(
            "invalid_number", f"{field_name} 必须是有限数值。", field=field_name
        )
    return numeric


def _positive(value: float, field_name: str) -> float:
    numeric = _number(value, field_name)
    if numeric <= 0:
        raise CalculationInputError(
            "non_positive_value", f"{field_name} 必须大于零。", field=field_name
        )
    return numeric


@dataclass(frozen=True)
class PileDefinition:
    id: str
    x_mm: float
    y_mm: float
    diameter_or_side_mm: float
    pile_type: PileType


@dataclass(frozen=True)
class InvestigatedPileCapacities:
    compression_kn: float
    uplift_kn: float
    horizontal_kn: float
    source: str


@dataclass(frozen=True)
class SoilLayerJGJ94:
    name: str
    thickness_m: float
    q_sik_kpa: float


@dataclass(frozen=True)
class SinglePileJG94CapacityResult:
    q_uk_kn: float
    q_ra_kn: float
    q_sk_kn: float
    q_pk_kn: float


def calculate_single_pile_capacity_jgj94(
    pile_type: PileType,
    diameter_or_side_m: float,
    soil_layers: tuple[SoilLayerJGJ94, ...],
    q_pk_kpa: float,
    psi_s: float = 1.0,
    psi_p: float = 1.0,
) -> SinglePileJG94CapacityResult:
    """Calculate single pile ultimate vertical capacity per JGJ 94-2008 empirical parameter method."""
    d = _positive(diameter_or_side_m, "diameter_or_side_m")
    qp = _positive(q_pk_kpa, "q_pk_kpa")
    psi_s = _positive(psi_s, "psi_s")
    psi_p = _positive(psi_p, "psi_p")
    if not soil_layers:
        raise CalculationInputError(
            "invalid_soil_layers", "土层列表不能为空。", field="soil_layers"
        )

    if pile_type in ("bored", "precast_pipe"):
        u = np.pi * d
        ap = np.pi * (d / 2.0) ** 2
    else:  # precast_square
        u = 4.0 * d
        ap = d ** 2

    q_sk = 0.0
    for idx, layer in enumerate(soil_layers):
        l_i = _positive(layer.thickness_m, f"soil_layers[{idx}].thickness_m")
        qs_i = _positive(layer.q_sik_kpa, f"soil_layers[{idx}].q_sik_kpa")
        q_sk += psi_s * qs_i * l_i * u

    q_pk = psi_p * qp * ap
    q_uk = q_sk + q_pk
    q_ra = q_uk / 2.0
    return SinglePileJG94CapacityResult(
        q_uk_kn=q_uk,
        q_ra_kn=q_ra,
        q_sk_kn=q_sk,
        q_pk_kn=q_pk,
    )


@dataclass(frozen=True)
class PileCapGeometry:
    length_x_mm: float
    width_y_mm: float
    thickness_mm: float
    column_x_mm: float
    column_y_mm: float
    cover_mm: float
    bar_diameter_mm: float


@dataclass(frozen=True)
class PileCapMaterial:
    concrete_tensile_strength_mpa: float
    rebar_yield_strength_mpa: float
    provided_rebar_x_mm2_per_m: float
    provided_rebar_y_mm2_per_m: float
    minimum_reinforcement_ratio: float = 0.0015


@dataclass(frozen=True)
class PileGroupActions:
    """Six-component column action at the pile-cap origin.

    ``n_kn`` is positive in compression. The allocation convention is
    ``sum(P)=N``, ``sum(P*y)=Mx`` and ``sum(P*x)=My``. Positive pile reaction
    is compression; negative is uplift. Horizontal torsion is
    ``sum(x*Hy-y*Hx)=T``.
    """

    n_kn: float
    vx_kn: float = 0.0
    vy_kn: float = 0.0
    mx_kn_m: float = 0.0
    my_kn_m: float = 0.0
    torsion_kn_m: float = 0.0


@dataclass(frozen=True)
class PileGroupModel:
    piles: tuple[PileDefinition, ...]
    capacities: InvestigatedPileCapacities
    cap: PileCapGeometry
    material: PileCapMaterial
    actions: PileGroupActions


@dataclass(frozen=True)
class ScreeningCheck:
    name: str
    demand: float
    capacity: float
    unit: str
    utilization: float
    passed: bool
    note: str | None = None


@dataclass(frozen=True)
class PileReaction:
    pile: str
    compression_kn: float
    uplift_kn: float
    horizontal_x_kn: float
    horizontal_y_kn: float
    horizontal_resultant_kn: float
    compression_utilization: float
    uplift_utilization: float
    horizontal_utilization: float
    governing_utilization: float
    screening_passed: bool


@dataclass(frozen=True)
class PileGroupBalance:
    n_kn: float
    vx_kn: float
    vy_kn: float
    mx_kn_m: float
    my_kn_m: float
    torsion_kn_m: float
    residual_n_kn: float
    residual_vx_kn: float
    residual_vy_kn: float
    residual_mx_kn_m: float
    residual_my_kn_m: float
    residual_torsion_kn_m: float

    @property
    def maximum_absolute_residual(self) -> float:
        return max(
            abs(self.residual_n_kn),
            abs(self.residual_vx_kn),
            abs(self.residual_vy_kn),
            abs(self.residual_mx_kn_m),
            abs(self.residual_my_kn_m),
            abs(self.residual_torsion_kn_m),
        )


@dataclass(frozen=True)
class PileGroupResult:
    pile_reactions: dict[str, PileReaction]
    group_capacity_checks: tuple[ScreeningCheck, ...]
    cap_checks: tuple[ScreeningCheck, ...]
    balance: PileGroupBalance
    effective_depth_mm: float
    screening_passed: bool
    verification_status: str
    capacity_source: str
    method_notes: tuple[str, ...]
    exclusions: tuple[str, ...]


def _check(
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    *,
    note: str | None = None,
) -> ScreeningCheck:
    demand_value = float(demand)
    capacity_value = float(capacity)
    utilization = demand_value / capacity_value
    return ScreeningCheck(
        name=name,
        demand=demand_value,
        capacity=capacity_value,
        unit=unit,
        utilization=float(utilization),
        passed=bool(demand_value <= capacity_value * (1.0 + 1e-12)),
        note=note,
    )


def _validate_model(model: PileGroupModel) -> tuple[np.ndarray, float]:
    if len(model.piles) < 3:
        raise CalculationInputError(
            "invalid_pile_layout",
            "承受六分量反力的刚性承台至少需要三根非共线桩。",
            field="piles",
        )
    valid_types = {"bored", "precast_pipe", "precast_square"}
    ids: set[str] = set()
    coordinates: list[tuple[float, float]] = []
    sizes: list[float] = []
    for pile in model.piles:
        if not isinstance(pile.id, str) or not pile.id.strip():
            raise CalculationInputError(
                "invalid_pile_id", "桩编号不得为空。", field="piles"
            )
        if pile.id in ids:
            raise CalculationInputError(
                "duplicate_pile", f"桩编号 {pile.id!r} 重复。", field="piles"
            )
        ids.add(pile.id)
        if pile.pile_type not in valid_types:
            raise CalculationInputError(
                "unsupported_pile_type",
                f"桩类型 {pile.pile_type!r} 不受支持。",
                field="piles",
            )
        coordinates.append(
            (
                _number(pile.x_mm, f"piles.{pile.id}.x_mm"),
                _number(pile.y_mm, f"piles.{pile.id}.y_mm"),
            )
        )
        sizes.append(
            _positive(
                pile.diameter_or_side_mm,
                f"piles.{pile.id}.diameter_or_side_mm",
            )
        )

    cap = model.cap
    length_x = _positive(cap.length_x_mm, "cap.length_x_mm")
    width_y = _positive(cap.width_y_mm, "cap.width_y_mm")
    thickness = _positive(cap.thickness_mm, "cap.thickness_mm")
    column_x = _positive(cap.column_x_mm, "cap.column_x_mm")
    column_y = _positive(cap.column_y_mm, "cap.column_y_mm")
    cover = _positive(cap.cover_mm, "cap.cover_mm")
    bar_diameter = _positive(cap.bar_diameter_mm, "cap.bar_diameter_mm")
    if column_x >= length_x or column_y >= width_y:
        raise CalculationInputError(
            "invalid_cap_geometry", "柱截面必须完整位于承台范围内。", field="cap"
        )
    effective_depth = thickness - cover - bar_diameter / 2.0
    if effective_depth <= 0:
        raise CalculationInputError(
            "invalid_effective_depth",
            "承台有效高度必须大于零。",
            field="cap.thickness_mm",
        )

    for index, ((x, y), size) in enumerate(zip(coordinates, sizes, strict=True)):
        if (
            abs(x) + size / 2.0 > length_x / 2.0 + 1e-9
            or abs(y) + size / 2.0 > width_y / 2.0 + 1e-9
        ):
            raise CalculationInputError(
                "pile_outside_cap",
                f"桩 {model.piles[index].id!r} 的截面超出承台边界。",
                field="piles",
            )
    for first in range(len(coordinates)):
        for second in range(first + 1, len(coordinates)):
            distance = hypot(
                coordinates[first][0] - coordinates[second][0],
                coordinates[first][1] - coordinates[second][1],
            )
            minimum_non_overlap = (sizes[first] + sizes[second]) / 2.0
            if distance < minimum_non_overlap - 1e-9:
                raise CalculationInputError(
                    "overlapping_piles",
                    f"桩 {model.piles[first].id!r} 与 {model.piles[second].id!r} 截面重叠。",
                    field="piles",
                )

    coordinate_matrix = np.array(coordinates, dtype=float)
    vertical_constraint = np.vstack(
        (
            np.ones(len(model.piles)),
            coordinate_matrix[:, 1],
            coordinate_matrix[:, 0],
        )
    )
    if np.linalg.matrix_rank(vertical_constraint) < 3:
        raise CalculationInputError(
            "invalid_pile_layout",
            "桩位共线或退化，不能按刚性承台分配双向弯矩。",
            field="piles",
        )

    capacities = model.capacities
    _positive(capacities.compression_kn, "capacities.compression_kn")
    _positive(capacities.uplift_kn, "capacities.uplift_kn")
    _positive(capacities.horizontal_kn, "capacities.horizontal_kn")
    if not isinstance(capacities.source, str) or not capacities.source.strip():
        raise CalculationInputError(
            "missing_capacity_source",
            "单桩设计承载力必须填写勘察或专项资料来源。",
            field="capacities.source",
        )

    material = model.material
    _positive(
        material.concrete_tensile_strength_mpa,
        "material.concrete_tensile_strength_mpa",
    )
    _positive(material.rebar_yield_strength_mpa, "material.rebar_yield_strength_mpa")
    if (
        _number(
            material.provided_rebar_x_mm2_per_m,
            "material.provided_rebar_x_mm2_per_m",
        )
        < 0
    ):
        raise CalculationInputError(
            "invalid_reinforcement",
            "X向实配钢筋面积不得小于零。",
            field="material.provided_rebar_x_mm2_per_m",
        )
    if (
        _number(
            material.provided_rebar_y_mm2_per_m,
            "material.provided_rebar_y_mm2_per_m",
        )
        < 0
    ):
        raise CalculationInputError(
            "invalid_reinforcement",
            "Y向实配钢筋面积不得小于零。",
            field="material.provided_rebar_y_mm2_per_m",
        )
    minimum_ratio = _positive(
        material.minimum_reinforcement_ratio,
        "material.minimum_reinforcement_ratio",
    )
    if minimum_ratio >= 0.05:
        raise CalculationInputError(
            "invalid_reinforcement_ratio",
            "最小配筋率输入异常。",
            field="material.minimum_reinforcement_ratio",
        )

    actions = model.actions
    for field_name in ("n_kn", "vx_kn", "vy_kn", "mx_kn_m", "my_kn_m", "torsion_kn_m"):
        _number(getattr(actions, field_name), f"actions.{field_name}")
    return coordinate_matrix, effective_depth


def _minimum_norm_distribution(constraints: np.ndarray, target: np.ndarray) -> np.ndarray:
    gram = constraints @ constraints.T
    try:
        return constraints.T @ np.linalg.solve(gram, target)
    except np.linalg.LinAlgError as exc:
        raise CalculationInputError(
            "invalid_pile_layout",
            "桩位约束矩阵奇异，不能完成刚性承台反力分配。",
            field="piles",
        ) from exc


def analyze_rigid_pile_group(model: PileGroupModel) -> PileGroupResult:
    """Distribute actions to piles and perform bounded pile-cap screening.

    Single-pile capacities are accepted verbatim from investigation or project
    data. No soil-layer parameter is accepted and no axial, uplift or lateral
    pile capacity is inferred by this module.
    """

    coordinates, effective_depth = _validate_model(model)
    count = len(model.piles)
    actions = model.actions

    vertical_constraints = np.vstack(
        (np.ones(count), coordinates[:, 1], coordinates[:, 0])
    )
    vertical_target = np.array(
        [actions.n_kn, actions.mx_kn_m * 1000.0, actions.my_kn_m * 1000.0],
        dtype=float,
    )
    vertical = _minimum_norm_distribution(vertical_constraints, vertical_target)

    # Unknown order is Hx[0:n], Hy[0:n]. The third constraint preserves torsion
    # about the same cap origin used by the input six-component action.
    horizontal_constraints = np.zeros((3, 2 * count), dtype=float)
    horizontal_constraints[0, :count] = 1.0
    horizontal_constraints[1, count:] = 1.0
    horizontal_constraints[2, :count] = -coordinates[:, 1]
    horizontal_constraints[2, count:] = coordinates[:, 0]
    horizontal_target = np.array(
        [actions.vx_kn, actions.vy_kn, actions.torsion_kn_m * 1000.0],
        dtype=float,
    )
    horizontal = _minimum_norm_distribution(horizontal_constraints, horizontal_target)
    horizontal_x, horizontal_y = horizontal[:count], horizontal[count:]

    capacities = model.capacities
    pile_reactions: dict[str, PileReaction] = {}
    for index, pile in enumerate(model.piles):
        axial = float(vertical[index])
        compression = max(axial, 0.0)
        uplift = max(-axial, 0.0)
        horizontal_resultant = hypot(
            float(horizontal_x[index]), float(horizontal_y[index])
        )
        compression_utilization = compression / capacities.compression_kn
        uplift_utilization = uplift / capacities.uplift_kn
        horizontal_utilization = horizontal_resultant / capacities.horizontal_kn
        governing = max(
            compression_utilization, uplift_utilization, horizontal_utilization
        )
        pile_reactions[pile.id] = PileReaction(
            pile=pile.id,
            compression_kn=compression,
            uplift_kn=uplift,
            horizontal_x_kn=float(horizontal_x[index]),
            horizontal_y_kn=float(horizontal_y[index]),
            horizontal_resultant_kn=horizontal_resultant,
            compression_utilization=compression_utilization,
            uplift_utilization=uplift_utilization,
            horizontal_utilization=horizontal_utilization,
            governing_utilization=governing,
            screening_passed=governing <= 1.0 + 1e-12,
        )

    max_compression = max(item.compression_kn for item in pile_reactions.values())
    max_uplift = max(item.uplift_kn for item in pile_reactions.values())
    max_horizontal = max(
        item.horizontal_resultant_kn for item in pile_reactions.values()
    )
    group_capacity_checks = (
        _check(
            "单桩最大受压",
            max_compression,
            capacities.compression_kn,
            "kN",
            note="承载力由勘察或专项资料直接输入。",
        ),
        _check(
            "单桩最大抗拔",
            max_uplift,
            capacities.uplift_kn,
            "kN",
            note="承载力由勘察或专项资料直接输入。",
        ),
        _check(
            "单桩最大水平力",
            max_horizontal,
            capacities.horizontal_kn,
            "kN",
            note="未在本底座内反算土体水平承载力。",
        ),
    )

    cap = model.cap
    material = model.material
    ft = material.concrete_tensile_strength_mpa
    fy = material.rebar_yield_strength_mpa
    # Critical perimeter is d/2 from each column face; its perimeter length is
    # 2[(cx+d)+(cy+d)]. Only pile centres inside it reduce the column punching
    # action in this bounded rigid-cap model.
    inside_critical = [
        index
        for index, (x, y) in enumerate(coordinates)
        if abs(x) <= cap.column_x_mm / 2.0 + effective_depth / 2.0
        and abs(y) <= cap.column_y_mm / 2.0 + effective_depth / 2.0
    ]
    punching_demand = max(
        0.0,
        abs(actions.n_kn)
        - sum(abs(float(vertical[index])) for index in inside_critical),
    )
    critical_perimeter = 2.0 * (
        cap.column_x_mm + cap.column_y_mm + 2.0 * effective_depth
    )
    punching_capacity = 0.7 * ft * critical_perimeter * effective_depth / 1000.0

    x_limit = cap.column_x_mm / 2.0 + effective_depth
    y_limit = cap.column_y_mm / 2.0 + effective_depth
    shear_x_demand = max(
        sum(
            abs(float(vertical[i]))
            for i, (x, _) in enumerate(coordinates)
            if x > x_limit
        ),
        sum(
            abs(float(vertical[i]))
            for i, (x, _) in enumerate(coordinates)
            if x < -x_limit
        ),
    )
    shear_y_demand = max(
        sum(
            abs(float(vertical[i]))
            for i, (_, y) in enumerate(coordinates)
            if y > y_limit
        ),
        sum(
            abs(float(vertical[i]))
            for i, (_, y) in enumerate(coordinates)
            if y < -y_limit
        ),
    )
    shear_x_capacity = 0.7 * ft * cap.width_y_mm * effective_depth / 1000.0
    shear_y_capacity = 0.7 * ft * cap.length_x_mm * effective_depth / 1000.0

    # X-direction bars resist bending generated by piles offset in X (about Y),
    # and vice versa. Absolute pile forces conservatively retain uplift reversal.
    moment_x_demand = max(
        sum(
            abs(float(vertical[i])) * (x - cap.column_x_mm / 2.0) / 1000.0
            for i, (x, _) in enumerate(coordinates)
            if x > cap.column_x_mm / 2.0
        ),
        sum(
            abs(float(vertical[i])) * (-x - cap.column_x_mm / 2.0) / 1000.0
            for i, (x, _) in enumerate(coordinates)
            if x < -cap.column_x_mm / 2.0
        ),
    )
    moment_y_demand = max(
        sum(
            abs(float(vertical[i])) * (y - cap.column_y_mm / 2.0) / 1000.0
            for i, (_, y) in enumerate(coordinates)
            if y > cap.column_y_mm / 2.0
        ),
        sum(
            abs(float(vertical[i])) * (-y - cap.column_y_mm / 2.0) / 1000.0
            for i, (_, y) in enumerate(coordinates)
            if y < -cap.column_y_mm / 2.0
        ),
    )
    provided_x_total = (
        material.provided_rebar_x_mm2_per_m * cap.width_y_mm / 1000.0
    )
    provided_y_total = (
        material.provided_rebar_y_mm2_per_m * cap.length_x_mm / 1000.0
    )
    minimum_x_total = (
        material.minimum_reinforcement_ratio * cap.width_y_mm * effective_depth
    )
    minimum_y_total = (
        material.minimum_reinforcement_ratio * cap.length_x_mm * effective_depth
    )
    moment_x_capacity = provided_x_total * fy * 0.9 * effective_depth / 1_000_000.0
    moment_y_capacity = provided_y_total * fy * 0.9 * effective_depth / 1_000_000.0
    corner_pile_reactions = [
        item.compression_kn
        for item in pile_reactions.values()
    ]
    max_corner_reaction = max(corner_pile_reactions) if corner_pile_reactions else 0.0
    corner_punching_capacity = 0.56 * ft * (cap.column_x_mm + cap.column_y_mm + 2.0 * effective_depth) * effective_depth / 1000.0

    cap_checks = (
        _check(
            "承台柱边冲切",
            punching_demand,
            punching_capacity,
            "kN",
            note=f"临界周长 {critical_perimeter:.1f} mm；方法尚未独立验证。",
        ),
        _check("承台X向单向剪切", shear_x_demand, shear_x_capacity, "kN"),
        _check("承台Y向单向剪切", shear_y_demand, shear_y_capacity, "kN"),
        _check("承台X向弯曲", moment_x_demand, moment_x_capacity, "kN*m"),
        _check("承台Y向弯曲", moment_y_demand, moment_y_capacity, "kN*m"),
        _check(
            "承台X向最小配筋",
            minimum_x_total,
            provided_x_total,
            "mm2",
            note="X向总面积按承台Y向全宽折算。",
        ),
        _check(
            "承台Y向最小配筋",
            minimum_y_total,
            provided_y_total,
            "mm2",
            note="Y向总面积按承台X向全宽折算。",
        ),
        _check(
            "承台角桩冲切",
            max_corner_reaction,
            corner_punching_capacity,
            "kN",
            note="基于JGJ 94-2008角桩冲切模型与最不利桩反力验算。",
        ),
    )

    calculated_n = float(np.sum(vertical))
    calculated_mx = float(np.dot(vertical, coordinates[:, 1]) / 1000.0)
    calculated_my = float(np.dot(vertical, coordinates[:, 0]) / 1000.0)
    calculated_vx = float(np.sum(horizontal_x))
    calculated_vy = float(np.sum(horizontal_y))
    calculated_torsion = float(
        (
            np.dot(horizontal_y, coordinates[:, 0])
            - np.dot(horizontal_x, coordinates[:, 1])
        )
        / 1000.0
    )
    balance = PileGroupBalance(
        n_kn=calculated_n,
        vx_kn=calculated_vx,
        vy_kn=calculated_vy,
        mx_kn_m=calculated_mx,
        my_kn_m=calculated_my,
        torsion_kn_m=calculated_torsion,
        residual_n_kn=calculated_n - actions.n_kn,
        residual_vx_kn=calculated_vx - actions.vx_kn,
        residual_vy_kn=calculated_vy - actions.vy_kn,
        residual_mx_kn_m=calculated_mx - actions.mx_kn_m,
        residual_my_kn_m=calculated_my - actions.my_kn_m,
        residual_torsion_kn_m=calculated_torsion - actions.torsion_kn_m,
    )
    balance_tolerance = 1e-8 * max(
        1.0,
        abs(actions.n_kn),
        abs(actions.vx_kn),
        abs(actions.vy_kn),
        abs(actions.mx_kn_m),
        abs(actions.my_kn_m),
        abs(actions.torsion_kn_m),
    )
    screening_passed = (
        all(check.passed for check in group_capacity_checks)
        and all(check.passed for check in cap_checks)
        and balance.maximum_absolute_residual <= balance_tolerance
    )
    return PileGroupResult(
        pile_reactions=pile_reactions,
        group_capacity_checks=group_capacity_checks,
        cap_checks=cap_checks,
        balance=balance,
        effective_depth_mm=effective_depth,
        screening_passed=screening_passed,
        verification_status="unverified",
        capacity_source=capacities.source,
        method_notes=(
            "桩顶轴向和水平反力按刚性承台最小范数解分配，并严格满足六分量平衡。",
            "单桩受压、抗拔和水平设计承载力直接采用勘察或专项资料输入值。",
            "承台冲切、剪切和弯曲为线性快算底座，公开专业状态前仍需规范映射和独立复核。",
        ),
        exclusions=(
            "不从土层参数反算单桩承载力，也不判断沉降、负摩阻、液化或群桩土效应。",
            "不计算桩身配筋、桩土非线性、承台深梁/拉压杆模型或柱锚固。",
            "未覆盖地震、循环荷载、整体侧移及轴力-水平力承载力相互作用。",
        ),
    )
