from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, radians, tan
from typing import Literal

from .errors import CalculationInputError


PoolState = Literal["empty", "full"]
LimitState = Literal["SLS", "ULS"]


@dataclass(frozen=True)
class RectangularPoolGeometry:
    inside_length_m: float
    inside_width_m: float
    wall_height_m: float
    wall_thickness_mm: float
    base_thickness_mm: float
    base_projection_m: float = 0.20
    retained_soil_height_m: float = 0.0
    wall_horizontal_span_m: float | None = None


@dataclass(frozen=True)
class PoolMaterials:
    concrete_unit_weight_kn_m3: float = 25.0
    water_unit_weight_kn_m3: float = 10.0
    soil_unit_weight_kn_m3: float = 18.0
    soil_friction_angle_deg: float = 30.0
    surcharge_kpa: float = 0.0
    allowable_bearing_kpa: float = 120.0
    concrete_fc_mpa: float = 14.3
    concrete_ft_mpa: float = 1.43
    rebar_fy_mpa: float = 360.0
    rebar_es_mpa: float = 200_000.0


@dataclass(frozen=True)
class PoolReinforcement:
    wall_vertical_as_mm2_per_m: float = 1_000.0
    wall_horizontal_as_mm2_per_m: float = 1_000.0
    base_x_as_mm2_per_m: float = 1_200.0
    base_y_as_mm2_per_m: float = 1_200.0
    wall_bar_diameter_mm: float = 14.0
    base_bar_diameter_mm: float = 16.0
    wall_cover_mm: float = 35.0
    base_cover_mm: float = 40.0
    minimum_reinforcement_ratio: float = 0.002
    crack_width_limit_mm: float = 0.20


@dataclass(frozen=True)
class PoolWaterLevels:
    """Water depths; external heads are measured above the base underside."""

    full_internal_depth_m: float
    empty_external_head_m: float = 0.0
    full_external_head_m: float | None = None


@dataclass(frozen=True)
class RectangularPoolInput:
    geometry: RectangularPoolGeometry
    materials: PoolMaterials
    reinforcement: PoolReinforcement
    water_levels: PoolWaterLevels
    additional_ballast_kn: float = 0.0
    antifloat_factor: float = 1.05


@dataclass(frozen=True)
class LateralPressureComponents:
    active_coefficient: float
    external_soil_resultant_kn_per_m: float
    external_surcharge_resultant_kn_per_m: float
    external_water_resultant_kn_per_m: float
    internal_water_resultant_kn_per_m: float
    net_resultant_kn_per_m: float
    net_base_moment_kn_m_per_m: float
    net_base_pressure_kpa: float


@dataclass(frozen=True)
class WallStripDemand:
    vertical_moment_kn_m_per_m: float
    vertical_shear_kn_per_m: float
    horizontal_moment_kn_m_per_m: float
    horizontal_shear_kn_per_m: float
    pressure_direction: Literal["external_inward", "internal_outward", "balanced"]


@dataclass(frozen=True)
class BaseSlabDemand:
    uplift_kn: float
    downward_kn: float
    net_vertical_kn: float
    soil_reaction_kpa: float
    unbalanced_uplift_kn: float
    net_distributed_pressure_kpa: float
    x_moment_kn_m_per_m: float
    y_moment_kn_m_per_m: float
    x_shear_kn_per_m: float
    y_shear_kn_per_m: float
    tension_face: Literal["top", "bottom", "none"]


@dataclass(frozen=True)
class PoolCombinationResult:
    combination_id: str
    limit_state: LimitState
    pool_state: PoolState
    purpose: Literal["service", "wall_external", "wall_internal", "gravity", "uplift"]
    factors: dict[str, float]
    pressures: LateralPressureComponents
    wall: WallStripDemand
    base: BaseSlabDemand
    wall_force_balance_error_kn_per_m: float
    wall_moment_balance_error_kn_m_per_m: float
    vertical_balance_error_kn: float


@dataclass(frozen=True)
class PoolCheck:
    name: str
    demand: float
    capacity: float
    unit: str
    utilization: float
    passed: bool
    controlling_combination_id: str
    reference_basis: str


