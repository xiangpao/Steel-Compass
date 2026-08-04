from __future__ import annotations

from dataclasses import dataclass
from math import radians, tan

from .errors import CalculationInputError


@dataclass(frozen=True)
class TriangularLateralAction:
    maximum_pressure_kpa: float
    resultant_kn_per_m: float
    resultant_height_from_base_m: float


@dataclass(frozen=True)
class EarthPressureAction:
    coefficient: float
    soil_resultant_kn_per_m: float
    surcharge_resultant_kn_per_m: float
    total_resultant_kn_per_m: float
    overturning_moment_kn_m_per_m: float


def hydrostatic_lateral_action(
    *, depth_m: float, water_unit_weight_kn_m3: float = 10.0
) -> TriangularLateralAction:
    if depth_m < 0 or water_unit_weight_kn_m3 <= 0:
        raise CalculationInputError(
            "invalid_water_pressure_input",
            "水深不得小于 0，水重度必须大于 0。",
            field="depth_m",
        )
    maximum = water_unit_weight_kn_m3 * depth_m
    resultant = maximum * depth_m / 2
    return TriangularLateralAction(
        maximum_pressure_kpa=maximum,
        resultant_kn_per_m=resultant,
        resultant_height_from_base_m=depth_m / 3 if depth_m else 0.0,
    )


def rankine_active_earth_action(
    *,
    height_m: float,
    friction_angle_deg: float,
    soil_unit_weight_kn_m3: float,
    surcharge_kpa: float = 0.0,
) -> EarthPressureAction:
    if height_m <= 0:
        raise CalculationInputError(
            "invalid_wall_height", "挡土高度必须大于 0。", field="height_m"
        )
    if not 0 < friction_angle_deg < 45:
        raise CalculationInputError(
            "invalid_friction_angle",
            "首期 Rankine 主动土压力要求内摩擦角大于 0 且小于 45°。",
            field="friction_angle_deg",
        )
    if soil_unit_weight_kn_m3 <= 0 or surcharge_kpa < 0:
        raise CalculationInputError(
            "invalid_soil_pressure_input",
            "土重度必须大于 0，附加荷载不得小于 0。",
            field="soil_unit_weight_kn_m3",
        )
    coefficient = tan(radians(45 - friction_angle_deg / 2)) ** 2
    soil_resultant = 0.5 * coefficient * soil_unit_weight_kn_m3 * height_m**2
    surcharge_resultant = coefficient * surcharge_kpa * height_m
    moment = soil_resultant * height_m / 3 + surcharge_resultant * height_m / 2
    return EarthPressureAction(
        coefficient=coefficient,
        soil_resultant_kn_per_m=soil_resultant,
        surcharge_resultant_kn_per_m=surcharge_resultant,
        total_resultant_kn_per_m=soil_resultant + surcharge_resultant,
        overturning_moment_kn_m_per_m=moment,
    )


def buoyancy_force(
    *,
    plan_area_m2: float,
    submerged_depth_m: float,
    water_unit_weight_kn_m3: float = 10.0,
) -> float:
    if plan_area_m2 <= 0 or submerged_depth_m < 0 or water_unit_weight_kn_m3 <= 0:
        raise CalculationInputError(
            "invalid_buoyancy_input",
            "受浮面积和水重度必须大于 0，浸没深度不得小于 0。",
            field="plan_area_m2",
        )
    return plan_area_m2 * submerged_depth_m * water_unit_weight_kn_m3
