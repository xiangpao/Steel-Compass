"""Independent references for current RC, wall and foundation screeners.

This module deliberately imports nothing from :mod:`app.core`.  The functions
are bounded, closed-form mechanics checks used to detect accidental changes in
the production implementation.  They are not a substitute for clause-by-clause
code review and do not promote any production module to ``independently_verified``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, radians, sqrt, tan


def _positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def threshold_passes(*, demand: float, capacity: float) -> bool:
    """Return the exact pass/fail convention used by the evidence fixtures."""

    if demand < 0 or capacity <= 0:
        raise ValueError("threshold inputs outside the bounded reference domain")
    return demand <= capacity


@dataclass(frozen=True)
class SimpleSpanActions:
    line_load_kn_m: float
    reaction_kn: float
    shear_kn: float
    moment_kn_m: float


def simple_span_udl(*, line_load_kn_m: float, span_m: float) -> SimpleSpanActions:
    if line_load_kn_m < 0:
        raise ValueError("line_load_kn_m must be non-negative")
    _positive("span_m", span_m)
    reaction = line_load_kn_m * span_m / 2.0
    return SimpleSpanActions(
        line_load_kn_m=line_load_kn_m,
        reaction_kn=reaction,
        shear_kn=reaction,
        moment_kn_m=line_load_kn_m * span_m**2 / 8.0,
    )


@dataclass(frozen=True)
class RCFlexureReference:
    steel_area_mm2: float
    neutral_axis_mm: float
    limiting_axis_mm: float
    moment_capacity_kn_m: float
    reinforcement_ratio: float


def rc_rectangular_flexure(
    *,
    width_mm: float,
    effective_depth_mm: float,
    steel_area_mm2: float,
    concrete_design_strength_mpa: float,
    steel_design_strength_mpa: float,
    limiting_axis_ratio: float,
) -> RCFlexureReference:
    for name, value in (
        ("width_mm", width_mm),
        ("effective_depth_mm", effective_depth_mm),
        ("steel_area_mm2", steel_area_mm2),
        ("concrete_design_strength_mpa", concrete_design_strength_mpa),
        ("steel_design_strength_mpa", steel_design_strength_mpa),
        ("limiting_axis_ratio", limiting_axis_ratio),
    ):
        _positive(name, value)
    neutral_axis = steel_design_strength_mpa * steel_area_mm2 / (
        concrete_design_strength_mpa * width_mm
    )
    limiting_axis = limiting_axis_ratio * effective_depth_mm
    effective_axis = min(neutral_axis, limiting_axis)
    capacity = (
        steel_design_strength_mpa
        * steel_area_mm2
        * (effective_depth_mm - effective_axis / 2.0)
        / 1e6
    )
    return RCFlexureReference(
        steel_area_mm2=steel_area_mm2,
        neutral_axis_mm=neutral_axis,
        limiting_axis_mm=limiting_axis,
        moment_capacity_kn_m=capacity,
        reinforcement_ratio=steel_area_mm2 / (width_mm * effective_depth_mm),
    )


def bar_area(*, diameter_mm: float, count: float = 1.0) -> float:
    _positive("diameter_mm", diameter_mm)
    _positive("count", count)
    return count * pi * diameter_mm**2 / 4.0


@dataclass(frozen=True)
class RCColumnReference:
    gross_area_mm2: float
    radius_of_gyration_mm: float
    slenderness: float
    stability_factor: float
    axial_capacity_kn: float
    moment_capacity_kn_m: float
    interaction: float


def rc_rectangular_column(
    *,
    width_mm: float,
    depth_mm: float,
    height_m: float,
    effective_length_factor: float,
    steel_area_mm2: float,
    concrete_design_strength_mpa: float,
    steel_design_strength_mpa: float,
    axial_demand_kn: float,
    moment_demand_kn_m: float,
) -> RCColumnReference:
    for name, value in (
        ("width_mm", width_mm),
        ("depth_mm", depth_mm),
        ("height_m", height_m),
        ("effective_length_factor", effective_length_factor),
        ("steel_area_mm2", steel_area_mm2),
        ("concrete_design_strength_mpa", concrete_design_strength_mpa),
        ("steel_design_strength_mpa", steel_design_strength_mpa),
    ):
        _positive(name, value)
    if axial_demand_kn < 0 or moment_demand_kn_m < 0:
        raise ValueError("column demands must be non-negative")
    gross_area = width_mm * depth_mm
    if steel_area_mm2 >= gross_area:
        raise ValueError("steel area must be smaller than gross area")
    radius = min(width_mm, depth_mm) / sqrt(12.0)
    slenderness = height_m * 1000.0 * effective_length_factor / radius
    stability = max(0.65, min(1.0, 1.0 - max(slenderness - 20.0, 0.0) / 300.0))
    concrete_area = gross_area - steel_area_mm2
    axial_capacity = (
        0.9
        * stability
        * (
            concrete_design_strength_mpa * concrete_area
            + steel_design_strength_mpa * steel_area_mm2
        )
        / 1000.0
    )
    lever_arm = 0.4 * depth_mm
    moment_capacity = (
        0.8 * steel_design_strength_mpa * steel_area_mm2 * lever_arm / 1e6
    )
    return RCColumnReference(
        gross_area_mm2=gross_area,
        radius_of_gyration_mm=radius,
        slenderness=slenderness,
        stability_factor=stability,
        axial_capacity_kn=axial_capacity,
        moment_capacity_kn_m=moment_capacity,
        interaction=axial_demand_kn / axial_capacity
        + moment_demand_kn_m / moment_capacity,
    )


@dataclass(frozen=True)
class MasonryWallReference:
    line_load_kn_m: float
    shear_kn: float
    moment_kn_m: float
    bending_stress_mpa: float


def masonry_wall_strip(
    *, pressure_kpa: float, height_m: float, support_spacing_m: float, thickness_mm: float
) -> MasonryWallReference:
    if pressure_kpa < 0:
        raise ValueError("pressure_kpa must be non-negative")
    for name, value in (
        ("height_m", height_m),
        ("support_spacing_m", support_spacing_m),
        ("thickness_mm", thickness_mm),
    ):
        _positive(name, value)
    line_load = pressure_kpa * height_m
    moment = line_load * support_spacing_m**2 / 8.0
    shear = line_load * support_spacing_m / 2.0
    section_modulus = 1000.0 * thickness_mm**2 / 6.0
    return MasonryWallReference(
        line_load_kn_m=line_load,
        shear_kn=shear,
        moment_kn_m=moment,
        bending_stress_mpa=moment * 1e6 / section_modulus,
    )


def rankine_active_coefficient(*, friction_angle_deg: float) -> float:
    if not 0.0 < friction_angle_deg < 60.0:
        raise ValueError("friction angle outside the bounded reference domain")
    return tan(radians(45.0 - friction_angle_deg / 2.0)) ** 2


@dataclass(frozen=True)
class RCWallReference:
    active_coefficient: float
    horizontal_force_kn_m: float
    base_moment_kn_m_m: float
    steel_area_mm2_m: float
    flexural_capacity_kn_m_m: float
    shear_capacity_kn: float


def rc_wall_cantilever(
    *,
    wind_pressure_kpa: float,
    wall_height_m: float,
    wall_thickness_mm: float,
    strip_width_m: float,
    bar_diameter_mm: float,
    bar_spacing_mm: float,
    soil_height_m: float = 0.0,
    soil_unit_weight_kn_m3: float = 18.0,
    friction_angle_deg: float = 30.0,
    surcharge_kpa: float = 0.0,
) -> RCWallReference:
    if wind_pressure_kpa < 0 or surcharge_kpa < 0:
        raise ValueError("wall pressures must be non-negative")
    for name, value in (
        ("wall_height_m", wall_height_m),
        ("wall_thickness_mm", wall_thickness_mm),
        ("strip_width_m", strip_width_m),
        ("bar_diameter_mm", bar_diameter_mm),
        ("bar_spacing_mm", bar_spacing_mm),
        ("soil_unit_weight_kn_m3", soil_unit_weight_kn_m3),
    ):
        _positive(name, value)
    if not 0.0 <= soil_height_m <= wall_height_m:
        raise ValueError("soil height outside the wall")
    coefficient = rankine_active_coefficient(friction_angle_deg=friction_angle_deg)
    soil_force = 0.5 * coefficient * soil_unit_weight_kn_m3 * soil_height_m**2
    soil_force += coefficient * surcharge_kpa * soil_height_m
    soil_moment = (
        0.5 * coefficient * soil_unit_weight_kn_m3 * soil_height_m**3 / 3.0
        + coefficient * surcharge_kpa * soil_height_m**2 / 2.0
    )
    wind_force = wind_pressure_kpa * wall_height_m
    steel_area = 1000.0 / bar_spacing_mm * bar_area(diameter_mm=bar_diameter_mm)
    return RCWallReference(
        active_coefficient=coefficient,
        horizontal_force_kn_m=wind_force + soil_force,
        base_moment_kn_m_m=wind_pressure_kpa * wall_height_m**2 / 2.0
        + soil_moment,
        steel_area_mm2_m=steel_area,
        flexural_capacity_kn_m_m=360.0
        * steel_area
        * (0.85 * wall_thickness_mm)
        / 1e6,
        shear_capacity_kn=0.7
        * 1.43
        * strip_width_m
        * wall_thickness_mm
        / 1000.0,
    )


@dataclass(frozen=True)
class EffectiveFoundationWeight:
    footing_kn: float
    cover_kn: float
    displaced_water_kn: float


def effective_foundation_weight(
    *,
    plan_area_m2: float,
    thickness_m: float,
    embedment_m: float,
    soil_cover_m: float,
    groundwater_depth_m: float | None,
) -> EffectiveFoundationWeight:
    for name, value in (
        ("plan_area_m2", plan_area_m2),
        ("thickness_m", thickness_m),
    ):
        _positive(name, value)
    if embedment_m < 0 or soil_cover_m < 0:
        raise ValueError("foundation depth inputs must be non-negative")
    if groundwater_depth_m is not None and groundwater_depth_m < 0:
        raise ValueError("groundwater depth must be non-negative")
    submerged_footing = 0.0
    submerged_cover = 0.0
    if groundwater_depth_m is not None:
        submerged_footing = max(
            0.0, min(thickness_m, embedment_m - groundwater_depth_m)
        )
        submerged_cover = max(
            0.0, min(soil_cover_m, soil_cover_m - groundwater_depth_m)
        )
    displaced = plan_area_m2 * (submerged_footing + submerged_cover) * 10.0
    return EffectiveFoundationWeight(
        footing_kn=plan_area_m2 * thickness_m * 25.0
        - plan_area_m2 * submerged_footing * 10.0,
        cover_kn=plan_area_m2 * soil_cover_m * 18.0
        - plan_area_m2 * submerged_cover * 10.0,
        displaced_water_kn=displaced,
    )


@dataclass(frozen=True)
class SpreadFootingReference:
    service_vertical_kn: float
    average_pressure_kpa: float
    maximum_pressure_kpa: float
    minimum_pressure_kpa: float
    punching_perimeter_mm: float


def spread_footing_pressure(
    *,
    service_column_load_kn: float,
    footing_weight_kn: float,
    length_m: float,
    width_m: float,
    moment_x_kn_m: float,
    moment_y_kn_m: float,
    column_x_mm: float,
    column_y_mm: float,
    effective_depth_mm: float,
) -> SpreadFootingReference:
    for name, value in (
        ("length_m", length_m),
        ("width_m", width_m),
        ("column_x_mm", column_x_mm),
        ("column_y_mm", column_y_mm),
        ("effective_depth_mm", effective_depth_mm),
    ):
        _positive(name, value)
    vertical = service_column_load_kn + footing_weight_kn
    if vertical <= 0:
        raise ValueError("net service vertical must be positive")
    area = length_m * width_m
    average = vertical / area
    ex = abs(moment_y_kn_m) / vertical
    ey = abs(moment_x_kn_m) / vertical
    maximum = average * (1.0 + 6.0 * ex / length_m + 6.0 * ey / width_m)
    minimum = average * (1.0 - 6.0 * ex / length_m - 6.0 * ey / width_m)
    perimeter = 2.0 * (column_x_mm + column_y_mm + 2.0 * effective_depth_mm)
    return SpreadFootingReference(
        service_vertical_kn=vertical,
        average_pressure_kpa=average,
        maximum_pressure_kpa=maximum,
        minimum_pressure_kpa=minimum,
        punching_perimeter_mm=perimeter,
    )


@dataclass(frozen=True)
class StripFootingReference:
    service_vertical_kn_m: float
    eccentricity_m: float
    left_pressure_kpa: float
    right_pressure_kpa: float


def strip_footing_pressure(
    *,
    service_wall_load_kn_m: float,
    footing_weight_kn_m: float,
    width_m: float,
    applied_moment_kn_m_m: float,
    wall_eccentricity_mm: float,
) -> StripFootingReference:
    _positive("width_m", width_m)
    vertical = service_wall_load_kn_m + footing_weight_kn_m
    if vertical <= 0:
        raise ValueError("net service vertical must be positive")
    total_moment = applied_moment_kn_m_m + vertical * wall_eccentricity_mm / 1000.0
    eccentricity = total_moment / vertical
    average = vertical / width_m
    return StripFootingReference(
        service_vertical_kn_m=vertical,
        eccentricity_m=eccentricity,
        left_pressure_kpa=average * (1.0 - 6.0 * eccentricity / width_m),
        right_pressure_kpa=average * (1.0 + 6.0 * eccentricity / width_m),
    )


@dataclass(frozen=True)
class RetainingWallReference:
    active_coefficient: float
    earth_force_kn_m: float
    water_force_kn_m: float
    horizontal_force_kn_m: float
    overturning_moment_kn_m_m: float
    vertical_force_kn_m: float
    maximum_pressure_kpa: float
    minimum_pressure_kpa: float


def cantilever_retaining_wall(
    *,
    retained_height_m: float,
    stem_thickness_m: float,
    base_width_m: float,
    toe_length_m: float,
    base_thickness_m: float,
    soil_unit_weight_kn_m3: float,
    friction_angle_deg: float,
    surcharge_kpa: float,
    water_depth_m: float,
) -> RetainingWallReference:
    for name, value in (
        ("retained_height_m", retained_height_m),
        ("stem_thickness_m", stem_thickness_m),
        ("base_width_m", base_width_m),
        ("toe_length_m", toe_length_m),
        ("base_thickness_m", base_thickness_m),
        ("soil_unit_weight_kn_m3", soil_unit_weight_kn_m3),
    ):
        _positive(name, value)
    if surcharge_kpa < 0 or not 0.0 <= water_depth_m <= retained_height_m:
        raise ValueError("retaining pressure inputs outside the bounded domain")
    heel = max(base_width_m - toe_length_m - stem_thickness_m, 0.1)
    coefficient = rankine_active_coefficient(friction_angle_deg=friction_angle_deg)
    triangular_earth = (
        0.5 * coefficient * soil_unit_weight_kn_m3 * retained_height_m**2
    )
    surcharge_earth = coefficient * surcharge_kpa * retained_height_m
    earth = triangular_earth + surcharge_earth
    earth_moment = triangular_earth * retained_height_m / 3.0
    earth_moment += surcharge_earth * retained_height_m / 2.0
    # The current bounded project convention rounds water unit weight to
    # 10 kN/m3; the evidence record makes this assumption explicit.
    water = 0.5 * 10.0 * water_depth_m**2
    water_moment = water * water_depth_m / 3.0
    concrete = (
        stem_thickness_m * retained_height_m
        + base_width_m * base_thickness_m
    ) * 25.0
    soil_over_heel = heel * retained_height_m * soil_unit_weight_kn_m3
    vertical = concrete + soil_over_heel
    overturn = earth_moment + water_moment
    average = vertical / base_width_m
    eccentricity = (
        overturn - vertical * (base_width_m / 2.0 - toe_length_m)
    ) / vertical
    return RetainingWallReference(
        active_coefficient=coefficient,
        earth_force_kn_m=earth,
        water_force_kn_m=water,
        horizontal_force_kn_m=earth + water,
        overturning_moment_kn_m_m=overturn,
        vertical_force_kn_m=vertical,
        maximum_pressure_kpa=average * (1.0 + 6.0 * eccentricity / base_width_m),
        minimum_pressure_kpa=average * (1.0 - 6.0 * eccentricity / base_width_m),
    )
