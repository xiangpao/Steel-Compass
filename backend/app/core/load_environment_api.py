from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import CalculationInputError
from .load_environment import (
    LoadCase,
    SoilWaterInput,
    WindSnowGuideInput,
    calculate_soil_water_actions,
    calculate_wind_snow_actions,
    generate_action_combinations,
)
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    LoadCombinationResult,
    LoadCombinationsInputs,
    LoadDirection,
    Quantity,
    SoilWaterActionsInputs,
    TypedInputValue,
    WindSnowGuideInputs,
)


def _unit(value: str) -> str:
    return (
        value.strip()
        .replace("²", "2")
        .replace("³", "3")
        .replace("·", "*")
        .replace(" ", "")
        .lower()
    )


def _convert(
    value: TypedInputValue,
    factors: Mapping[str, float],
    *,
    field: str,
) -> float:
    canonical = _unit(value.unit)
    if canonical not in factors:
        raise CalculationInputError(
            "invalid_unit",
            f"{field} 的单位 {value.unit!r} 不受支持。",
            field=field,
            details={"unit": value.unit, "supported_units": sorted(factors)},
        )
    return value.value * factors[canonical]


def _optional(
    value: TypedInputValue | None,
    factors: Mapping[str, float],
    *,
    field: str,
) -> float | None:
    return None if value is None else _convert(value, factors, field=field)


def _typed(request: CalculationRequest, expected: type[Any]) -> Any:
    if not isinstance(request.typed_inputs, expected):
        raise CalculationInputError(
            "typed_input_module_mismatch",
            f"{request.module.value} 必须使用对应的 Schema 3.2 typed_inputs。",
            field="typed_inputs",
        )
    return request.typed_inputs


DIMENSIONLESS = {"1": 1.0}
FORCE = {"kn": (1.0, "kN"), "n": (0.001, "kN")}
LINE = {"kn/m": (1.0, "kN/m"), "n/mm": (1.0, "kN/m")}
PRESSURE = {"kpa": (1.0, "kPa"), "kn/m2": (1.0, "kN/m2")}
LENGTH_M = {"m": 1.0, "mm": 0.001}
AREA_M2 = {"m2": 1.0, "mm2": 1.0e-6}
UNIT_WEIGHT = {"kn/m3": 1.0}
ANGLE = {"deg": 1.0, "°": 1.0}
YEARS = {"year": 1.0, "years": 1.0, "a": 1.0, "年": 1.0}


def _action_value(value: TypedInputValue, *, field: str) -> tuple[float, str]:
    canonical = _unit(value.unit)
    for factors in (FORCE, LINE, PRESSURE):
        if canonical in factors:
            scale, output_unit = factors[canonical]
            return value.value * scale, output_unit
    raise CalculationInputError(
        "invalid_action_unit",
        f"{field} 必须使用力、线荷载或压力单位。",
        field=field,
        details={"unit": value.unit},
    )


def _effect_components(
    *, vertical: float = 0.0, x: float = 0.0, y: float = 0.0, unit: str
) -> dict[str, Quantity]:
    return {
        "N": Quantity(value=vertical, unit=unit),
        "Vx": Quantity(value=x, unit=unit),
        "Vy": Quantity(value=y, unit=unit),
        "Mx": Quantity(value=0.0, unit=f"{unit}*m"),
        "My": Quantity(value=0.0, unit=f"{unit}*m"),
        "T": Quantity(value=0.0, unit=f"{unit}*m"),
    }


def _base_result(
    request: CalculationRequest,
    trace_id: str,
    *,
    combinations: list[LoadCombinationResult],
    steps: list[CalculationStep],
    input_summary: dict[str, Quantity | str | bool],
    assumptions: list[str],
    applicability: list[str],
) -> CalculationResult:
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status="passed",
        result_class=(
            "quick_estimate" if request.mode.value == "quick" else "professional_check"
        ),
        verification_status="unverified",
        standards=[request.standard_profile, "荷载环境参数化底座（未独立验证）"],
        input_summary=input_summary,
        combinations=combinations,
        steps=steps,
        checks=[],
        provisional_checks=[],
        warnings=[
            CalculationWarning(
                severity="warning",
                code="load_environment_solver_unverified",
                message="该荷载环境模块尚未完成规范映射和独立验证。",
            )
        ],
        assumptions=assumptions,
        applicability=applicability,
        catalog_versions={"schema": request.schema_version},
    )


