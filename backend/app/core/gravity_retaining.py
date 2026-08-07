from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, radians, sin, tan
from typing import Literal

from .errors import CalculationInputError
from .schemas import LoadDirection, Quantity, ReactionEnvelope


@dataclass(frozen=True)
class GravityRetainingInput:
    combination_id: str
    combination_name: str
    limit_state: Literal["ULS", "SLS"]
    retained_height_m: float
    base_width_m: float
    base_slab_thickness_m: float
    wall_bottom_thickness_m: float
    wall_top_thickness_m: float
    toe_projection_m: float
    wall_unit_weight_kn_m3: float
    soil_unit_weight_kn_m3: float
    soil_friction_angle_deg: float
    surcharge_kpa: float
    base_friction_coefficient: float
    soil_bearing_capacity_kpa: float
    material_compressive_design_kpa: float
    water_depth_behind_m: float = 0.0
    water_unit_weight_kn_m3: float = 10.0
    uplift_head_toe_m: float = 0.0
    uplift_head_heel_m: float = 0.0
    shear_key_depth_m: float = 0.0
    base_inclination_deg: float = 0.0
    sliding_safety_factor: float = 1.0
    overturning_safety_factor: float = 1.0



@dataclass(frozen=True)
class GravityCheck:
    key: str
    name: str
    demand: Quantity
    capacity: Quantity
    utilization: float
    passed: bool
    combination_id: str
    reference: str
    note: str | None = None


@dataclass(frozen=True)
class GravityRetainingResult:
    status: Literal["passed", "failed"]
    verification_status: Literal["unverified"]
    active_coefficient: float
    soil_resultant_kn_per_m: float
    surcharge_resultant_kn_per_m: float
    water_resultant_kn_per_m: float
    total_horizontal_kn_per_m: float
    lateral_moment_kn_m_per_m: float
    wall_weight_kn_per_m: float
    base_weight_kn_per_m: float
    uplift_kn_per_m: float
    effective_vertical_kn_per_m: float
    resultant_location_from_toe_m: float
    eccentricity_m: float
    contact_length_m: float
    q_max_kpa: float
    q_min_kpa: float
    material_max_compression_kpa: float
    checks: tuple[GravityCheck, ...]
    reaction_envelopes: tuple[ReactionEnvelope, ...]
    assumptions: tuple[str, ...]
    applicability: tuple[str, ...]
    warnings: tuple[str, ...]


def _finite(value: float, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_number", f"{field} 必须是有限数值。", field=field
        ) from exc
    if not isfinite(number):
        raise CalculationInputError(
            "invalid_number", f"{field} 必须是有限数值。", field=field
        )
    return number


def _positive(value: float, field: str) -> float:
    number = _finite(value, field)
    if number <= 0:
        raise CalculationInputError(
            "non_positive_value", f"{field} 必须大于零。", field=field
        )
    return number


def _non_negative(value: float, field: str) -> float:
    number = _finite(value, field)
    if number < 0:
        raise CalculationInputError(
            "negative_value", f"{field} 不得小于零。", field=field
        )
    return number


def _check(
    data: GravityRetainingInput,
    *,
    key: str,
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    reference: str,
    note: str | None = None,
) -> GravityCheck:
    if demand < 0 or capacity <= 0 or not isfinite(demand + capacity):
        raise CalculationInputError(
            "invalid_check_value",
            "挡土墙验算需求必须非负且承载力必须为正。",
            details={"key": key, "demand": demand, "capacity": capacity},
        )
    utilization = demand / capacity
    return GravityCheck(
        key=key,
        name=name,
        demand=Quantity(value=demand, unit=unit),
        capacity=Quantity(value=capacity, unit=unit),
        utilization=utilization,
        passed=demand <= capacity,
        combination_id=data.combination_id,
        reference=reference,
        note=note,
    )


