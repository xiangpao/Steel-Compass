"""Independent mechanics references for the existing steel and timber modules.

This module deliberately imports no production code.  It provides bounded,
closed-form checks for verification tests; it is not a parallel design engine
and does not promote any module to ``independently_verified``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, pi, sqrt
from typing import Literal


@dataclass(frozen=True)
class SectionReference:
    area_mm2: float
    ix_mm4: float
    iy_mm4: float
    wx_mm3: float
    wy_mm3: float
    rx_mm: float
    ry_mm: float
    shear_area_mm2: float


@dataclass(frozen=True)
class BeamReference:
    reaction_left_kn: float
    reaction_right_kn: float
    maximum_shear_kn: float
    maximum_moment_kn_m: float
    maximum_deflection_mm: float
    bending_capacity_kn_m: float
    shear_capacity_kn: float


@dataclass(frozen=True)
class ColumnReference:
    slenderness: float
    stability_factor: float
    axial_capacity_kn: float
    moment_capacity_kn_m: float
    interaction: float


@dataclass(frozen=True)
class PortalEquilibriumReference:
    total_vertical_load_kn: float
    reaction_left_kn: float
    reaction_right_kn: float
    total_horizontal_reaction_kn: float


@dataclass(frozen=True)
class BaseplateReference:
    bearing_pressure_mpa: float
    plate_stress_mpa: float
    anchor_tension_each_kn: float
    anchor_shear_each_kn: float
    anchor_interaction: float
    weld_demand_kn: float
    weld_capacity_kn: float


@dataclass(frozen=True)
class CantileverPostReference:
    shear_kn: float
    moment_kn_m: float
    torsion_kn_m: float


def _positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def solve_hollow_rect_section(
    *, depth_mm: float, width_mm: float, thickness_mm: float
) -> SectionReference:
    """Exact sharp-corner RHS/SHS properties used by the bounded references."""

    _positive("depth_mm", depth_mm)
    _positive("width_mm", width_mm)
    _positive("thickness_mm", thickness_mm)
    if 2 * thickness_mm >= min(depth_mm, width_mm):
        raise ValueError("hollow section wall is not geometrically valid")
    inner_depth = depth_mm - 2 * thickness_mm
    inner_width = width_mm - 2 * thickness_mm
    area = width_mm * depth_mm - inner_width * inner_depth
    ix = (width_mm * depth_mm**3 - inner_width * inner_depth**3) / 12
    iy = (depth_mm * width_mm**3 - inner_depth * inner_width**3) / 12
    return SectionReference(
        area_mm2=area,
        ix_mm4=ix,
        iy_mm4=iy,
        wx_mm3=ix / (depth_mm / 2),
        wy_mm3=iy / (width_mm / 2),
        rx_mm=sqrt(ix / area),
        ry_mm=sqrt(iy / area),
        shear_area_mm2=2 * thickness_mm * inner_depth,
    )


def solve_udl_beam(
    *,
    support: Literal["simple", "cantilever"],
    uls_line_load_kn_m: float,
    sls_line_load_kn_m: float,
    span_m: float,
    elastic_modulus_mpa: float,
    inertia_mm4: float,
    section_modulus_mm3: float,
    shear_area_mm2: float,
    bending_strength_mpa: float,
    shear_strength_mpa: float,
) -> BeamReference:
    for name, value in (
        ("span_m", span_m),
        ("elastic_modulus_mpa", elastic_modulus_mpa),
        ("inertia_mm4", inertia_mm4),
        ("section_modulus_mm3", section_modulus_mm3),
        ("shear_area_mm2", shear_area_mm2),
        ("bending_strength_mpa", bending_strength_mpa),
        ("shear_strength_mpa", shear_strength_mpa),
    ):
        _positive(name, value)
    if uls_line_load_kn_m < 0 or sls_line_load_kn_m < 0:
        raise ValueError("reference line loads must be non-negative magnitudes")
    length_mm = span_m * 1000
    if support == "simple":
        reaction = sls_line_load_kn_m * span_m / 2
        shear = uls_line_load_kn_m * span_m / 2
        moment = uls_line_load_kn_m * span_m**2 / 8
        deflection = (
            5
            * sls_line_load_kn_m
            * length_mm**4
            / (384 * elastic_modulus_mpa * inertia_mm4)
        )
        left, right = reaction, reaction
    else:
        left = sls_line_load_kn_m * span_m
        right = 0.0
        shear = uls_line_load_kn_m * span_m
        moment = uls_line_load_kn_m * span_m**2 / 2
        deflection = (
            sls_line_load_kn_m
            * length_mm**4
            / (8 * elastic_modulus_mpa * inertia_mm4)
        )
    return BeamReference(
        reaction_left_kn=left,
        reaction_right_kn=right,
        maximum_shear_kn=shear,
        maximum_moment_kn_m=moment,
        maximum_deflection_mm=deflection,
        bending_capacity_kn_m=bending_strength_mpa * section_modulus_mm3 / 1e6,
        shear_capacity_kn=shear_strength_mpa * shear_area_mm2 / 1000,
    )


def solve_steel_column(
    *,
    axial_kn: float,
    moment_kn_m: float,
    height_m: float,
    effective_length_factor: float,
    area_mm2: float,
    minimum_radius_mm: float,
    section_modulus_mm3: float,
    design_strength_mpa: float,
    yield_strength_mpa: float,
    elastic_modulus_mpa: float = 206_000.0,
) -> ColumnReference:
    for name, value in (
        ("height_m", height_m),
        ("effective_length_factor", effective_length_factor),
        ("area_mm2", area_mm2),
        ("minimum_radius_mm", minimum_radius_mm),
        ("section_modulus_mm3", section_modulus_mm3),
        ("design_strength_mpa", design_strength_mpa),
        ("yield_strength_mpa", yield_strength_mpa),
        ("elastic_modulus_mpa", elastic_modulus_mpa),
    ):
        _positive(name, value)
    if axial_kn < 0 or moment_kn_m < 0:
        raise ValueError("column action magnitudes must be non-negative")
    slenderness = height_m * 1000 * effective_length_factor / minimum_radius_mm
    lambda_bar = slenderness / pi * sqrt(yield_strength_mpa / elastic_modulus_mpa)
    if lambda_bar <= 0.215:
        phi = max(0.0, 1.0 - 0.65 * lambda_bar**2)
    else:
        alpha2, alpha3 = 0.965, 0.300
        value = (alpha2 + alpha3 * lambda_bar + lambda_bar**2) / 2
        phi = 1 / (value + sqrt(max(value**2 - lambda_bar**2, 0.0)))
    axial_capacity = phi * area_mm2 * design_strength_mpa / 1000
    moment_capacity = design_strength_mpa * section_modulus_mm3 / 1e6
    return ColumnReference(
        slenderness=slenderness,
        stability_factor=phi,
        axial_capacity_kn=axial_capacity,
        moment_capacity_kn_m=moment_capacity,
        interaction=axial_kn / axial_capacity + moment_kn_m / moment_capacity,
    )


def solve_timber_column(
    *,
    axial_kn: float,
    width_mm: float,
    depth_mm: float,
    height_m: float,
    effective_length_factor: float,
    elastic_modulus_mpa: float,
    compression_strength_mpa: float,
) -> ColumnReference:
    for name, value in (
        ("width_mm", width_mm),
        ("depth_mm", depth_mm),
        ("height_m", height_m),
        ("effective_length_factor", effective_length_factor),
        ("elastic_modulus_mpa", elastic_modulus_mpa),
        ("compression_strength_mpa", compression_strength_mpa),
    ):
        _positive(name, value)
    if axial_kn < 0:
        raise ValueError("axial_kn must be a non-negative magnitude")
    area = width_mm * depth_mm
    minimum_radius = min(width_mm, depth_mm) / sqrt(12)
    effective_length_mm = height_m * 1000 * effective_length_factor
    minimum_inertia = min(
        depth_mm * width_mm**3, width_mm * depth_mm**3
    ) / 12
    euler_kn = pi**2 * elastic_modulus_mpa * minimum_inertia / effective_length_mm**2 / 1000
    material_capacity = compression_strength_mpa * area / 1000
    capacity = min(euler_kn / 1.8, material_capacity)
    return ColumnReference(
        slenderness=effective_length_mm / minimum_radius,
        stability_factor=capacity / material_capacity,
        axial_capacity_kn=capacity,
        moment_capacity_kn_m=0.0,
        interaction=axial_kn / capacity,
    )


def solve_symmetric_portal_equilibrium(
    *, line_load_kn_m: float, span_m: float, horizontal_force_kn: float = 0.0
) -> PortalEquilibriumReference:
    if line_load_kn_m < 0:
        raise ValueError("line_load_kn_m must be non-negative")
    _positive("span_m", span_m)
    total = line_load_kn_m * span_m
    return PortalEquilibriumReference(
        total_vertical_load_kn=total,
        reaction_left_kn=total / 2,
        reaction_right_kn=total / 2,
        total_horizontal_reaction_kn=-horizontal_force_kn,
    )


def solve_baseplate_anchor(
    *,
    axial_kn: float,
    shear_x_kn: float,
    shear_y_kn: float,
    moment_x_kn_m: float,
    moment_y_kn_m: float,
    plate_length_mm: float,
    plate_width_mm: float,
    plate_thickness_mm: float,
    column_depth_mm: float,
    column_width_mm: float,
    anchor_count: int,
    anchor_diameter_mm: float,
    anchor_spacing_mm: float,
    anchor_fu_mpa: float,
    plate_design_strength_mpa: float,
    weld_throat_mm: float,
    weld_shear_strength_mpa: float,
) -> BaseplateReference:
    for name, value in (
        ("plate_length_mm", plate_length_mm),
        ("plate_width_mm", plate_width_mm),
        ("plate_thickness_mm", plate_thickness_mm),
        ("column_depth_mm", column_depth_mm),
        ("column_width_mm", column_width_mm),
        ("anchor_diameter_mm", anchor_diameter_mm),
        ("anchor_spacing_mm", anchor_spacing_mm),
        ("anchor_fu_mpa", anchor_fu_mpa),
        ("plate_design_strength_mpa", plate_design_strength_mpa),
        ("weld_throat_mm", weld_throat_mm),
        ("weld_shear_strength_mpa", weld_shear_strength_mpa),
    ):
        _positive(name, value)
    if anchor_count < 4 or anchor_count % 2:
        raise ValueError("anchor_count must be even and at least four")
    if plate_length_mm <= column_depth_mm or plate_width_mm <= column_width_mm:
        raise ValueError("baseplate must project beyond the column")
    plate_area = plate_length_mm * plate_width_mm
    compression = max(axial_kn, 0.0)
    uplift = max(-axial_kn, 0.0)
    pressure = compression * 1000 / plate_area
    projection = max(
        (plate_length_mm - column_depth_mm) / 2,
        (plate_width_mm - column_width_mm) / 2,
    )
    plate_stress = 3 * pressure * projection**2 / plate_thickness_mm**2
    resultant_shear = hypot(shear_x_kn, shear_y_kn)
    resultant_moment = hypot(moment_x_kn_m, moment_y_kn_m)
    lever_arm_m = anchor_spacing_mm / 1000
    raw_anchor_tension = uplift + max(
        resultant_moment / lever_arm_m - compression / 2, 0.0
    )
    total_anchor_tension = raw_anchor_tension * 1.25
    tension_each = total_anchor_tension / (anchor_count / 2)
    shear_each = resultant_shear / anchor_count
    anchor_area = pi * anchor_diameter_mm**2 / 4
    tension_capacity = 0.65 * anchor_fu_mpa * anchor_area / 1000
    shear_capacity = 0.40 * anchor_fu_mpa * anchor_area / 1000
    interaction = sqrt(
        (tension_each / tension_capacity) ** 2
        + (shear_each / shear_capacity) ** 2
    )
    weld_length = 2 * (column_depth_mm + column_width_mm)
    weld_capacity = weld_length * weld_throat_mm * weld_shear_strength_mpa / 1000
    weld_demand = hypot(resultant_shear, resultant_moment / 0.1)
    return BaseplateReference(
        bearing_pressure_mpa=pressure,
        plate_stress_mpa=plate_stress,
        anchor_tension_each_kn=tension_each,
        anchor_shear_each_kn=shear_each,
        anchor_interaction=interaction,
        weld_demand_kn=weld_demand,
        weld_capacity_kn=weld_capacity,
    )


def solve_cantilever_post(
    *, force_kn: float, lever_arm_m: float, eccentricity_m: float = 0.0
) -> CantileverPostReference:
    if force_kn < 0 or lever_arm_m < 0 or abs(eccentricity_m) > 5:
        raise ValueError("post inputs are outside the bounded reference domain")
    return CantileverPostReference(
        shear_kn=force_kn,
        moment_kn_m=force_kn * lever_arm_m + abs(force_kn * eccentricity_m),
        torsion_kn_m=force_kn * eccentricity_m,
    )


def screening_passes(*, demand: float, capacity: float) -> bool:
    """Shared exact-boundary oracle for 0.99/1.01 conclusion tests."""

    if demand < 0 or capacity <= 0:
        raise ValueError("screening inputs are outside the bounded domain")
    return demand <= capacity
