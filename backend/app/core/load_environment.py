from __future__ import annotations

from collections import defaultdict
from itertools import product
from math import isfinite, sin, radians
from typing import Literal

from pydantic import BaseModel, Field

from .errors import CalculationInputError


Direction = Literal[
    "gravity", "uplift", "x_positive", "x_negative", "y_positive", "y_negative"
]
ActionCategory = Literal[
    "permanent", "live", "wind", "snow", "soil", "water", "buoyancy", "seismic"
]

SUPPORTED_ACTION_UNITS = {"kN", "kN/m", "kN/m2", "kPa"}


class LoadCase(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    category: ActionCategory
    characteristic_value: float
    unit: str = Field(min_length=1, max_length=24)
    direction: Direction
    target: str = Field(min_length=1, max_length=120)
    source_reference: str = Field(min_length=1, max_length=240)
    exclusive_group: str | None = None
    permanent_role: Literal["auto", "favorable", "unfavorable"] = "auto"
    psi0: float | None = None
    psi1: float | None = None
    psi2: float | None = None


class CombinationPolicy(BaseModel):
    permanent_unfavorable_uls: float = 1.3
    permanent_favorable_uls: float = 0.9
    variable_leading_uls: float = 1.5
    variable_accompanying_uls: float = 1.5


class FactoredAction(BaseModel):
    case_id: str
    category: ActionCategory
    direction: Direction
    source_reference: str
    factor: float
    characteristic_value: float
    signed_characteristic_value: float
    factored_value: float
    unit: str


class ActionCombination(BaseModel):
    id: str
    design_situation: Literal["persistent", "seismic"] = "persistent"
    limit_state: Literal["ULS", "SLS"]
    sls_type: Literal["standard", "frequent", "quasi_permanent"] | None = None
    leading_action: str | None = None
    target: str
    unit: str
    actions: list[FactoredAction]
    resultants: dict[Literal["vertical", "x", "y"], float]
    verification_status: Literal["unverified"] = "unverified"


class CombinationBundle(BaseModel):
    combinations: list[ActionCombination]
    verification_status: Literal["unverified"] = "unverified"


def _direction_axis(direction: Direction) -> Literal["vertical", "x", "y"]:
    if direction in {"gravity", "uplift"}:
        return "vertical"
    return "x" if direction.startswith("x_") else "y"


def _direction_sign(direction: Direction) -> float:
    return -1.0 if direction in {"uplift", "x_negative", "y_negative"} else 1.0


def _psi(case: LoadCase) -> tuple[float, float, float]:
    defaults = {
        "live": (0.7, 0.5, 0.3),
        "wind": (0.6, 0.2, 0.0),
        "snow": (0.7, 0.2, 0.0),
        "soil": (1.0, 1.0, 1.0),
        "water": (1.0, 1.0, 1.0),
        "buoyancy": (1.0, 1.0, 1.0),
    }.get(case.category, (1.0, 1.0, 1.0))
    values = (
        defaults[0] if case.psi0 is None else case.psi0,
        defaults[1] if case.psi1 is None else case.psi1,
        defaults[2] if case.psi2 is None else case.psi2,
    )
    if any(value < 0 or value > 1 for value in values):
        raise CalculationInputError(
            "invalid_combination_coefficient",
            "组合值系数必须位于 0 到 1 之间。",
            field=case.id,
        )
    return values


def _validate_load_cases(cases: list[LoadCase]) -> None:
    if not cases:
        raise CalculationInputError("missing_load_cases", "至少需要一个作用工况。")
    if len({case.id for case in cases}) != len(cases):
        raise CalculationInputError("duplicate_load_case", "作用工况编号不能重复。")
    target = cases[0].target
    unit = cases[0].unit
    for case in cases:
        if not isfinite(case.characteristic_value) or case.characteristic_value < 0:
            raise CalculationInputError(
                "invalid_load_value",
                "作用标准值必须是非负有限数。",
                field=case.id,
            )
        if case.unit not in SUPPORTED_ACTION_UNITS:
            raise CalculationInputError(
                "unsupported_load_unit",
                "作用组合使用了不支持的单位。",
                field=case.id,
                details={"unit": case.unit},
            )
        if case.target != target or case.unit != unit:
            raise CalculationInputError(
                "incompatible_combination_scope",
                "一次组合只能处理同一目标和同一量纲的作用。",
                details={"expected_target": target, "expected_unit": unit},
            )
        if not case.source_reference.strip():
            raise CalculationInputError(
                "missing_load_source", "作用工况必须提供可追溯来源。", field=case.id
            )
        _psi(case)


def _permanent_factor(
    case: LoadCase, leading: LoadCase | None, policy: CombinationPolicy
) -> float:
    if case.permanent_role == "favorable":
        return policy.permanent_favorable_uls
    if case.permanent_role == "unfavorable":
        return policy.permanent_unfavorable_uls
    if (
        leading is not None
        and _direction_axis(case.direction) == _direction_axis(leading.direction)
        and _direction_sign(case.direction) != _direction_sign(leading.direction)
    ):
        return policy.permanent_favorable_uls
    return policy.permanent_unfavorable_uls


def _factored(case: LoadCase, factor: float) -> FactoredAction:
    signed = case.characteristic_value * _direction_sign(case.direction)
    return FactoredAction(
        case_id=case.id,
        category=case.category,
        direction=case.direction,
        source_reference=case.source_reference,
        factor=factor,
        characteristic_value=case.characteristic_value,
        signed_characteristic_value=signed,
        factored_value=signed * factor,
        unit=case.unit,
    )


def _combination(
    combination_id: str,
    cases_and_factors: list[tuple[LoadCase, float]],
    *,
    limit_state: Literal["ULS", "SLS"],
    leading: LoadCase | None = None,
    sls_type: Literal["standard", "frequent", "quasi_permanent"] | None = None,
    design_situation: Literal["persistent", "seismic"] = "persistent",
) -> ActionCombination:
    actions = [_factored(case, factor) for case, factor in cases_and_factors if factor]
    resultants: dict[Literal["vertical", "x", "y"], float] = {
        "vertical": 0.0,
        "x": 0.0,
        "y": 0.0,
    }
    for case, factor in cases_and_factors:
        resultants[_direction_axis(case.direction)] += (
            case.characteristic_value * _direction_sign(case.direction) * factor
        )
    first = cases_and_factors[0][0]
    return ActionCombination(
        id=combination_id,
        design_situation=design_situation,
        limit_state=limit_state,
        sls_type=sls_type,
        leading_action=leading.id if leading else None,
        target=first.target,
        unit=first.unit,
        actions=actions,
        resultants=resultants,
    )


def _variable_selections(
    variable: list[LoadCase], leading: LoadCase | None
) -> list[list[LoadCase]]:
    ungrouped = [case for case in variable if not case.exclusive_group]
    groups: dict[str, list[LoadCase]] = defaultdict(list)
    for case in variable:
        if case.exclusive_group:
            groups[case.exclusive_group].append(case)
    choices: list[list[LoadCase]] = []
    for group_cases in groups.values():
        if leading is not None and leading in group_cases:
            choices.append([leading])
        else:
            choices.append(group_cases)
    if not choices:
        return [ungrouped]
    return [ungrouped + list(selection) for selection in product(*choices)]


def _selection_suffix(selected: list[LoadCase]) -> str:
    alternatives = [case.id for case in selected if case.exclusive_group]
    return "" if not alternatives else "-ALT-" + "-".join(alternatives)


def generate_action_combinations(
    cases: list[LoadCase], policy: CombinationPolicy | None = None
) -> CombinationBundle:
    """Generate traceable combinations for one target and one effect unit.

    Alternative cases (for example positive and negative wind) share an
    ``exclusive_group`` and never appear together in one combination.
    """

    _validate_load_cases(cases)
    policy = policy or CombinationPolicy()
    permanent = [case for case in cases if case.category == "permanent"]
    seismic = [case for case in cases if case.category == "seismic"]
    variable = [
        case for case in cases if case.category not in {"permanent", "seismic"}
    ]
    combinations: list[ActionCombination] = []

    leading_cases: list[LoadCase | None] = variable or [None]
    for leading in leading_cases:
        for selected_variables in _variable_selections(variable, leading):
            factors: list[tuple[LoadCase, float]] = [
                (case, _permanent_factor(case, leading, policy)) for case in permanent
            ]
            factors.extend(
                (
                    case,
                    policy.variable_leading_uls
                    if case is leading
                    else policy.variable_accompanying_uls * _psi(case)[0],
                )
                for case in selected_variables
            )
            combinations.append(
                _combination(
                    f"ULS-{leading.id if leading else 'PERMANENT'}"
                    f"{_selection_suffix(selected_variables)}",
                    factors,
                    limit_state="ULS",
                    leading=leading,
                )
            )

    for leading in leading_cases:
        for selected_variables in _variable_selections(variable, leading):
            suffix = _selection_suffix(selected_variables)
            standard = [(case, 1.0) for case in permanent]
            standard.extend(
                (case, 1.0 if case is leading else _psi(case)[0])
                for case in selected_variables
            )
            frequent = [(case, 1.0) for case in permanent]
            frequent.extend(
                (case, _psi(case)[1] if case is leading else _psi(case)[2])
                for case in selected_variables
            )
            combinations.extend(
                [
                    _combination(
                        f"SLS-STANDARD-{leading.id if leading else 'PERMANENT'}{suffix}",
                        standard,
                        limit_state="SLS",
                        leading=leading,
                        sls_type="standard",
                    ),
                    _combination(
                        f"SLS-FREQUENT-{leading.id if leading else 'PERMANENT'}{suffix}",
                        frequent,
                        limit_state="SLS",
                        leading=leading,
                        sls_type="frequent",
                    ),
                ]
            )

    # Seismic is a separate design situation: E is used with factor 1.0 and
    # ordinary variable actions use their quasi-permanent coefficient. It is
    # intentionally excluded from the 1.5 persistent-action branch above.
    for earthquake in seismic:
        factors = [(case, 1.0) for case in permanent]
        factors.extend((case, _psi(case)[2]) for case in variable)
        factors.append((earthquake, 1.0))
        combinations.append(
            _combination(
                f"SEISMIC-{earthquake.id}",
                factors,
                limit_state="ULS",
                leading=earthquake,
                design_situation="seismic",
            )
        )
    for selected_variables in _variable_selections(variable, None):
        quasi = [(case, 1.0) for case in permanent]
        quasi.extend((case, _psi(case)[2]) for case in selected_variables)
        combinations.append(
            _combination(
                f"SLS-QUASI-PERMANENT{_selection_suffix(selected_variables)}",
                quasi,
                limit_state="SLS",
                sls_type="quasi_permanent",
            )
        )
    return CombinationBundle(combinations=combinations)


class WindSnowGuideInput(BaseModel):
    basic_wind_pressure_kpa: float
    wind_source_reference: str
    recurrence_period_years: int
    recurrence_factor: float = 1.0
    terrain_roughness: Literal["A", "B", "C", "D"]
    terrain_height_factor: float
    shape_coefficient_positive: float
    shape_coefficient_negative: float
    wind_area_m2: float
    snow_applicability: Literal["applicable", "not_applicable"]
    basic_snow_pressure_kpa: float | None = None
    snow_source_reference: str | None = None
    roof_snow_coefficient: float | None = None
    snow_area_m2: float | None = None
    no_snow_basis: str | None = None
    target: str = Field(min_length=1, max_length=120)


class EnvironmentalAction(BaseModel):
    id: str
    category: Literal["wind", "snow"]
    characteristic_value: float
    unit: Literal["kN"]
    pressure_kpa: float
    direction: Direction
    target: str
    source_reference: str
    calculation: str


class WindSnowGuideResult(BaseModel):
    actions: list[EnvironmentalAction]
    snow_status: Literal["calculated", "not_applicable"]
    no_snow_basis: str | None = None
    verification_status: Literal["unverified"] = "unverified"


def calculate_wind_snow_actions(data: WindSnowGuideInput) -> WindSnowGuideResult:
    positive_fields = {
        "basic_wind_pressure_kpa": data.basic_wind_pressure_kpa,
        "recurrence_factor": data.recurrence_factor,
        "terrain_height_factor": data.terrain_height_factor,
        "shape_coefficient_positive": data.shape_coefficient_positive,
        "wind_area_m2": data.wind_area_m2,
    }
    if any(not isfinite(value) or value <= 0 for value in positive_fields.values()):
        raise CalculationInputError(
            "invalid_wind_guide_input",
            "风荷载向导的压力、系数和面积必须为正有限数。",
            details=positive_fields,
        )
    if data.shape_coefficient_negative >= 0 or not isfinite(
        data.shape_coefficient_negative
    ):
        raise CalculationInputError(
            "invalid_negative_shape_coefficient",
            "负向体型系数必须小于零。",
            field="shape_coefficient_negative",
        )
    if data.recurrence_period_years <= 0 or not data.wind_source_reference.strip():
        raise CalculationInputError(
            "missing_wind_basis", "风压必须提供有效重现期和已复核资料来源。"
        )
    common = (
        data.basic_wind_pressure_kpa
        * data.recurrence_factor
        * data.terrain_height_factor
    )
    positive_pressure = common * data.shape_coefficient_positive
    negative_pressure = common * abs(data.shape_coefficient_negative)
    actions = [
        EnvironmentalAction(
            id="wind-positive",
            category="wind",
            characteristic_value=positive_pressure * data.wind_area_m2,
            unit="kN",
            pressure_kpa=positive_pressure,
            direction="x_positive",
            target=data.target,
            source_reference=data.wind_source_reference,
            calculation="w0 * recurrence * terrain-height * positive-shape * area",
        ),
        EnvironmentalAction(
            id="wind-negative",
            category="wind",
            characteristic_value=negative_pressure * data.wind_area_m2,
            unit="kN",
            pressure_kpa=negative_pressure,
            direction="x_negative",
            target=data.target,
            source_reference=data.wind_source_reference,
            calculation="w0 * recurrence * terrain-height * abs(negative-shape) * area",
        ),
    ]
    if data.snow_applicability == "not_applicable":
        if not (data.no_snow_basis or "").strip():
            raise CalculationInputError(
                "missing_no_snow_basis",
                "无雪地区必须记录不适用依据。",
                field="no_snow_basis",
            )
        return WindSnowGuideResult(
            actions=actions,
            snow_status="not_applicable",
            no_snow_basis=data.no_snow_basis,
        )
    snow_values = (
        data.basic_snow_pressure_kpa,
        data.roof_snow_coefficient,
        data.snow_area_m2,
    )
    if (
        any(value is None or not isfinite(value) or value < 0 for value in snow_values)
        or not (data.snow_source_reference or "").strip()
    ):
        raise CalculationInputError(
            "incomplete_snow_guide",
            "适用雪荷载时必须提供基本雪压、屋面积雪系数、面积和来源。",
        )
    snow_pressure = data.basic_snow_pressure_kpa * data.roof_snow_coefficient  # type: ignore[operator]
    actions.append(
        EnvironmentalAction(
            id="roof-snow",
            category="snow",
            characteristic_value=snow_pressure * data.snow_area_m2,  # type: ignore[operator]
            unit="kN",
            pressure_kpa=snow_pressure,
            direction="gravity",
            target=data.target,
            source_reference=data.snow_source_reference or "",
            calculation="s0 * roof-snow-coefficient * area",
        )
    )
    return WindSnowGuideResult(actions=actions, snow_status="calculated")


class SoilWaterInput(BaseModel):
    wall_height_m: float
    earth_pressure_state: Literal["active", "at_rest"]
    soil_unit_weight_dry_kn_m3: float
    soil_unit_weight_saturated_kn_m3: float
    soil_friction_angle_deg: float
    surcharge_kpa: float = 0.0
    groundwater_depth_below_top_m: float
    water_unit_weight_kn_m3: float = 10.0
    internal_water_depth_m: float = 0.0
    external_water_depth_m: float | None = None
    base_area_m2: float
    at_rest_coefficient: float | None = None
    source_reference: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=120)


