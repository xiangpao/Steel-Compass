"""Independent closed-form references for the 3.1 scene screeners.

The functions in this file intentionally have no imports from ``app.core``.
They are small mechanics checks for the supported quick-estimate domains, not
alternative Chinese-code design implementations and not a reason to promote a
module to ``independently_verified``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import radians, tan


@dataclass(frozen=True)
class SimplySupportedReference:
    reaction_kn: float
    shear_kn: float
    moment_kn_m: float
    deflection_mm: float


def solve_simply_supported_udl(
    *,
    line_load_kn_m: float,
    span_m: float,
    elastic_modulus_mpa: float,
    inertia_mm4: float,
) -> SimplySupportedReference:
    """Return the closed-form UDL response for one simply supported span."""

    if line_load_kn_m < 0 or span_m <= 0 or elastic_modulus_mpa <= 0 or inertia_mm4 <= 0:
        raise ValueError("inputs outside the bounded reference domain")
    span_mm = span_m * 1000.0
    reaction = line_load_kn_m * span_m / 2.0
    moment = line_load_kn_m * span_m**2 / 8.0
    deflection = 5.0 * line_load_kn_m * span_mm**4 / (
        384.0 * elastic_modulus_mpa * inertia_mm4
    )
    return SimplySupportedReference(reaction, reaction, moment, deflection)


@dataclass(frozen=True)
class CantileverPostReference:
    shear_kn: float
    moment_kn_m: float
    torsion_kn_m: float


def solve_cantilever_post(*, force_kn: float, lever_arm_m: float, eccentricity_m: float = 0.0) -> CantileverPostReference:
    if force_kn < 0 or lever_arm_m < 0 or abs(eccentricity_m) > 20:
        raise ValueError("inputs outside the bounded reference domain")
    return CantileverPostReference(
        shear_kn=force_kn,
        moment_kn_m=force_kn * lever_arm_m + abs(force_kn * eccentricity_m),
        torsion_kn_m=force_kn * eccentricity_m,
    )


@dataclass(frozen=True)
class WallStripReference:
    line_load_kn_m: float
    shear_kn: float
    moment_kn_m: float


def solve_wall_strip(*, pressure_kpa: float, height_m: float, span_m: float = 1.0) -> WallStripReference:
    if pressure_kpa < 0 or height_m <= 0 or span_m <= 0:
        raise ValueError("inputs outside the bounded reference domain")
    line_load = pressure_kpa * height_m
    return WallStripReference(
        line_load_kn_m=line_load,
        shear_kn=line_load * span_m / 2.0,
        moment_kn_m=line_load * span_m**2 / 8.0,
    )


def solve_rc_wall_cantilever(*, pressure_kpa: float, height_m: float) -> WallStripReference:
    if pressure_kpa < 0 or height_m <= 0:
        raise ValueError("inputs outside the bounded reference domain")
    line_load = pressure_kpa * height_m
    return WallStripReference(
        line_load_kn_m=line_load,
        shear_kn=line_load,
        moment_kn_m=pressure_kpa * height_m**2 / 2.0,
    )


def solve_rc_wall_wind_and_soil(
    *,
    wind_pressure_kpa: float,
    wall_height_m: float,
    soil_height_m: float,
    soil_unit_weight_kn_m3: float,
    friction_angle_deg: float,
    surcharge_kpa: float = 0.0,
) -> WallStripReference:
    """Independent resultant for a planter wall with wind and active soil."""

    if wind_pressure_kpa < 0 or wall_height_m <= 0 or not 0 <= soil_height_m <= wall_height_m:
        raise ValueError("inputs outside the bounded reference domain")
    if soil_unit_weight_kn_m3 <= 0 or not 0 < friction_angle_deg < 45 or surcharge_kpa < 0:
        raise ValueError("inputs outside the bounded reference domain")
    coefficient = tan(radians(45.0 - friction_angle_deg / 2.0)) ** 2
    soil_force = 0.5 * coefficient * soil_unit_weight_kn_m3 * soil_height_m**2
    soil_force += coefficient * surcharge_kpa * soil_height_m
    soil_moment = 0.5 * coefficient * soil_unit_weight_kn_m3 * soil_height_m**3 / 3.0
    soil_moment += coefficient * surcharge_kpa * soil_height_m**2 / 2.0
    wind_force = wind_pressure_kpa * wall_height_m
    return WallStripReference(
        line_load_kn_m=wind_force + soil_force,
        shear_kn=wind_force + soil_force,
        moment_kn_m=wind_pressure_kpa * wall_height_m**2 / 2.0 + soil_moment,
    )


@dataclass(frozen=True)
class RetainingReference:
    active_coefficient: float
    earth_force_kn_m: float
    water_force_kn_m: float
    horizontal_force_kn_m: float
    overturning_moment_kn_m: float


def solve_retaining_wall_actions(
    *,
    height_m: float,
    soil_unit_weight_kn_m3: float,
    friction_angle_deg: float,
    surcharge_kpa: float = 0.0,
    water_depth_m: float = 0.0,
) -> RetainingReference:
    if height_m <= 0 or soil_unit_weight_kn_m3 <= 0 or not 0 < friction_angle_deg < 60:
        raise ValueError("inputs outside the bounded reference domain")
    if surcharge_kpa < 0 or not 0 <= water_depth_m <= height_m:
        raise ValueError("inputs outside the bounded reference domain")
    coefficient = tan(radians(45.0 - friction_angle_deg / 2.0)) ** 2
    earth = 0.5 * coefficient * soil_unit_weight_kn_m3 * height_m**2
    earth += coefficient * surcharge_kpa * height_m
    water = 0.5 * 9.81 * water_depth_m**2
    earth_moment = earth * height_m / 3.0
    water_moment = water * water_depth_m / 3.0
    return RetainingReference(
        active_coefficient=coefficient,
        earth_force_kn_m=earth,
        water_force_kn_m=water,
        horizontal_force_kn_m=earth + water,
        overturning_moment_kn_m=earth_moment + water_moment,
    )
