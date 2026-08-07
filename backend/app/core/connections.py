from __future__ import annotations

from math import hypot, isfinite, pi, sqrt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .errors import CalculationInputError
from .schemas import Quantity


class ConnectionEffect(BaseModel):
    """One already-combined six-component action effect.

    ``N`` is positive in compression and negative in uplift.  Forces are kN
    and moments are kN.m.  The connection functions never apply load factors.
    """

    combination_id: str
    combination_name: str
    limit_state: Literal["ULS", "SLS"]
    n_kn: float = 0.0
    vx_kn: float = 0.0
    vy_kn: float = 0.0
    mx_kn_m: float = 0.0
    my_kn_m: float = 0.0
    torsion_kn_m: float = 0.0

    @model_validator(mode="after")
    def finite_components(self) -> "ConnectionEffect":
        values = (
            self.n_kn,
            self.vx_kn,
            self.vy_kn,
            self.mx_kn_m,
            self.my_kn_m,
            self.torsion_kn_m,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("连接作用效应必须是有限数值")
        return self


class FastenerPosition(BaseModel):
    x_mm: float
    y_mm: float

    @model_validator(mode="after")
    def finite_coordinates(self) -> "FastenerPosition":
        if not isfinite(self.x_mm) or not isfinite(self.y_mm):
            raise ValueError("连接件坐标必须是有限数值")
        return self


class DemandCapacityCheck(BaseModel):
    key: str
    name: str
    combination_id: str | None
    combination_name: str | None
    demand: Quantity
    capacity: Quantity
    utilization: float = Field(ge=0)
    passed: bool
    reference: str
    note: str | None = None
    governing_fastener: int | None = None


class ConnectionResult(BaseModel):
    status: Literal["passed", "failed", "capability_unavailable"]
    verification_status: Literal["unverified"] = "unverified"
    effects: list[ConnectionEffect]
    checks: list[DemandCapacityCheck]
    governing_check: str | None
    assumptions: list[str]
    applicability: list[str]
    capacity_sources: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


class TimberPostBaseInput(BaseModel):
    post_width_mm: float = Field(gt=0)
    post_depth_mm: float = Field(gt=0)
    plate_width_mm: float = Field(gt=0)
    plate_depth_mm: float = Field(gt=0)
    fastener_diameter_mm: float = Field(gt=0)
    fastener_positions: list[FastenerPosition] = Field(min_length=2)
    connector_standoff_mm: float = Field(default=0.0, ge=0)

    # A project-assessed design capacity may be supplied directly.  If it is
    # absent, the corresponding material parameters below are used.
    bearing_design_capacity_kn: float | None = Field(default=None, gt=0)
    fastener_tension_design_capacity_kn: float | None = Field(default=None, gt=0)
    fastener_shear_design_capacity_kn: float | None = Field(default=None, gt=0)
    connector_bending_design_capacity_kn_m: float | None = Field(
        default=None, gt=0
    )

    timber_compression_design_mpa: float | None = Field(default=None, gt=0)
    timber_withdrawal_design_mpa: float | None = Field(default=None, gt=0)
    timber_shear_design_mpa: float | None = Field(default=None, gt=0)
    embedment_length_mm: float | None = Field(default=None, gt=0)
    fastener_fu_mpa: float | None = Field(default=None, gt=0)
    connector_bending_strength_mpa: float | None = Field(default=None, gt=0)
    connector_section_modulus_mm3: float | None = Field(default=None, gt=0)

    minimum_spacing_mm: float | None = Field(default=None, gt=0)
    minimum_edge_distance_mm: float | None = Field(default=None, gt=0)


class WallAnchorGroupInput(BaseModel):
    base_material: Literal["reinforced_concrete", "solid_masonry", "unknown"]
    plate_width_mm: float = Field(gt=0)
    plate_depth_mm: float = Field(gt=0)
    anchor_diameter_mm: float = Field(gt=0)
    anchor_positions: list[FastenerPosition] = Field(min_length=2)
    anchor_fu_mpa: float | None = Field(default=None, gt=0)
    anchor_tension_design_capacity_kn: float | None = Field(default=None, gt=0)
    anchor_shear_design_capacity_kn: float | None = Field(default=None, gt=0)
    minimum_spacing_mm: float | None = Field(default=None, gt=0)
    minimum_edge_distance_mm: float | None = Field(default=None, gt=0)

    concrete_capacity_method: Literal["provided", "simplified"] = "provided"
    concrete_cone_design_capacity_kn: float | None = Field(default=None, gt=0)
    concrete_pullout_design_capacity_kn: float | None = Field(default=None, gt=0)
    concrete_splitting_design_capacity_kn: float | None = Field(default=None, gt=0)
    concrete_fc_mpa: float | None = Field(default=None, gt=0)
    effective_embedment_mm: float | None = Field(default=None, gt=0)

    masonry_evaluated_tension_capacity_kn: float | None = Field(
        default=None, gt=0
    )
    masonry_evaluated_shear_capacity_kn: float | None = Field(default=None, gt=0)
    masonry_capacity_source: str | None = None


def _check(
    *,
    key: str,
    name: str,
    effect: ConnectionEffect | None,
    demand: float,
    capacity: float,
    unit: str,
    reference: str,
    note: str | None = None,
    governing_fastener: int | None = None,
) -> DemandCapacityCheck:
    if not isfinite(demand) or demand < 0 or not isfinite(capacity) or capacity <= 0:
        raise CalculationInputError(
            "invalid_connection_demand_capacity",
            "连接需求和承载力必须是有限非负需求及有限正承载力。",
            details={"demand": demand, "capacity": capacity, "check": key},
        )
    utilization = demand / capacity
    return DemandCapacityCheck(
        key=key,
        name=name,
        combination_id=effect.combination_id if effect else None,
        combination_name=effect.combination_name if effect else None,
        demand=Quantity(value=demand, unit=unit),
        capacity=Quantity(value=capacity, unit=unit),
        utilization=utilization,
        passed=demand <= capacity,
        reference=reference,
        note=note,
        governing_fastener=governing_fastener,
    )


def _layout(
    positions: list[FastenerPosition], plate_width: float, plate_depth: float
) -> tuple[list[tuple[float, float]], float, float]:
    count = len(positions)
    x_centroid = sum(item.x_mm for item in positions) / count
    y_centroid = sum(item.y_mm for item in positions) / count
    centered = [
        (item.x_mm - x_centroid, item.y_mm - y_centroid) for item in positions
    ]
    if len({(round(x, 9), round(y, 9)) for x, y in centered}) != count:
        raise CalculationInputError(
            "duplicate_fastener_position",
            "连接件坐标不得重合。",
            field="fastener_positions",
        )
    minimum_spacing = min(
        hypot(centered[i][0] - centered[j][0], centered[i][1] - centered[j][1])
        for i in range(count)
        for j in range(i + 1, count)
    )
    edge_distances = [
        min(plate_width / 2 - abs(x), plate_depth / 2 - abs(y))
        for x, y in centered
    ]
    minimum_edge = min(edge_distances)
    if minimum_edge <= 0:
        raise CalculationInputError(
            "fastener_outside_plate",
            "连接件必须位于连接板范围内并具有正边距。",
            field="fastener_positions",
        )
    return centered, minimum_spacing, minimum_edge


def _fastener_distribution(
    effect: ConnectionEffect, positions: list[tuple[float, float]]
) -> tuple[list[float], list[float]]:
    """Elastic fastener distribution without mixing combinations."""

    count = len(positions)
    sum_x2 = sum((x / 1000) ** 2 for x, _ in positions)
    sum_y2 = sum((y / 1000) ** 2 for _, y in positions)
    sum_r2 = sum_x2 + sum_y2
    if abs(effect.my_kn_m) > 1e-12 and sum_x2 <= 1e-15:
        raise CalculationInputError(
            "anchor_layout_has_no_x_lever_arm",
            "锚栓组无法分配绕 y 轴弯矩：x 方向无力臂。",
            field="fastener_positions",
        )
    if abs(effect.mx_kn_m) > 1e-12 and sum_y2 <= 1e-15:
        raise CalculationInputError(
            "anchor_layout_has_no_y_lever_arm",
            "锚栓组无法分配绕 x 轴弯矩：y 方向无力臂。",
            field="fastener_positions",
        )
    if abs(effect.torsion_kn_m) > 1e-12 and sum_r2 <= 1e-15:
        raise CalculationInputError(
            "anchor_layout_has_no_torsion_lever_arm",
            "锚栓组无法分配扭矩：连接件无极惯性力臂。",
            field="fastener_positions",
        )

    uniform_tension = max(-effect.n_kn, 0.0) / count
    tensions: list[float] = []
    shears: list[float] = []
    for x_mm, y_mm in positions:
        x_m = x_mm / 1000
        y_m = y_mm / 1000
        tension = uniform_tension
        if sum_y2 > 0:
            tension += effect.mx_kn_m * y_m / sum_y2
        if sum_x2 > 0:
            tension += effect.my_kn_m * x_m / sum_x2
        tensions.append(max(tension, 0.0))

        vx = effect.vx_kn / count
        vy = effect.vy_kn / count
        if sum_r2 > 0:
            vx -= effect.torsion_kn_m * y_m / sum_r2
            vy += effect.torsion_kn_m * x_m / sum_r2
        shears.append(hypot(vx, vy))
    return tensions, shears


def _require_effects(effects: list[ConnectionEffect]) -> None:
    if not effects:
        raise CalculationInputError(
            "missing_connection_effects",
            "连接验算至少需要一个已组合作用效应。",
            field="effects",
        )
    identities = [(item.combination_id, item.limit_state) for item in effects]
    if len(set(identities)) != len(identities):
        raise CalculationInputError(
            "duplicate_connection_combination",
            "连接作用效应的组合 ID 与极限状态必须唯一。",
            field="effects",
        )


def _timber_capacities(
    data: TimberPostBaseInput,
) -> tuple[dict[str, float], dict[str, str]]:
    area = pi * data.fastener_diameter_mm**2 / 4
    bearing = data.bearing_design_capacity_kn
    bearing_source = "项目输入的设计承载力"
    if bearing is None and data.timber_compression_design_mpa is not None:
        bearing = (
            data.timber_compression_design_mpa
            * data.post_width_mm
            * data.post_depth_mm
            / 1000
        )
        bearing_source = "木材顺纹承压设计强度 × 柱端承压面积"

    tension = data.fastener_tension_design_capacity_kn
    tension_source = "项目输入的单件设计承载力"
    if tension is None:
        candidates: list[tuple[float, str]] = []
        if data.fastener_fu_mpa is not None:
            candidates.append(
                (0.65 * data.fastener_fu_mpa * area / 1000, "连接件钢材拉力筛查")
            )
        if (
            data.timber_withdrawal_design_mpa is not None
            and data.embedment_length_mm is not None
        ):
            candidates.append(
                (
                    data.timber_withdrawal_design_mpa
                    * pi
                    * data.fastener_diameter_mm
                    * data.embedment_length_mm
                    / 1000,
                    "木材拔出侧表面设计强度筛查",
                )
            )
        if candidates:
            tension, tension_source = min(candidates, key=lambda item: item[0])

    shear = data.fastener_shear_design_capacity_kn
    shear_source = "项目输入的单件设计承载力"
    if shear is None:
        shear_candidates: list[tuple[float, str]] = []
        if data.fastener_fu_mpa is not None:
            shear_candidates.append(
                (0.40 * data.fastener_fu_mpa * area / 1000, "连接件钢材剪切筛查")
            )
        if (
            data.timber_shear_design_mpa is not None
            and data.embedment_length_mm is not None
        ):
            shear_candidates.append(
                (
                    data.timber_shear_design_mpa
                    * data.fastener_diameter_mm
                    * data.embedment_length_mm
                    / 1000,
                    "木材销槽剪切面积筛查",
                )
            )
        if shear_candidates:
            shear, shear_source = min(shear_candidates, key=lambda item: item[0])

    bending = data.connector_bending_design_capacity_kn_m
    bending_source = "项目输入的单件设计承载力"
    if (
        bending is None
        and data.connector_bending_strength_mpa is not None
        and data.connector_section_modulus_mm3 is not None
    ):
        bending = (
            data.connector_bending_strength_mpa
            * data.connector_section_modulus_mm3
            / 1_000_000
        )
        bending_source = "连接件设计强度 × 截面模量"

    missing = [
        name
        for name, value in {
            "bearing": bearing,
            "tension": tension,
            "shear": shear,
            "bending": bending,
        }.items()
        if value is None
    ]
    if missing:
        raise CalculationInputError(
            "missing_connection_capacity",
            "木柱脚缺少设计承载力或完整材料参数。",
            field=missing[0],
            details={"missing": missing},
        )
    capacities = {
        "bearing": float(bearing),
        "tension": float(tension),
        "shear": float(shear),
        "bending": float(bending),
    }
    sources = {
        "bearing": bearing_source,
        "tension": tension_source,
        "shear": shear_source,
        "bending": bending_source,
    }
    return capacities, sources


def calculate_timber_post_base(
    data: TimberPostBaseInput, effects: list[ConnectionEffect]
) -> ConnectionResult:
    """Screen a regular metal timber post base under combined actions."""

    _require_effects(effects)
    positions, actual_spacing, actual_edge = _layout(
        data.fastener_positions, data.plate_width_mm, data.plate_depth_mm
    )
    capacities, sources = _timber_capacities(data)
    required_spacing = data.minimum_spacing_mm or 4 * data.fastener_diameter_mm
    required_edge = (
        data.minimum_edge_distance_mm or 4 * data.fastener_diameter_mm
    )
    checks: list[DemandCapacityCheck] = [
        _check(
            key="fastener_spacing",
            name="连接件最小间距",
            effect=None,
            demand=required_spacing,
            capacity=actual_spacing,
            unit="mm",
            reference="项目构造要求；未输入时按 4d 快算限值",
        ),
        _check(
            key="fastener_edge_distance",
            name="连接件最小边距",
            effect=None,
            demand=required_edge,
            capacity=actual_edge,
            unit="mm",
            reference="项目构造要求；未输入时按 4d 快算限值",
        ),
    ]
    for effect in effects:
        tensions, shears = _fastener_distribution(effect, positions)
        max_tension = max(tensions)
        tension_index = tensions.index(max_tension) + 1
        max_shear = max(shears)
        shear_index = shears.index(max_shear) + 1
        total_tension = sum(tensions)
        bearing_demand = max(effect.n_kn + total_tension, 0.0)
        bending_demand = max_shear * data.connector_standoff_mm / 1000
        interaction = sqrt(
            (max_tension / capacities["tension"]) ** 2
            + (max_shear / capacities["shear"]) ** 2
        )
        checks.extend(
            [
                _check(
                    key="timber_end_bearing",
                    name="木柱端部轴压承压",
                    effect=effect,
                    demand=bearing_demand,
                    capacity=capacities["bearing"],
                    unit="kN",
                    reference="GB 50005-2017 木构件局部承压计算路径；承载力可由项目输入",
                ),
                _check(
                    key="fastener_tension_withdrawal",
                    name="拔出/螺栓拉力",
                    effect=effect,
                    demand=max_tension,
                    capacity=capacities["tension"],
                    unit="kN/件",
                    reference="GB 50005-2017 连接设计路径；项目设计承载力优先",
                    governing_fastener=tension_index,
                ),
                _check(
                    key="fastener_horizontal_shear",
                    name="连接件水平剪切",
                    effect=effect,
                    demand=max_shear,
                    capacity=capacities["shear"],
                    unit="kN/件",
                    reference="GB 50005-2017 连接设计路径；项目设计承载力优先",
                    governing_fastener=shear_index,
                ),
                _check(
                    key="fastener_tension_shear_interaction",
                    name="连接件拉剪组合",
                    effect=effect,
                    demand=interaction,
                    capacity=1.0,
                    unit="1",
                    reference="椭圆拉剪相互作用快算",
                    governing_fastener=tension_index,
                ),
                _check(
                    key="connector_bending",
                    name="金属连接件弯曲",
                    effect=effect,
                    demand=bending_demand,
                    capacity=capacities["bending"],
                    unit="kN·m/件",
                    reference="连接件悬臂力臂快算；项目设计承载力优先",
                    governing_fastener=shear_index,
                ),
            ]
        )
    governing = max(checks, key=lambda item: item.utilization)
    return ConnectionResult(
        status="passed" if all(item.passed for item in checks) else "failed",
        effects=effects,
        checks=checks,
        governing_check=f"{governing.key}:{governing.combination_id or 'layout'}",
        assumptions=[
            "作用效应已完成组合，本模块不再次施加分项系数。",
            "连接件按弹性分配，木柱端部与金属连接件共同满足静力平衡。",
            "未输入项目构造限值时，间距和边距采用显式标注的快算限值。",
        ],
        applicability=[
            "规则金属木柱脚、至少两个不重合连接件",
            "静力轴力、双向剪力、双向弯矩及扭矩组合",
            "不覆盖循环疲劳、火灾、腐朽、劈裂扩展和产品专有认证",
        ],
        capacity_sources=sources,
        warnings=["计算方法尚未完成独立验证，不得据此宣称专业验算已验证。"],
    )


def _steel_anchor_capacities(
    data: WallAnchorGroupInput,
) -> tuple[float, float, dict[str, str]]:
    tension = data.anchor_tension_design_capacity_kn
    shear = data.anchor_shear_design_capacity_kn
    sources: dict[str, str] = {}
    if tension is not None:
        sources["anchor_steel_tension"] = "项目输入的单锚栓设计承载力"
    if shear is not None:
        sources["anchor_steel_shear"] = "项目输入的单锚栓设计承载力"
    if tension is None or shear is None:
        if data.anchor_fu_mpa is None:
            raise CalculationInputError(
                "missing_anchor_steel_capacity",
                "须输入锚栓钢材设计承载力或锚栓抗拉强度。",
                field="anchor_fu_mpa",
            )
        area = pi * data.anchor_diameter_mm**2 / 4
        if tension is None:
            tension = 0.65 * data.anchor_fu_mpa * area / 1000
            sources["anchor_steel_tension"] = "0.65 fu A 钢材拉力筛查"
        if shear is None:
            shear = 0.40 * data.anchor_fu_mpa * area / 1000
            sources["anchor_steel_shear"] = "0.40 fu A 钢材剪切筛查"
    return float(tension), float(shear), sources


def _concrete_capacities(
    data: WallAnchorGroupInput,
    *,
    anchor_count: int,
    actual_spacing: float,
    actual_edge: float,
) -> tuple[dict[str, float], dict[str, str], list[str]]:
    if data.concrete_capacity_method == "provided":
        provided = {
            "concrete_cone": data.concrete_cone_design_capacity_kn,
            "concrete_pullout": data.concrete_pullout_design_capacity_kn,
            "concrete_splitting": data.concrete_splitting_design_capacity_kn,
        }
        missing = [key for key, value in provided.items() if value is None]
        if missing:
            raise CalculationInputError(
                "missing_concrete_anchor_capacity",
                "RC 基材须提供锥体、拔出和劈裂设计承载力，或选择简化快算。",
                field=missing[0],
                details={"missing": missing},
            )
        return (
            {key: float(value) for key, value in provided.items()},  # type: ignore[arg-type]
            {key: "项目输入的锚栓组设计承载力" for key in provided},
            [],
        )

    if data.concrete_fc_mpa is None or data.effective_embedment_mm is None:
        raise CalculationInputError(
            "missing_simplified_concrete_parameters",
            "简化 RC 锚固快算须输入混凝土强度和有效锚固深度。",
            field="concrete_fc_mpa",
        )
    fc = data.concrete_fc_mpa
    embedment = data.effective_embedment_mm
    spacing_factor = min(1.0, actual_spacing / (3 * embedment))
    effective_count = 1 + (anchor_count - 1) * spacing_factor
    edge_factor = min(1.0, actual_edge / (1.5 * embedment))
    cone = 7.2 * sqrt(fc) * embedment**1.5 / 1000 * effective_count * edge_factor
    pullout = (
        8
        * fc
        * pi
        * data.anchor_diameter_mm
        * embedment
        / 1000
        * anchor_count
    )
    splitting = cone * edge_factor
    source = "未验证的锚固几何简化式，仅用于方案筛查"
    return (
        {
            "concrete_cone": cone,
            "concrete_pullout": pullout,
            "concrete_splitting": splitting,
        },
        {
            "concrete_cone": source,
            "concrete_pullout": source,
            "concrete_splitting": source,
        },
        ["RC 锚固承载力使用简化式，不替代锚栓产品认证和完整锚固设计。"],
    )


def calculate_wall_anchor_group(
    data: WallAnchorGroupInput, effects: list[ConnectionEffect]
) -> ConnectionResult:
    """Screen a wall-mounted canopy anchor group without hiding substrate gaps."""

    _require_effects(effects)
    if data.base_material == "unknown":
        return ConnectionResult(
            status="capability_unavailable",
            effects=effects,
            checks=[],
            governing_check=None,
            assumptions=["未知墙体基材不采用默认锚固承载力。"],
            applicability=["墙附雨棚锚栓组；基材必须明确"],
            capacity_sources={},
            warnings=["墙体基材未知，无法生成锚固验算结论。"],
        )

    positions, actual_spacing, actual_edge = _layout(
        data.anchor_positions, data.plate_width_mm, data.plate_depth_mm
    )
    steel_tension, steel_shear, sources = _steel_anchor_capacities(data)
    required_spacing = data.minimum_spacing_mm or 3 * data.anchor_diameter_mm
    required_edge = data.minimum_edge_distance_mm or 1.5 * data.anchor_diameter_mm
    warnings: list[str] = []
    substrate: dict[str, float]
    if data.base_material == "reinforced_concrete":
        substrate, substrate_sources, capacity_warnings = _concrete_capacities(
            data,
            anchor_count=len(positions),
            actual_spacing=actual_spacing,
            actual_edge=actual_edge,
        )
        sources.update(substrate_sources)
        warnings.extend(capacity_warnings)
    else:
        if (
            data.masonry_evaluated_tension_capacity_kn is None
            or data.masonry_evaluated_shear_capacity_kn is None
            or not data.masonry_capacity_source
            or not data.masonry_capacity_source.strip()
        ):
            raise CalculationInputError(
                "missing_evaluated_masonry_capacity",
                "实心砌体仅接受经评估的拉力、剪力设计承载力及来源。",
                field="masonry_evaluated_tension_capacity_kn",
            )
        substrate = {
            "masonry_tension": data.masonry_evaluated_tension_capacity_kn,
            "masonry_shear": data.masonry_evaluated_shear_capacity_kn,
        }
        sources.update(
            {
                "masonry_tension": data.masonry_capacity_source.strip(),
                "masonry_shear": data.masonry_capacity_source.strip(),
            }
        )

    checks: list[DemandCapacityCheck] = [
        _check(
            key="anchor_spacing",
            name="锚栓最小间距",
            effect=None,
            demand=required_spacing,
            capacity=actual_spacing,
            unit="mm",
            reference="项目/产品构造要求；未输入时按 3d 快算限值",
        ),
        _check(
            key="anchor_edge_distance",
            name="锚栓最小边距",
            effect=None,
            demand=required_edge,
            capacity=actual_edge,
            unit="mm",
            reference="项目/产品构造要求；未输入时按 1.5d 快算限值",
        ),
    ]
    for effect in effects:
        tensions, shears = _fastener_distribution(effect, positions)
        max_tension = max(tensions)
        max_shear = max(shears)
        tension_index = tensions.index(max_tension) + 1
        shear_index = shears.index(max_shear) + 1
        group_tension = sum(tensions)
        group_shear = hypot(effect.vx_kn, effect.vy_kn)
        steel_interaction = sqrt(
            (max_tension / steel_tension) ** 2 + (max_shear / steel_shear) ** 2
        )
        checks.extend(
            [
                _check(
                    key="anchor_steel_tension",
                    name="锚栓钢材受拉",
                    effect=effect,
                    demand=max_tension,
                    capacity=steel_tension,
                    unit="kN/根",
                    reference="GB 50017-2017 钢材承载路径；项目/产品设计值优先",
                    governing_fastener=tension_index,
                ),
                _check(
                    key="anchor_steel_shear",
                    name="锚栓钢材受剪",
                    effect=effect,
                    demand=max_shear,
                    capacity=steel_shear,
                    unit="kN/根",
                    reference="GB 50017-2017 钢材承载路径；项目/产品设计值优先",
                    governing_fastener=shear_index,
                ),
                _check(
                    key="anchor_steel_interaction",
                    name="锚栓钢材拉剪组合",
                    effect=effect,
                    demand=steel_interaction,
                    capacity=1.0,
                    unit="1",
                    reference="椭圆拉剪相互作用快算",
                    governing_fastener=tension_index,
                ),
            ]
        )
        if data.base_material == "reinforced_concrete":
            for key, label in (
                ("concrete_cone", "混凝土锥体受拉"),
                ("concrete_pullout", "锚栓拔出"),
                ("concrete_splitting", "混凝土劈裂"),
            ):
                checks.append(
                    _check(
                        key=key,
                        name=label,
                        effect=effect,
                        demand=group_tension,
                        capacity=substrate[key],
                        unit="kN/组",
                        reference=sources[key],
                    )
                )
        else:
            checks.extend(
                [
                    _check(
                        key="masonry_tension",
                        name="实心砌体锚固受拉",
                        effect=effect,
                        demand=group_tension,
                        capacity=substrate["masonry_tension"],
                        unit="kN/组",
                        reference=sources["masonry_tension"],
                    ),
                    _check(
                        key="masonry_shear",
                        name="实心砌体锚固受剪",
                        effect=effect,
                        demand=group_shear,
                        capacity=substrate["masonry_shear"],
                        unit="kN/组",
                        reference=sources["masonry_shear"],
                    ),
                ]
            )
    governing = max(checks, key=lambda item: item.utilization)
    warnings.append("计算方法尚未完成独立验证，不得据此宣称专业验算已验证。")
    return ConnectionResult(
        status="passed" if all(item.passed for item in checks) else "failed",
        effects=effects,
        checks=checks,
        governing_check=f"{governing.key}:{governing.combination_id or 'layout'}",
        assumptions=[
            "上游六分量效应按同一组合逐项验算，不拼接包络且不重复分项。",
            "锚栓组按刚性连接板和弹性分配计算；受压由墙面承压路径承担。",
            "实心砌体不由材料名称推导承载力，只采用经评估的项目设计值。",
        ],
        applicability=[
            "规则墙附雨棚锚栓组、静力作用",
            "RC 基材或具有经评估锚固设计值的实心砌体",
            "不覆盖空心砌块、未知墙体、疲劳、火灾及产品专有安装偏差",
        ],
        capacity_sources=sources,
        warnings=warnings,
    )