class PressureAction(BaseModel):
    id: str
    category: Literal["soil", "water", "buoyancy"]
    resultant_kn_per_m: float | None = None
    force_kn: float | None = None
    base_pressure_kpa: float
    moment_about_base_kn_m_per_m: float | None = None
    centroid_above_base_m: float | None = None
    direction: Direction
    target: str
    source_reference: str


class SoilWaterResult(BaseModel):
    earth_pressure_coefficient: float
    actions: list[PressureAction]
    verification_status: Literal["unverified"] = "unverified"


def _integrate_linear_pressure(
    c: float, slope: float, start: float, end: float, height: float
) -> tuple[float, float]:
    force = c * (end - start) + slope * (end**2 - start**2) / 2.0
    moment = (
        c * (height * (end - start) - (end**2 - start**2) / 2.0)
        + slope
        * (height * (end**2 - start**2) / 2.0 - (end**3 - start**3) / 3.0)
    )
    return force, moment


def calculate_soil_water_actions(data: SoilWaterInput) -> SoilWaterResult:
    numeric = {
        "wall_height_m": data.wall_height_m,
        "soil_unit_weight_dry_kn_m3": data.soil_unit_weight_dry_kn_m3,
        "soil_unit_weight_saturated_kn_m3": data.soil_unit_weight_saturated_kn_m3,
        "water_unit_weight_kn_m3": data.water_unit_weight_kn_m3,
        "base_area_m2": data.base_area_m2,
    }
    if any(not isfinite(value) or value <= 0 for value in numeric.values()):
        raise CalculationInputError(
            "invalid_soil_water_geometry",
            "墙高、土水重度和底板面积必须为正有限数。",
            details=numeric,
        )
    if not 0 < data.soil_friction_angle_deg < 45:
        raise CalculationInputError(
            "invalid_friction_angle", "土内摩擦角必须位于 0° 到 45° 之间。"
        )
    if data.surcharge_kpa < 0 or data.internal_water_depth_m < 0:
        raise CalculationInputError(
            "invalid_soil_water_load", "附加荷载和水深不能为负值。"
        )
    height = data.wall_height_m
    groundwater_depth = min(max(data.groundwater_depth_below_top_m, 0.0), height)
    external_depth = (
        height - groundwater_depth
        if data.external_water_depth_m is None
        else data.external_water_depth_m
    )
    if external_depth < 0 or external_depth > height or data.internal_water_depth_m > height:
        raise CalculationInputError(
            "water_level_out_of_range", "内外水深必须位于零和墙高之间。"
        )
    phi = radians(data.soil_friction_angle_deg)
    if data.earth_pressure_state == "active":
        coefficient = (1.0 - sin(phi)) / (1.0 + sin(phi))
    else:
        coefficient = (
            1.0 - sin(phi)
            if data.at_rest_coefficient is None
            else data.at_rest_coefficient
        )
        if coefficient <= 0 or coefficient >= 1:
            raise CalculationInputError(
                "invalid_at_rest_coefficient", "静止土压力系数必须位于 0 和 1 之间。"
            )

    dry_end = groundwater_depth
    surcharge_pressure = coefficient * data.surcharge_kpa
    soil_force, soil_moment = _integrate_linear_pressure(
        surcharge_pressure,
        coefficient * data.soil_unit_weight_dry_kn_m3,
        0.0,
        dry_end,
        height,
    )
    submerged_weight = (
        data.soil_unit_weight_saturated_kn_m3 - data.water_unit_weight_kn_m3
    )
    if submerged_weight <= 0:
        raise CalculationInputError(
            "invalid_submerged_unit_weight",
            "饱和土重度必须大于水重度。",
        )
    if dry_end < height:
        intercept = coefficient * (
            (data.soil_unit_weight_dry_kn_m3 - submerged_weight) * dry_end
            + data.surcharge_kpa
        )
        below_force, below_moment = _integrate_linear_pressure(
            intercept,
            coefficient * submerged_weight,
            dry_end,
            height,
            height,
        )
        soil_force += below_force
        soil_moment += below_moment
    effective_stress_base = (
        data.soil_unit_weight_dry_kn_m3 * dry_end
        + submerged_weight * (height - dry_end)
    )
    soil_base_pressure = coefficient * (
        effective_stress_base + data.surcharge_kpa
    )
    actions = [
        PressureAction(
            id=f"soil-{data.earth_pressure_state}",
            category="soil",
            resultant_kn_per_m=soil_force,
            base_pressure_kpa=soil_base_pressure,
            moment_about_base_kn_m_per_m=soil_moment,
            centroid_above_base_m=soil_moment / soil_force if soil_force else 0.0,
            direction="x_positive",
            target=data.target,
            source_reference=data.source_reference,
        )
    ]
    for action_id, depth, direction in (
        ("external-water", external_depth, "x_positive"),
        ("internal-water", data.internal_water_depth_m, "x_negative"),
    ):
        pressure = data.water_unit_weight_kn_m3 * depth
        force = pressure * depth / 2.0
        actions.append(
            PressureAction(
                id=action_id,
                category="water",
                resultant_kn_per_m=force,
                base_pressure_kpa=pressure,
                moment_about_base_kn_m_per_m=force * depth / 3.0,
                centroid_above_base_m=depth / 3.0,
                direction=direction,  # type: ignore[arg-type]
                target=data.target,
                source_reference=data.source_reference,
            )
        )
    buoyancy_pressure = data.water_unit_weight_kn_m3 * external_depth
    actions.append(
        PressureAction(
            id="base-uplift",
            category="buoyancy",
            force_kn=buoyancy_pressure * data.base_area_m2,
            base_pressure_kpa=buoyancy_pressure,
            direction="uplift",
            target=data.target,
            source_reference=data.source_reference,
        )
    )
    return SoilWaterResult(
        earth_pressure_coefficient=coefficient,
        actions=actions,
    )