@dataclass(frozen=True)
class PoolStructureResult:
    combinations: tuple[PoolCombinationResult, ...]
    checks: tuple[PoolCheck, ...]
    governing_check: str
    governing_utilization: float
    verification_status: Literal["unverified"]
    assumptions: tuple[str, ...]
    applicability: tuple[str, ...]


def _positive(value: float, field: str, *, allow_zero: bool = False) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_pool_input", f"{field} 必须是有限数值。", field=field
        ) from exc
    if not isfinite(numeric) or numeric < 0 or (numeric == 0 and not allow_zero):
        relation = "不得小于零" if allow_zero else "必须大于零"
        raise CalculationInputError(
            "invalid_pool_input", f"{field} {relation}。", field=field
        )
    return numeric


def _validate(pool: RectangularPoolInput) -> None:
    geometry = pool.geometry
    materials = pool.materials
    reinforcement = pool.reinforcement
    levels = pool.water_levels
    for value, field in (
        (geometry.inside_length_m, "geometry.inside_length_m"),
        (geometry.inside_width_m, "geometry.inside_width_m"),
        (geometry.wall_height_m, "geometry.wall_height_m"),
        (geometry.wall_thickness_mm, "geometry.wall_thickness_mm"),
        (geometry.base_thickness_mm, "geometry.base_thickness_mm"),
        (materials.concrete_unit_weight_kn_m3, "materials.concrete_unit_weight_kn_m3"),
        (materials.water_unit_weight_kn_m3, "materials.water_unit_weight_kn_m3"),
        (materials.soil_unit_weight_kn_m3, "materials.soil_unit_weight_kn_m3"),
        (materials.allowable_bearing_kpa, "materials.allowable_bearing_kpa"),
        (materials.concrete_fc_mpa, "materials.concrete_fc_mpa"),
        (materials.concrete_ft_mpa, "materials.concrete_ft_mpa"),
        (materials.rebar_fy_mpa, "materials.rebar_fy_mpa"),
        (materials.rebar_es_mpa, "materials.rebar_es_mpa"),
        (reinforcement.wall_vertical_as_mm2_per_m, "reinforcement.wall_vertical_as_mm2_per_m"),
        (reinforcement.wall_horizontal_as_mm2_per_m, "reinforcement.wall_horizontal_as_mm2_per_m"),
        (reinforcement.base_x_as_mm2_per_m, "reinforcement.base_x_as_mm2_per_m"),
        (reinforcement.base_y_as_mm2_per_m, "reinforcement.base_y_as_mm2_per_m"),
        (reinforcement.wall_bar_diameter_mm, "reinforcement.wall_bar_diameter_mm"),
        (reinforcement.base_bar_diameter_mm, "reinforcement.base_bar_diameter_mm"),
        (reinforcement.minimum_reinforcement_ratio, "reinforcement.minimum_reinforcement_ratio"),
        (reinforcement.crack_width_limit_mm, "reinforcement.crack_width_limit_mm"),
        (pool.antifloat_factor, "antifloat_factor"),
    ):
        _positive(value, field)
    for value, field in (
        (geometry.base_projection_m, "geometry.base_projection_m"),
        (geometry.retained_soil_height_m, "geometry.retained_soil_height_m"),
        (materials.surcharge_kpa, "materials.surcharge_kpa"),
        (reinforcement.wall_cover_mm, "reinforcement.wall_cover_mm"),
        (reinforcement.base_cover_mm, "reinforcement.base_cover_mm"),
        (levels.full_internal_depth_m, "water_levels.full_internal_depth_m"),
        (levels.empty_external_head_m, "water_levels.empty_external_head_m"),
        (pool.additional_ballast_kn, "additional_ballast_kn"),
    ):
        _positive(value, field, allow_zero=True)
    if levels.full_external_head_m is not None:
        _positive(
            levels.full_external_head_m,
            "water_levels.full_external_head_m",
            allow_zero=True,
        )
    if geometry.wall_horizontal_span_m is not None:
        _positive(geometry.wall_horizontal_span_m, "geometry.wall_horizontal_span_m")
    if not 0.0 < materials.soil_friction_angle_deg < 45.0:
        raise CalculationInputError(
            "invalid_soil_friction_angle",
            "单一土层 Rankine 主动土压力要求内摩擦角大于 0°且小于 45°。",
            field="materials.soil_friction_angle_deg",
        )
    if geometry.retained_soil_height_m > geometry.wall_height_m:
        raise CalculationInputError(
            "soil_height_out_of_scope",
            "保留土高度不得超过直墙高度。",
            field="geometry.retained_soil_height_m",
        )
    if levels.full_internal_depth_m > geometry.wall_height_m:
        raise CalculationInputError(
            "internal_water_depth_out_of_scope",
            "池内设计水深不得超过直墙高度。",
            field="water_levels.full_internal_depth_m",
        )
    maximum_external_head = (
        geometry.wall_height_m + geometry.base_thickness_mm / 1000.0
    )
    for value, field in (
        (levels.empty_external_head_m, "water_levels.empty_external_head_m"),
        (
            levels.full_external_head_m,
            "water_levels.full_external_head_m",
        ),
    ):
        if value is not None and value > maximum_external_head:
            raise CalculationInputError(
                "external_water_head_out_of_scope",
                "外部水头不得超过池壁顶以上的适用边界。",
                field=field,
                details={"maximum_external_head_m": maximum_external_head},
            )
    wall_effective_depth = (
        geometry.wall_thickness_mm
        - reinforcement.wall_cover_mm
        - reinforcement.wall_bar_diameter_mm / 2.0
    )
    base_effective_depth = (
        geometry.base_thickness_mm
        - reinforcement.base_cover_mm
        - reinforcement.base_bar_diameter_mm / 2.0
    )
    if wall_effective_depth <= 0 or base_effective_depth <= 0:
        raise CalculationInputError(
            "invalid_effective_depth",
            "保护层和钢筋直径导致池壁或底板有效高度不大于零。",
            field="reinforcement",
        )