def _validate(data: GravityRetainingInput) -> None:
    for field in (
        "retained_height_m",
        "base_width_m",
        "wall_bottom_thickness_m",
        "wall_top_thickness_m",
        "wall_unit_weight_kn_m3",
        "soil_unit_weight_kn_m3",
        "base_friction_coefficient",
        "soil_bearing_capacity_kpa",
        "material_compressive_design_kpa",
        "water_unit_weight_kn_m3",
        "sliding_safety_factor",
        "overturning_safety_factor",
    ):
        _positive(getattr(data, field), field)
    for field in (
        "base_slab_thickness_m",
        "toe_projection_m",
        "surcharge_kpa",
        "water_depth_behind_m",
        "uplift_head_toe_m",
        "uplift_head_heel_m",
        "shear_key_depth_m",
    ):
        _non_negative(getattr(data, field), field)
    inclination = _finite(data.base_inclination_deg, "base_inclination_deg")
    if not -20.0 <= inclination <= 20.0:
        raise CalculationInputError(
            "invalid_base_inclination",
            "基底倾角必须在 -20° 至 20° 之间。",
            field="base_inclination_deg",
        )

    friction_angle = _finite(data.soil_friction_angle_deg, "soil_friction_angle_deg")
    if not 0 < friction_angle < 45:
        raise CalculationInputError(
            "invalid_friction_angle",
            "Rankine 主动土压力要求土内摩擦角大于 0°且小于 45°。",
            field="soil_friction_angle_deg",
        )
    if data.wall_top_thickness_m > data.wall_bottom_thickness_m:
        raise CalculationInputError(
            "invalid_wall_taper",
            "首期重力墙要求墙顶厚度不得大于墙底厚度。",
            field="wall_top_thickness_m",
        )
    if data.toe_projection_m + data.wall_bottom_thickness_m > data.base_width_m:
        raise CalculationInputError(
            "wall_outside_base",
            "墙身底面必须完整落在基底宽度内。",
            field="toe_projection_m",
        )
    if data.water_depth_behind_m > data.retained_height_m:
        raise CalculationInputError(
            "water_depth_exceeds_wall",
            "墙后水深不得大于挡土高度。",
            field="water_depth_behind_m",
        )
    if data.soil_unit_weight_kn_m3 <= data.water_unit_weight_kn_m3:
        raise CalculationInputError(
            "invalid_submerged_unit_weight",
            "土重度必须大于水重度，才能形成正的浮重度。",
            field="soil_unit_weight_kn_m3",
        )
    if not data.combination_id.strip() or not data.combination_name.strip():
        raise CalculationInputError(
            "missing_combination_identity",
            "重力式挡土墙必须提供组合 ID 和名称。",
            field="combination_id",
        )


def _trapezoid_horizontal_centroid(
    *, bottom_width: float, top_width: float
) -> float:
    """Centroid from the vertical front face of a tapered wall body."""

    return (
        bottom_width**2 + bottom_width * top_width + top_width**2
    ) / (3 * (bottom_width + top_width))


def _soil_water_actions(
    data: GravityRetainingInput,
) -> tuple[float, float, float, float, float]:
    """Return Ka, soil, surcharge, water and total base moment per metre."""

    height = data.retained_height_m
    water_depth = data.water_depth_behind_m
    dry_height = height - water_depth
    gamma = data.soil_unit_weight_kn_m3
    submerged_gamma = gamma - data.water_unit_weight_kn_m3
    ka = tan(radians(45 - data.soil_friction_angle_deg / 2)) ** 2

    dry_wedge = 0.5 * ka * gamma * dry_height**2
    dry_wedge_height = water_depth + dry_height / 3 if dry_height else 0.0
    saturated_rectangle = ka * gamma * dry_height * water_depth
    saturated_triangle = 0.5 * ka * submerged_gamma * water_depth**2
    soil_resultant = dry_wedge + saturated_rectangle + saturated_triangle
    soil_moment = (
        dry_wedge * dry_wedge_height
        + saturated_rectangle * water_depth / 2
        + saturated_triangle * water_depth / 3
    )

    surcharge = ka * data.surcharge_kpa * height
    surcharge_moment = surcharge * height / 2
    water = 0.5 * data.water_unit_weight_kn_m3 * water_depth**2
    water_moment = water * water_depth / 3
    return ka, soil_resultant, surcharge, water, (
        soil_moment + surcharge_moment + water_moment
    )