def calculate_load_combinations(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: LoadCombinationsInputs = _typed(request, LoadCombinationsInputs)
    cases: list[LoadCase] = []
    distributions: dict[str, str] = {}
    for index, item in enumerate(data.cases):
        value, unit = _action_value(
            item.characteristic, field=f"cases.{index}.characteristic"
        )
        distributions[item.id] = item.distribution
        cases.append(
            LoadCase(
                id=item.id,
                label=item.label,
                category=item.category,
                characteristic_value=value,
                unit=unit,
                direction=item.direction,
                target=item.target,
                source_reference=item.source_reference,
                exclusive_group=item.exclusive_group,
                permanent_role=item.permanent_role,
                psi0=_optional(item.psi0, DIMENSIONLESS, field=f"cases.{index}.psi0"),
                psi1=_optional(item.psi1, DIMENSIONLESS, field=f"cases.{index}.psi1"),
                psi2=_optional(item.psi2, DIMENSIONLESS, field=f"cases.{index}.psi2"),
            )
        )
    bundle = generate_action_combinations(cases)
    combinations: list[LoadCombinationResult] = []
    for item in bundle.combinations:
        resultant = next(
            (
                value
                for value in (
                    item.resultants["vertical"],
                    item.resultants["x"],
                    item.resultants["y"],
                )
                if abs(value) > 1.0e-12
            ),
            0.0,
        )
        combinations.append(
            LoadCombinationResult(
                name=item.id,
                combination_id=item.id,
                limit_state=item.limit_state,
                sls_type=item.sls_type,
                leading_action=item.leading_action,
                factors={action.case_id: action.factor for action in item.actions},
                factored_by_kind={
                    action.case_id: Quantity(
                        value=action.factored_value, unit=action.unit
                    )
                    for action in item.actions
                },
                directions_by_kind={
                    action.case_id: [LoadDirection(action.direction)]
                    for action in item.actions
                },
                total=Quantity(value=resultant, unit=item.unit),
                effect_components=_effect_components(
                    vertical=item.resultants["vertical"],
                    x=item.resultants["x"],
                    y=item.resultants["y"],
                    unit=item.unit,
                ),
            )
        )
    steps = [
        CalculationStep(
            name="作用组合生成",
            equation="G + leading Q + accompanying ψQ",
            substitution=(
                f"cases={len(cases)}, combinations={len(combinations)}, "
                f"exclusive_groups={len({case.exclusive_group for case in cases if case.exclusive_group})}"
            ),
            result=Quantity(value=len(combinations), unit="1"),
            reference="CN-2026.1 组合配置候选映射（待独立复核）",
        )
    ]
    summary: dict[str, Quantity | str | bool] = {
        "target": cases[0].target,
        "unit": cases[0].unit,
        "case_count": Quantity(value=len(cases), unit="1"),
    }
    for case in cases:
        summary[f"source.{case.id}"] = case.source_reference
        summary[f"distribution.{case.id}"] = distributions[case.id]
    return _base_result(
        request,
        trace_id,
        combinations=combinations,
        steps=steps,
        input_summary=summary,
        assumptions=["互斥方向工况不在同一组合中同时出现。"],
        applicability=["同一目标、同一作用量纲的 ULS/SLS 组合生成"],
    )


def _single_action_combination(
    *,
    action_id: str,
    category: str,
    value: float,
    unit: str,
    direction: str,
) -> LoadCombinationResult:
    sign = -1.0 if direction in {"uplift", "x_negative", "y_negative"} else 1.0
    signed = value * sign
    vertical = signed if direction in {"gravity", "uplift"} else 0.0
    x = signed if direction.startswith("x_") else 0.0
    y = signed if direction.startswith("y_") else 0.0
    return LoadCombinationResult(
        name=action_id,
        combination_id=action_id,
        limit_state="SLS",
        sls_type="standard",
        factors={action_id: 1.0},
        factored_by_kind={category: Quantity(value=signed, unit=unit)},
        directions_by_kind={category: [LoadDirection(direction)]},
        total=Quantity(value=signed, unit=unit),
        effect_components=_effect_components(
            vertical=vertical, x=x, y=y, unit=unit
        ),
    )


def calculate_wind_snow_guide(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: WindSnowGuideInputs = _typed(request, WindSnowGuideInputs)
    recurrence = _convert(
        data.recurrence_period, YEARS, field="recurrence_period"
    )
    rounded = round(recurrence)
    if abs(recurrence - rounded) > 1.0e-9:
        raise CalculationInputError(
            "invalid_recurrence_period",
            "重现期必须是整年数。",
            field="recurrence_period",
        )
    solved = calculate_wind_snow_actions(
        WindSnowGuideInput(
            basic_wind_pressure_kpa=_convert(
                data.basic_wind_pressure, {"kpa": 1.0, "kn/m2": 1.0}, field="basic_wind_pressure"
            ),
            wind_source_reference=data.wind_source_reference,
            recurrence_period_years=int(rounded),
            recurrence_factor=_convert(
                data.recurrence_factor, DIMENSIONLESS, field="recurrence_factor"
            ),
            terrain_roughness=data.terrain_roughness,
            terrain_height_factor=_convert(
                data.terrain_height_factor,
                DIMENSIONLESS,
                field="terrain_height_factor",
            ),
            shape_coefficient_positive=_convert(
                data.shape_coefficient_positive,
                DIMENSIONLESS,
                field="shape_coefficient_positive",
            ),
            shape_coefficient_negative=_convert(
                data.shape_coefficient_negative,
                DIMENSIONLESS,
                field="shape_coefficient_negative",
            ),
            wind_area_m2=_convert(data.wind_area, AREA_M2, field="wind_area"),
            snow_applicability=data.snow_applicability,
            basic_snow_pressure_kpa=_optional(
                data.basic_snow_pressure,
                {"kpa": 1.0, "kn/m2": 1.0},
                field="basic_snow_pressure",
            ),
            snow_source_reference=data.snow_source_reference,
            roof_snow_coefficient=_optional(
                data.roof_snow_coefficient,
                DIMENSIONLESS,
                field="roof_snow_coefficient",
            ),
            snow_area_m2=_optional(data.snow_area, AREA_M2, field="snow_area"),
            no_snow_basis=data.no_snow_basis,
            target=data.target,
        )
    )
    combinations = [
        _single_action_combination(
            action_id=item.id,
            category=item.category,
            value=item.characteristic_value,
            unit=item.unit,
            direction=item.direction,
        )
        for item in solved.actions
    ]
    steps = [
        CalculationStep(
            name=item.id,
            equation=item.calculation,
            substitution=(
                f"pressure={item.pressure_kpa:.6g} kPa, "
                f"force={item.characteristic_value:.6g} kN, direction={item.direction}"
            ),
            result=Quantity(value=item.characteristic_value, unit=item.unit),
            reference=item.source_reference,
        )
        for item in solved.actions
    ]
    summary: dict[str, Quantity | str | bool] = {
        "wind_source": data.wind_source_reference,
        "snow_status": solved.snow_status,
        "target": data.target,
        "recurrence_period": Quantity(value=recurrence, unit="year"),
    }
    if solved.no_snow_basis:
        summary["no_snow_basis"] = solved.no_snow_basis
    return _base_result(
        request,
        trace_id,
        combinations=combinations,
        steps=steps,
        input_summary=summary,
        assumptions=["基本风压和雪压必须来自已复核资料，软件不自动抓取城市值。"],
        applicability=["参数化构件风雪作用生成", f"snow={solved.snow_status}"],
    )


def calculate_soil_water_action_package(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: SoilWaterActionsInputs = _typed(request, SoilWaterActionsInputs)
    solved = calculate_soil_water_actions(
        SoilWaterInput(
            wall_height_m=_convert(data.wall_height, LENGTH_M, field="wall_height"),
            earth_pressure_state=data.earth_pressure_state,
            soil_unit_weight_dry_kn_m3=_convert(
                data.soil_unit_weight_dry,
                UNIT_WEIGHT,
                field="soil_unit_weight_dry",
            ),
            soil_unit_weight_saturated_kn_m3=_convert(
                data.soil_unit_weight_saturated,
                UNIT_WEIGHT,
                field="soil_unit_weight_saturated",
            ),
            soil_friction_angle_deg=_convert(
                data.soil_friction_angle, ANGLE, field="soil_friction_angle"
            ),
            surcharge_kpa=_convert(
                data.surcharge,
                {"kpa": 1.0, "kn/m2": 1.0},
                field="surcharge",
            ),
            groundwater_depth_below_top_m=_convert(
                data.groundwater_depth_below_top,
                LENGTH_M,
                field="groundwater_depth_below_top",
            ),
            water_unit_weight_kn_m3=_convert(
                data.water_unit_weight, UNIT_WEIGHT, field="water_unit_weight"
            ),
            internal_water_depth_m=_convert(
                data.internal_water_depth, LENGTH_M, field="internal_water_depth"
            ),
            external_water_depth_m=_optional(
                data.external_water_depth, LENGTH_M, field="external_water_depth"
            ),
            base_area_m2=_convert(data.base_area, AREA_M2, field="base_area"),
            at_rest_coefficient=_optional(
                data.at_rest_coefficient,
                DIMENSIONLESS,
                field="at_rest_coefficient",
            ),
            source_reference=data.source_reference,
            target=data.target,
        )
    )
    combinations: list[LoadCombinationResult] = []
    steps: list[CalculationStep] = []
    for item in solved.actions:
        value = item.force_kn if item.force_kn is not None else item.resultant_kn_per_m or 0.0
        unit = "kN" if item.force_kn is not None else "kN/m"
        combinations.append(
            _single_action_combination(
                action_id=item.id,
                category=item.category,
                value=value,
                unit=unit,
                direction=item.direction,
            )
        )
        steps.append(
            CalculationStep(
                name=item.id,
                equation="earth/water pressure integration and resultant",
                substitution=(
                    f"base_pressure={item.base_pressure_kpa:.6g} kPa, "
                    f"resultant={value:.6g} {unit}, direction={item.direction}"
                ),
                result=Quantity(value=value, unit=unit),
                reference=item.source_reference,
            )
        )
    return _base_result(
        request,
        trace_id,
        combinations=combinations,
        steps=steps,
        input_summary={
            "source": data.source_reference,
            "target": data.target,
            "earth_pressure_state": data.earth_pressure_state,
            "earth_pressure_coefficient": Quantity(
                value=solved.earth_pressure_coefficient, unit="1"
            ),
        },
        assumptions=["土压力按单一均质土层和水平填土计算。"],
        applicability=["主动或静止土压力、内外水压力与基底浮力作用包"],
    )