def _pressure_components(
    pool: RectangularPoolInput,
    *,
    internal_depth_m: float,
    external_water_depth_m: float,
    external_factor: float,
    internal_factor: float,
) -> LateralPressureComponents:
    geometry = pool.geometry
    materials = pool.materials
    soil_height = geometry.retained_soil_height_m
    ka = tan(radians(45.0 - materials.soil_friction_angle_deg / 2.0)) ** 2
    soil_resultant = (
        0.5 * ka * materials.soil_unit_weight_kn_m3 * soil_height**2 * external_factor
    )
    surcharge_resultant = (
        ka * materials.surcharge_kpa * soil_height * external_factor
    )
    external_water_resultant = (
        0.5
        * materials.water_unit_weight_kn_m3
        * external_water_depth_m**2
        * external_factor
    )
    internal_water_resultant = (
        0.5
        * materials.water_unit_weight_kn_m3
        * internal_depth_m**2
        * internal_factor
    )
    net_resultant = (
        soil_resultant
        + surcharge_resultant
        + external_water_resultant
        - internal_water_resultant
    )
    net_moment = (
        soil_resultant * soil_height / 3.0
        + surcharge_resultant * soil_height / 2.0
        + external_water_resultant * external_water_depth_m / 3.0
        - internal_water_resultant * internal_depth_m / 3.0
    )
    net_base_pressure = (
        ka
        * (materials.soil_unit_weight_kn_m3 * soil_height + materials.surcharge_kpa)
        * external_factor
        + materials.water_unit_weight_kn_m3
        * external_water_depth_m
        * external_factor
        - materials.water_unit_weight_kn_m3 * internal_depth_m * internal_factor
    )
    return LateralPressureComponents(
        active_coefficient=ka,
        external_soil_resultant_kn_per_m=soil_resultant,
        external_surcharge_resultant_kn_per_m=surcharge_resultant,
        external_water_resultant_kn_per_m=external_water_resultant,
        internal_water_resultant_kn_per_m=internal_water_resultant,
        net_resultant_kn_per_m=net_resultant,
        net_base_moment_kn_m_per_m=net_moment,
        net_base_pressure_kpa=net_base_pressure,
    )