def calculate_gravity_retaining_wall(
    data: GravityRetainingInput,
) -> GravityRetainingResult:
    """Calculate a straight gravity retaining wall per metre run.

    The function is a quick-estimate mechanics core.  It deliberately excludes
    passive soil resistance, seismic action, global slope stability, settlement,
    bearing-capacity derivation and construction-stage effects.
    """

    _validate(data)
    ka, soil_force, surcharge_force, water_force, lateral_moment = (
        _soil_water_actions(data)
    )
    horizontal = soil_force + surcharge_force + water_force

    wall_area = (
        data.wall_bottom_thickness_m + data.wall_top_thickness_m
    ) * data.retained_height_m / 2
    wall_weight = wall_area * data.wall_unit_weight_kn_m3
    wall_centroid = data.toe_projection_m + _trapezoid_horizontal_centroid(
        bottom_width=data.wall_bottom_thickness_m,
        top_width=data.wall_top_thickness_m,
    )
    base_weight = (
        data.base_width_m
        * data.base_slab_thickness_m
        * data.wall_unit_weight_kn_m3
    )
    stabilizing_moment = (
        wall_weight * wall_centroid + base_weight * data.base_width_m / 2
    )

    toe_pressure = data.water_unit_weight_kn_m3 * data.uplift_head_toe_m
    heel_pressure = data.water_unit_weight_kn_m3 * data.uplift_head_heel_m
    uplift = (toe_pressure + heel_pressure) * data.base_width_m / 2
    if toe_pressure + heel_pressure > 0:
        uplift_centroid = data.base_width_m * (
            toe_pressure + 2 * heel_pressure
        ) / (3 * (toe_pressure + heel_pressure))
    else:
        uplift_centroid = data.base_width_m / 2
    uplift_moment = uplift * uplift_centroid

    effective_vertical = wall_weight + base_weight - uplift
    if effective_vertical <= 0:
        raise CalculationInputError(
            "non_positive_effective_vertical",
            "浮力已抵消全部竖向自重，基底无法形成压应力。",
            field="uplift_head_heel_m",
        )
    net_stabilizing_moment = stabilizing_moment - lateral_moment - uplift_moment
    resultant_location = net_stabilizing_moment / effective_vertical
    eccentricity = data.base_width_m / 2 - resultant_location

    warnings: list[str] = []
    if 0 < resultant_location < data.base_width_m:
        if abs(eccentricity) <= data.base_width_m / 6:
            q_average = effective_vertical / data.base_width_m
            q_toe = q_average * (1 + 6 * eccentricity / data.base_width_m)
            q_heel = q_average * (1 - 6 * eccentricity / data.base_width_m)
            q_max = max(q_toe, q_heel)
            q_min = min(q_toe, q_heel)
            contact_length = data.base_width_m
        elif resultant_location < data.base_width_m / 2:
            contact_length = 3 * resultant_location
            q_max = 2 * effective_vertical / contact_length
            q_min = 0.0
            warnings.append("基底在后缘局部脱开，压力按受压区三角形分布筛查。")
        else:
            contact_length = 3 * (data.base_width_m - resultant_location)
            q_max = 2 * effective_vertical / contact_length
            q_min = 0.0
            warnings.append("基底在前缘局部脱开，压力按受压区三角形分布筛查。")
    else:
        contact_length = 0.0
        # Preserve a finite structured failed result instead of allowing an
        # infinite pressure to escape through the public result contract.
        q_max = effective_vertical / 1.0e-9
        q_min = 0.0
        warnings.append("基底合力已落在基底范围之外，整体倾覆失稳。")

    wall_average_compression = wall_weight / data.wall_bottom_thickness_m
    material_max_compression = (
        wall_average_compression
        + 6 * lateral_moment / data.wall_bottom_thickness_m**2
    )

    kp = tan(radians(45.0 + data.soil_friction_angle_deg / 2.0)) ** 2
    h_base = data.base_slab_thickness_m
    h_key = data.shear_key_depth_m
    passive_resistance = (
        0.5 * kp * data.soil_unit_weight_kn_m3 * ((h_base + h_key)**2 - h_base**2)
        if h_key > 0
        else 0.0
    )

    alpha = radians(data.base_inclination_deg)
    if data.base_inclination_deg != 0.0:
        sliding_demand = max(0.0, horizontal * cos(alpha) - effective_vertical * sin(alpha)) * data.sliding_safety_factor
        normal_force_on_base = effective_vertical * cos(alpha) + horizontal * sin(alpha)
        sliding_capacity = data.base_friction_coefficient * normal_force_on_base + passive_resistance
        sliding_ref = f"基底倾角 {data.base_inclination_deg:.1f}° 法向摩擦与倾斜滑动力平衡"
    else:
        sliding_demand = horizontal * data.sliding_safety_factor
        sliding_capacity = data.base_friction_coefficient * effective_vertical + passive_resistance
        sliding_ref = "静力平衡；含底板抗滑凸榫被动阻力" if h_key > 0 else "静力平衡；不计被动土压力"

    net_center_moment = effective_vertical * eccentricity
    contact_capacity = data.base_width_m / 6
    h_mid = data.retained_height_m / 2.0
    v_mid_shear = 0.5 * ka * data.soil_unit_weight_kn_m3 * (h_mid**2)
    b_mid = data.wall_top_thickness_m + 0.5 * (data.wall_bottom_thickness_m - data.wall_top_thickness_m)
    tau_mid = v_mid_shear / b_mid  # kPa
    # Allowable shear design capacity assumed 0.1 * material_compressive_design_kpa for unreinforced masonry/concrete
    tau_allowable = 0.10 * data.material_compressive_design_kpa

    checks = (
        _check(
            data,
            key="sliding",
            name="抗滑移",
            demand=sliding_demand,
            capacity=sliding_capacity,
            unit="kN/m",
            reference=sliding_ref,
            note=f"包含抗滑凸榫被动阻力 {passive_resistance:.1f} kN/m。" if h_key > 0 else None,
        ),
        _check(
            data,
            key="overturning",
            name="抗倾覆",
            demand=(lateral_moment + uplift_moment)
            * data.overturning_safety_factor,
            capacity=stabilizing_moment,
            unit="kN·m/m",
            reference="绕基底前趾静力矩平衡",
        ),
        _check(
            data,
            key="eccentricity",
            name="基底偏心距",
            demand=abs(eccentricity),
            capacity=contact_capacity,
            unit="m",
            reference="线性全接触核芯范围 B/6",
            note="超过限值时结果仍输出受压区三角形压力，但本项判定失败。",
        ),
        _check(
            data,
            key="base_bearing",
            name="地基最大压力",
            demand=q_max,
            capacity=data.soil_bearing_capacity_kpa,
            unit="kPa",
            reference="基底合力和接触区静力平衡",
        ),
        _check(
            data,
            key="material_compression",
            name="墙体底部最大压应力",
            demand=material_max_compression,
            capacity=data.material_compressive_design_kpa,
            unit="kPa",
            reference="梯形/矩形墙身一米条带弹性压应力筛查",
        ),
        _check(
            data,
            key="wall_mid_shear",
            name="墙身截面平均剪应力",
            demand=tau_mid,
            capacity=tau_allowable,
            unit="kPa",
            reference="墙身H/2高截面无筋砌体/混凝土剪应力估算(f_v=0.10 f_cu)",
        ),
    )
    status: Literal["passed", "failed"] = (
        "passed" if all(item.passed for item in checks) else "failed"
    )
    envelope = ReactionEnvelope(
        name="gravity_retaining_base",
        limit_state=data.limit_state,
        combination_id=data.combination_id,
        combination_name=data.combination_name,
        direction=LoadDirection.GRAVITY,
        components={
            "N": Quantity(value=effective_vertical, unit="kN/m"),
            "Vx": Quantity(value=horizontal, unit="kN/m"),
            "Vy": Quantity(value=0.0, unit="kN/m"),
            "Mx": Quantity(value=0.0, unit="kN·m/m"),
            "My": Quantity(value=net_center_moment, unit="kN·m/m"),
            "T": Quantity(value=0.0, unit="kN·m/m"),
        },
    )
    return GravityRetainingResult(
        status=status,
        verification_status="unverified",
        active_coefficient=ka,
        soil_resultant_kn_per_m=soil_force,
        surcharge_resultant_kn_per_m=surcharge_force,
        water_resultant_kn_per_m=water_force,
        total_horizontal_kn_per_m=horizontal,
        lateral_moment_kn_m_per_m=lateral_moment,
        wall_weight_kn_per_m=wall_weight,
        base_weight_kn_per_m=base_weight,
        uplift_kn_per_m=uplift,
        effective_vertical_kn_per_m=effective_vertical,
        resultant_location_from_toe_m=resultant_location,
        eccentricity_m=eccentricity,
        contact_length_m=contact_length,
        q_max_kpa=q_max,
        q_min_kpa=q_min,
        material_max_compression_kpa=material_max_compression,
        checks=checks,
        reaction_envelopes=(envelope,),
        assumptions=(
            "墙后填土水平、单一土层，按 Rankine 主动土压力。",
            "地下水以下土压力采用浮重度，并另计静水侧压力。",
            "基底抗滑仅采用有效竖向力乘摩擦系数，不采用被动土压力。",
            "所有作用属于同一输入组合，本核心不再次施加分项系数。",
        ),
        applicability=(
            "直线重力式挡土墙、矩形或墙顶不宽于墙底的梯形截面",
            "每延米静力快算；已知水位和基底扬压力水头",
            "不含地震、整体稳定、沉降、软基、基岩锚固和施工阶段",
        ),
        warnings=tuple(
            warnings
            + ["核心尚未完成独立验证，verification_status 保持 unverified。"]
        ),
    )