def _weights(pool: RectangularPoolInput, internal_depth_m: float) -> tuple[float, float, float, float]:
    geometry = pool.geometry
    materials = pool.materials
    wall_t = geometry.wall_thickness_mm / 1000.0
    base_t = geometry.base_thickness_mm / 1000.0
    outer_length = geometry.inside_length_m + 2.0 * wall_t + 2.0 * geometry.base_projection_m
    outer_width = geometry.inside_width_m + 2.0 * wall_t + 2.0 * geometry.base_projection_m
    base_area = outer_length * outer_width
    base_weight = base_area * base_t * materials.concrete_unit_weight_kn_m3
    wall_volume = (
        2.0
        * (geometry.inside_length_m + geometry.inside_width_m + 2.0 * wall_t)
        * wall_t
        * geometry.wall_height_m
    )
    wall_weight = wall_volume * materials.concrete_unit_weight_kn_m3
    water_weight = (
        geometry.inside_length_m
        * geometry.inside_width_m
        * internal_depth_m
        * materials.water_unit_weight_kn_m3
    )
    return base_area, base_weight, wall_weight, water_weight


def _wall_demand(
    pool: RectangularPoolInput, pressure: LateralPressureComponents
) -> WallStripDemand:
    span = pool.geometry.wall_horizontal_span_m or max(
        pool.geometry.inside_length_m, pool.geometry.inside_width_m
    )
    horizontal_line_load = abs(pressure.net_base_pressure_kpa)
    if pressure.net_base_moment_kn_m_per_m > 1.0e-12:
        direction: Literal["external_inward", "internal_outward", "balanced"] = "external_inward"
    elif pressure.net_base_moment_kn_m_per_m < -1.0e-12:
        direction = "internal_outward"
    else:
        direction = "balanced"
    return WallStripDemand(
        vertical_moment_kn_m_per_m=abs(pressure.net_base_moment_kn_m_per_m),
        vertical_shear_kn_per_m=abs(pressure.net_resultant_kn_per_m),
        horizontal_moment_kn_m_per_m=horizontal_line_load * span**2 / 8.0,
        horizontal_shear_kn_per_m=horizontal_line_load * span / 2.0,
        pressure_direction=direction,
    )


def _base_demand(
    pool: RectangularPoolInput,
    *,
    internal_depth_m: float,
    external_head_m: float,
    permanent_factor: float,
    internal_water_factor: float,
    uplift_factor: float,
) -> BaseSlabDemand:
    geometry = pool.geometry
    materials = pool.materials
    area, base_weight, wall_weight, water_weight = _weights(pool, internal_depth_m)
    downward = (
        (base_weight + wall_weight + pool.additional_ballast_kn) * permanent_factor
        + water_weight * internal_water_factor
    )
    uplift = (
        area
        * external_head_m
        * materials.water_unit_weight_kn_m3
        * uplift_factor
    )
    net_vertical = downward - uplift
    soil_reaction = max(net_vertical, 0.0) / area
    unbalanced_uplift = max(-net_vertical, 0.0)
    base_self_pressure = (
        geometry.base_thickness_mm
        / 1000.0
        * materials.concrete_unit_weight_kn_m3
        * permanent_factor
    )
    ballast_pressure = pool.additional_ballast_kn * permanent_factor / area
    internal_water_pressure = (
        internal_depth_m
        * materials.water_unit_weight_kn_m3
        * internal_water_factor
    )
    uplift_pressure = (
        external_head_m * materials.water_unit_weight_kn_m3 * uplift_factor
    )
    net_distributed_pressure = (
        uplift_pressure
        + soil_reaction
        - base_self_pressure
        - ballast_pressure
        - internal_water_pressure
    )
    lx = min(geometry.inside_length_m, geometry.inside_width_m)
    ly = max(geometry.inside_length_m, geometry.inside_width_m)
    denominator = lx**4 + ly**4
    q_abs = abs(net_distributed_pressure)
    qx = q_abs * ly**4 / denominator
    qy = q_abs * lx**4 / denominator
    if net_distributed_pressure > 1.0e-12:
        tension_face: Literal["top", "bottom", "none"] = "top"
    elif net_distributed_pressure < -1.0e-12:
        tension_face = "bottom"
    else:
        tension_face = "none"
    return BaseSlabDemand(
        uplift_kn=uplift,
        downward_kn=downward,
        net_vertical_kn=net_vertical,
        soil_reaction_kpa=soil_reaction,
        unbalanced_uplift_kn=unbalanced_uplift,
        net_distributed_pressure_kpa=net_distributed_pressure,
        x_moment_kn_m_per_m=qx * lx**2 / 8.0,
        y_moment_kn_m_per_m=qy * ly**2 / 8.0,
        x_shear_kn_per_m=qx * lx / 2.0,
        y_shear_kn_per_m=qy * ly / 2.0,
        tension_face=tension_face,
    )


def _combination(
    pool: RectangularPoolInput,
    *,
    state: PoolState,
    purpose: Literal["service", "wall_external", "wall_internal", "gravity", "uplift"],
    limit_state: LimitState,
    factors: dict[str, float],
) -> PoolCombinationResult:
    levels = pool.water_levels
    internal_depth = levels.full_internal_depth_m if state == "full" else 0.0
    external_head = (
        levels.empty_external_head_m
        if state == "empty" or levels.full_external_head_m is None
        else levels.full_external_head_m
    )
    external_wall_depth = max(
        external_head - pool.geometry.base_thickness_mm / 1000.0, 0.0
    )
    pressures = _pressure_components(
        pool,
        internal_depth_m=internal_depth,
        external_water_depth_m=external_wall_depth,
        external_factor=factors["external_lateral"],
        internal_factor=factors["internal_water"],
    )
    wall = _wall_demand(pool, pressures)
    base = _base_demand(
        pool,
        internal_depth_m=internal_depth,
        external_head_m=external_head,
        permanent_factor=factors["permanent"],
        internal_water_factor=factors["internal_water"],
        uplift_factor=factors["uplift"],
    )
    support_horizontal = -pressures.net_resultant_kn_per_m
    support_moment = -pressures.net_base_moment_kn_m_per_m
    area, _, _, _ = _weights(pool, internal_depth)
    return PoolCombinationResult(
        combination_id=f"{state}-{limit_state.lower()}-{purpose}",
        limit_state=limit_state,
        pool_state=state,
        purpose=purpose,
        factors=dict(factors),
        pressures=pressures,
        wall=wall,
        base=base,
        wall_force_balance_error_kn_per_m=(
            pressures.net_resultant_kn_per_m + support_horizontal
        ),
        wall_moment_balance_error_kn_m_per_m=(
            pressures.net_base_moment_kn_m_per_m + support_moment
        ),
        vertical_balance_error_kn=(
            base.downward_kn - base.uplift_kn - base.soil_reaction_kpa * area
        ),
    )


def _rc_capacity(
    *, thickness_mm: float, cover_mm: float, bar_diameter_mm: float, as_mm2: float,
    concrete_fc_mpa: float, concrete_ft_mpa: float, rebar_fy_mpa: float,
) -> tuple[float, float, float, float]:
    width = 1_000.0
    effective_depth = thickness_mm - cover_mm - bar_diameter_mm / 2.0
    compression_depth = rebar_fy_mpa * as_mm2 / (concrete_fc_mpa * width)
    effective_compression_depth = min(compression_depth, 0.45 * effective_depth)
    moment_capacity = (
        rebar_fy_mpa
        * as_mm2
        * (effective_depth - effective_compression_depth / 2.0)
        / 1.0e6
    )
    shear_capacity = 0.7 * concrete_ft_mpa * width * effective_depth / 1_000.0
    reinforcement_ratio = as_mm2 / (width * effective_depth)
    return moment_capacity, shear_capacity, reinforcement_ratio, effective_depth


def _crack_width(
    *, moment_kn_m: float, effective_depth_mm: float, as_mm2: float,
    cover_mm: float, bar_diameter_mm: float, rebar_es_mpa: float,
) -> float:
    steel_stress = moment_kn_m * 1.0e6 / max(0.87 * effective_depth_mm * as_mm2, 1.0e-9)
    reinforcement_ratio = max(as_mm2 / (1_000.0 * effective_depth_mm), 0.002)
    return (
        1.7
        * steel_stress
        / rebar_es_mpa
        * (1.9 * cover_mm + 0.08 * bar_diameter_mm / reinforcement_ratio)
    )


def _check(
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    combination_id: str,
    basis: str,
) -> PoolCheck:
    utilization = demand / max(capacity, 1.0e-12)
    return PoolCheck(
        name=name,
        demand=demand,
        capacity=capacity,
        unit=unit,
        utilization=utilization,
        passed=demand <= capacity,
        controlling_combination_id=combination_id,
        reference_basis=basis,
    )


def calculate_rectangular_pool(pool: RectangularPoolInput) -> PoolStructureResult:
    """Calculate a bounded rectangular pool model without publishing a professional status."""

    _validate(pool)
    service_factors = {
        "external_lateral": 1.0,
        "internal_water": 1.0,
        "permanent": 1.0,
        "uplift": 1.0,
    }
    factor_sets = (
        ("service", "SLS", service_factors),
        (
            "wall_external",
            "ULS",
            {"external_lateral": 1.35, "internal_water": 1.0, "permanent": 1.0, "uplift": 1.0},
        ),
        (
            "wall_internal",
            "ULS",
            {"external_lateral": 1.0, "internal_water": 1.35, "permanent": 1.0, "uplift": 1.0},
        ),
        (
            "gravity",
            "ULS",
            {"external_lateral": 1.0, "internal_water": 1.35, "permanent": 1.35, "uplift": 1.0},
        ),
        (
            "uplift",
            "ULS",
            {"external_lateral": 1.0, "internal_water": 1.0, "permanent": 1.0, "uplift": pool.antifloat_factor},
        ),
    )
    combinations = tuple(
        _combination(
            pool,
            state=state,
            purpose=purpose,  # type: ignore[arg-type]
            limit_state=limit_state,  # type: ignore[arg-type]
            factors=factors,
        )
        for state in ("empty", "full")
        for purpose, limit_state, factors in factor_sets
    )
    uls = [item for item in combinations if item.limit_state == "ULS"]
    sls = [item for item in combinations if item.limit_state == "SLS"]
    wall_vertical = max(uls, key=lambda item: item.wall.vertical_moment_kn_m_per_m)
    wall_horizontal = max(uls, key=lambda item: item.wall.horizontal_moment_kn_m_per_m)
    wall_vertical_sls = max(sls, key=lambda item: item.wall.vertical_moment_kn_m_per_m)
    wall_horizontal_sls = max(sls, key=lambda item: item.wall.horizontal_moment_kn_m_per_m)
    base_x = max(uls, key=lambda item: item.base.x_moment_kn_m_per_m)
    base_y = max(uls, key=lambda item: item.base.y_moment_kn_m_per_m)
    base_x_sls = max(sls, key=lambda item: item.base.x_moment_kn_m_per_m)
    base_y_sls = max(sls, key=lambda item: item.base.y_moment_kn_m_per_m)
    uplift = max(
        (item for item in uls if item.purpose == "uplift"),
        key=lambda item: item.base.uplift_kn / max(item.base.downward_kn, 1.0e-12),
    )
    bearing = max(sls, key=lambda item: item.base.soil_reaction_kpa)

    geometry = pool.geometry
    materials = pool.materials
    reinforcement = pool.reinforcement
    wall_v_cap, wall_shear_cap, wall_v_rho, wall_d = _rc_capacity(
        thickness_mm=geometry.wall_thickness_mm,
        cover_mm=reinforcement.wall_cover_mm,
        bar_diameter_mm=reinforcement.wall_bar_diameter_mm,
        as_mm2=reinforcement.wall_vertical_as_mm2_per_m,
        concrete_fc_mpa=materials.concrete_fc_mpa,
        concrete_ft_mpa=materials.concrete_ft_mpa,
        rebar_fy_mpa=materials.rebar_fy_mpa,
    )
    wall_h_cap, _, wall_h_rho, _ = _rc_capacity(
        thickness_mm=geometry.wall_thickness_mm,
        cover_mm=reinforcement.wall_cover_mm,
        bar_diameter_mm=reinforcement.wall_bar_diameter_mm,
        as_mm2=reinforcement.wall_horizontal_as_mm2_per_m,
        concrete_fc_mpa=materials.concrete_fc_mpa,
        concrete_ft_mpa=materials.concrete_ft_mpa,
        rebar_fy_mpa=materials.rebar_fy_mpa,
    )
    base_x_cap, base_shear_cap, base_x_rho, base_d = _rc_capacity(
        thickness_mm=geometry.base_thickness_mm,
        cover_mm=reinforcement.base_cover_mm,
        bar_diameter_mm=reinforcement.base_bar_diameter_mm,
        as_mm2=reinforcement.base_x_as_mm2_per_m,
        concrete_fc_mpa=materials.concrete_fc_mpa,
        concrete_ft_mpa=materials.concrete_ft_mpa,
        rebar_fy_mpa=materials.rebar_fy_mpa,
    )
    base_y_cap, _, base_y_rho, _ = _rc_capacity(
        thickness_mm=geometry.base_thickness_mm,
        cover_mm=reinforcement.base_cover_mm,
        bar_diameter_mm=reinforcement.base_bar_diameter_mm,
        as_mm2=reinforcement.base_y_as_mm2_per_m,
        concrete_fc_mpa=materials.concrete_fc_mpa,
        concrete_ft_mpa=materials.concrete_ft_mpa,
        rebar_fy_mpa=materials.rebar_fy_mpa,
    )
    checks = [
        _check("池壁竖向条带受弯", wall_vertical.wall.vertical_moment_kn_m_per_m, wall_v_cap, "kN*m/m", wall_vertical.combination_id, "竖向悬臂条带简化"),
        _check("池壁竖向条带受剪", wall_vertical.wall.vertical_shear_kn_per_m, wall_shear_cap, "kN/m", wall_vertical.combination_id, "1 m 宽混凝土条带受剪简化"),
        _check("池壁水平条带受弯", wall_horizontal.wall.horizontal_moment_kn_m_per_m, wall_h_cap, "kN*m/m", wall_horizontal.combination_id, "两侧简支水平条带简化"),
        _check("池壁水平条带受剪", wall_horizontal.wall.horizontal_shear_kn_per_m, wall_shear_cap, "kN/m", wall_horizontal.combination_id, "两侧简支水平条带简化"),
        _check("池壁竖向最小配筋", reinforcement.minimum_reinforcement_ratio, wall_v_rho, "1", wall_vertical.combination_id, "双向每米条带配筋率"),
        _check("池壁水平最小配筋", reinforcement.minimum_reinforcement_ratio, wall_h_rho, "1", wall_horizontal.combination_id, "双向每米条带配筋率"),
        _check(
            "池壁竖向裂缝宽度",
            _crack_width(moment_kn_m=wall_vertical_sls.wall.vertical_moment_kn_m_per_m, effective_depth_mm=wall_d, as_mm2=reinforcement.wall_vertical_as_mm2_per_m, cover_mm=reinforcement.wall_cover_mm, bar_diameter_mm=reinforcement.wall_bar_diameter_mm, rebar_es_mpa=materials.rebar_es_mpa),
            reinforcement.crack_width_limit_mm,
            "mm",
            wall_vertical_sls.combination_id,
            "弹性钢筋应力裂缝宽度简化",
        ),
        _check(
            "池壁水平裂缝宽度",
            _crack_width(moment_kn_m=wall_horizontal_sls.wall.horizontal_moment_kn_m_per_m, effective_depth_mm=wall_d, as_mm2=reinforcement.wall_horizontal_as_mm2_per_m, cover_mm=reinforcement.wall_cover_mm, bar_diameter_mm=reinforcement.wall_bar_diameter_mm, rebar_es_mpa=materials.rebar_es_mpa),
            reinforcement.crack_width_limit_mm,
            "mm",
            wall_horizontal_sls.combination_id,
            "弹性钢筋应力裂缝宽度简化",
        ),
        _check("底板 X 向受弯", base_x.base.x_moment_kn_m_per_m, base_x_cap, "kN*m/m", base_x.combination_id, "四边支承双向分配简化"),
        _check("底板 Y 向受弯", base_y.base.y_moment_kn_m_per_m, base_y_cap, "kN*m/m", base_y.combination_id, "四边支承双向分配简化"),
        _check("底板 X 向受剪", base_x.base.x_shear_kn_per_m, base_shear_cap, "kN/m", base_x.combination_id, "1 m 宽底板条带受剪简化"),
        _check("底板 Y 向受剪", base_y.base.y_shear_kn_per_m, base_shear_cap, "kN/m", base_y.combination_id, "1 m 宽底板条带受剪简化"),
        _check("底板 X 向最小配筋", reinforcement.minimum_reinforcement_ratio, base_x_rho, "1", base_x.combination_id, "每米底板条带配筋率"),
        _check("底板 Y 向最小配筋", reinforcement.minimum_reinforcement_ratio, base_y_rho, "1", base_y.combination_id, "每米底板条带配筋率"),
        _check(
            "底板 X 向裂缝宽度",
            _crack_width(moment_kn_m=base_x_sls.base.x_moment_kn_m_per_m, effective_depth_mm=base_d, as_mm2=reinforcement.base_x_as_mm2_per_m, cover_mm=reinforcement.base_cover_mm, bar_diameter_mm=reinforcement.base_bar_diameter_mm, rebar_es_mpa=materials.rebar_es_mpa),
            reinforcement.crack_width_limit_mm,
            "mm",
            base_x_sls.combination_id,
            "弹性钢筋应力裂缝宽度简化",
        ),
        _check(
            "底板 Y 向裂缝宽度",
            _crack_width(moment_kn_m=base_y_sls.base.y_moment_kn_m_per_m, effective_depth_mm=base_d, as_mm2=reinforcement.base_y_as_mm2_per_m, cover_mm=reinforcement.base_cover_mm, bar_diameter_mm=reinforcement.base_bar_diameter_mm, rebar_es_mpa=materials.rebar_es_mpa),
            reinforcement.crack_width_limit_mm,
            "mm",
            base_y_sls.combination_id,
            "弹性钢筋应力裂缝宽度简化",
        ),
        _check("抗浮稳定", uplift.base.uplift_kn, uplift.base.downward_kn, "kN", uplift.combination_id, "地下水浮力乘抗浮系数与永久重量平衡"),
        _check("地基承载力", bearing.base.soil_reaction_kpa, materials.allowable_bearing_kpa, "kPa", bearing.combination_id, "均匀地基、中心受压"),
    ]
    governing = max(checks, key=lambda item: item.utilization)
    return PoolStructureResult(
        combinations=combinations,
        checks=tuple(checks),
        governing_check=governing.name,
        governing_utilization=governing.utilization,
        verification_status="unverified",
        assumptions=(
            "矩形直墙池体，池壁与底板整体连接；墙体分别按竖向悬臂和水平简支条带筛查。",
            "底板按均匀地基反力及四边支承双向荷载分配简化，不考虑局部集中反力。",
            "主动土压力采用水平填土、单一土层 Rankine 模型；不计被动土压力。",
        ),
        applicability=(
            "矩形、直墙、规则池体",
            "均匀地基与中心竖向作用",
            "静水压力、单一土层主动土压力和地下水浮力",
        ),
    )


__all__ = [
    "BaseSlabDemand",
    "LateralPressureComponents",
    "PoolCheck",
    "PoolCombinationResult",
    "PoolMaterials",
    "PoolReinforcement",
    "PoolStructureResult",
    "PoolWaterLevels",
    "RectangularPoolGeometry",
    "RectangularPoolInput",
    "WallStripDemand",
    "calculate_rectangular_pool",
]
