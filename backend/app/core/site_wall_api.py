"""Schema 3.2 adapters for bounded landscape-wall calculation cores."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import CalculationInputError
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    LoadCombinationResult,
    PlainMasonryWallInputs,
    Quantity,
    ReactionEnvelope,
    SiteRCWallInputs,
    SiteWallLoadCaseInputs,
    SteelInfillWallInputs,
    TypedInputValue,
)
from .site_walls import (
    CastInPlaceRCWallInput,
    LowMasonryWallInput,
    SiteWallResult,
    SteelPostInfillWallInput,
    WallLoadCase,
    calculate_cast_in_place_rc_wall,
    calculate_low_masonry_wall,
    calculate_steel_post_infill_wall,
)


def _unit(unit: str) -> str:
    return (
        unit.strip()
        .replace("虏", "2")
        .replace("鲁", "3")
        .replace("路", "*")
        .replace("·", "*")
        .replace(" ", "")
        .lower()
    )


def _convert(value: TypedInputValue, factors: Mapping[str, float], *, field: str) -> float:
    canonical = _unit(value.unit)
    if canonical not in factors:
        raise CalculationInputError(
            "invalid_unit",
            f"Unsupported unit {value.unit!r} for {field}.",
            field=field,
            details={"unit": value.unit, "supported_units": sorted(factors)},
        )
    return value.value * factors[canonical]


LENGTH_M = {"m": 1.0, "mm": 0.001}
LENGTH_MM = {"mm": 1.0, "m": 1000.0}
PRESSURE_KPA = {"kpa": 1.0, "kn/m2": 1.0}
UNIT_WEIGHT = {"kn/m3": 1.0}
STRESS_MPA = {"mpa": 1.0, "gpa": 1000.0}
AREA_MM2 = {"mm2": 1.0, "m2": 1.0e6}
AREA_PER_M = {"mm2/m": 1.0}
INERTIA_MM4 = {"mm4": 1.0, "m4": 1.0e12}
SECTION_MM3 = {"mm3": 1.0, "m3": 1.0e9}
LINE_KN_M = {"kn/m": 1.0, "n/mm": 1.0}
DIMENSIONLESS = {"1": 1.0}


def _cases(items: list[SiteWallLoadCaseInputs]) -> tuple[WallLoadCase, ...]:
    return tuple(
        WallLoadCase(
            combination_id=item.combination_id,
            combination_name=item.combination_name,
            limit_state=item.limit_state,
            wind_pressure_kpa=_convert(
                item.wind_pressure,
                PRESSURE_KPA,
                field=f"load_cases.{index}.wind_pressure",
            ),
            additional_dead_load_kpa=_convert(
                item.additional_dead_load,
                PRESSURE_KPA,
                field=f"load_cases.{index}.additional_dead_load",
            ),
        )
        for index, item in enumerate(items)
    )


def _typed(request: CalculationRequest, expected: type[Any]) -> Any:
    if not isinstance(request.typed_inputs, expected):
        raise CalculationInputError(
            "typed_input_module_mismatch",
            f"{request.module.value} requires its matching Schema 3.2 typed_inputs.",
            field="typed_inputs",
        )
    return request.typed_inputs


def _opposite_envelope(item: Any) -> ReactionEnvelope:
    """Return the support reaction, opposite to the external effect vector."""

    core = item.reaction
    return ReactionEnvelope(
        name=core.name,
        limit_state=core.limit_state,
        combination_id=core.combination_id,
        combination_name=core.combination_name,
        direction=core.direction,
        components={
            key: Quantity(value=-value.value, unit=value.unit)
            for key, value in core.components.items()
        },
    )


def _wrap(
    request: CalculationRequest,
    trace_id: str,
    solved: SiteWallResult,
    *,
    input_summary: dict[str, Quantity | str | bool],
    standards: list[str],
) -> CalculationResult:
    envelopes = [_opposite_envelope(item) for item in solved.combinations]
    combinations = [
        LoadCombinationResult(
            name=item.reaction.combination_name or item.combination_id,
            combination_id=item.combination_id,
            limit_state=item.limit_state,
            factors={},
            factored_by_kind={},
            directions_by_kind={"wind": [item.reaction.direction]} if item.reaction.direction else {},
            total=Quantity(value=item.axial_kn, unit="kN"),
            effect_components={
                "N": Quantity(value=item.axial_kn, unit="kN"),
                "Vx": Quantity(value=item.shear_kn, unit="kN"),
                "Vy": Quantity(value=0.0, unit="kN"),
                "Mx": Quantity(value=0.0, unit="kN*m"),
                "My": Quantity(value=item.moment_kn_m, unit="kN*m"),
                "T": Quantity(value=0.0, unit="kN*m"),
            },
        )
        for item in solved.combinations
    ]
    checks = [
        CheckResult(
            name=item.key,
            demand=Quantity(value=item.demand, unit=item.unit),
            capacity=Quantity(value=item.capacity, unit=item.unit),
            utilization=item.utilization,
            passed=item.passed,
            reference=item.reference_basis,
            governing_combination=item.combination_id,
        )
        for item in solved.checks
    ]
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=solved.status,
        result_class="quick_estimate" if request.mode.value == "quick" else "professional_check",
        verification_status="unverified",
        standards=standards,
        input_summary=input_summary,
        combinations=combinations,
        reactions={"foundation_line_load": Quantity(value=solved.foundation_line_load_kn_m, unit="kN/m")},
        reaction_envelopes=envelopes,
        steps=[
            CalculationStep(
                name="wall action and base equilibrium",
                equation="external effects + base reaction = 0",
                substitution=f"combinations={len(combinations)}",
                result=Quantity(value=0.0, unit="kN"),
                reference="same-combination static equilibrium",
            )
        ],
        checks=checks,
        governing_check=solved.governing_check,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="site_wall_capability_limited",
                message="The result excludes: " + "; ".join(solved.missing_capabilities),
            )
        ],
        assumptions=list(solved.assumptions),
        applicability=list(solved.applicability),
        catalog_versions={"schema": request.schema_version, "site_wall_core": "1.0-unverified"},
    )


def calculate_site_rc_wall(request: CalculationRequest, trace_id: str) -> CalculationResult:
    data: SiteRCWallInputs = _typed(request, SiteRCWallInputs)
    solved = calculate_cast_in_place_rc_wall(
        CastInPlaceRCWallInput(
            height_m=_convert(data.height, LENGTH_M, field="height"),
            length_m=_convert(data.length, LENGTH_M, field="length"),
            thickness_mm=_convert(data.thickness, LENGTH_MM, field="thickness"),
            support_spacing_m=_convert(data.support_spacing, LENGTH_M, field="support_spacing"),
            opening_ratio=_convert(data.opening_ratio, DIMENSIONLESS, field="opening_ratio"),
            concrete_unit_weight_kn_m3=_convert(data.concrete_unit_weight, UNIT_WEIGHT, field="concrete_unit_weight"),
            concrete_fc_mpa=_convert(data.concrete_fc, STRESS_MPA, field="concrete_fc"),
            concrete_ft_mpa=_convert(data.concrete_ft, STRESS_MPA, field="concrete_ft"),
            rebar_fy_mpa=_convert(data.rebar_fy, STRESS_MPA, field="rebar_fy"),
            vertical_rebar_mm2_per_m=_convert(data.vertical_rebar, AREA_PER_M, field="vertical_rebar"),
            horizontal_rebar_mm2_per_m=_convert(data.horizontal_rebar, AREA_PER_M, field="horizontal_rebar"),
            cover_mm=_convert(data.cover, LENGTH_MM, field="cover"),
            bar_diameter_mm=_convert(data.bar_diameter, LENGTH_MM, field="bar_diameter"),
            minimum_reinforcement_ratio=_convert(data.minimum_reinforcement_ratio, DIMENSIONLESS, field="minimum_reinforcement_ratio"),
            slenderness_limit=_convert(data.slenderness_limit, DIMENSIONLESS, field="slenderness_limit"),
            load_cases=_cases(data.load_cases),
        )
    )
    return _wrap(
        request, trace_id, solved,
        input_summary={
            "system": "cast_in_place_rc",
            "height": Quantity(value=_convert(data.height, LENGTH_M, field="height"), unit="m"),
            "thickness": Quantity(value=_convert(data.thickness, LENGTH_MM, field="thickness"), unit="mm"),
            "opening_ratio": Quantity(value=_convert(data.opening_ratio, DIMENSIONLESS, field="opening_ratio"), unit="1"),
        },
        standards=["CN-2026.1", "GB/T 50010-2010 (2024 amendment) candidate mapping"],
    )


def calculate_steel_infill_wall(request: CalculationRequest, trace_id: str) -> CalculationResult:
    data: SteelInfillWallInputs = _typed(request, SteelInfillWallInputs)
    solved = calculate_steel_post_infill_wall(
        SteelPostInfillWallInput(
            height_m=_convert(data.height, LENGTH_M, field="height"),
            length_m=_convert(data.length, LENGTH_M, field="length"),
            support_spacing_m=_convert(data.support_spacing, LENGTH_M, field="support_spacing"),
            opening_ratio=_convert(data.opening_ratio, DIMENSIONLESS, field="opening_ratio"),
            infill_dead_load_kpa=_convert(data.infill_dead_load, PRESSURE_KPA, field="infill_dead_load"),
            post_self_weight_kn_m=_convert(data.post_self_weight, LINE_KN_M, field="post_self_weight"),
            post_area_mm2=_convert(data.post_area, AREA_MM2, field="post_area"),
            post_inertia_mm4=_convert(data.post_inertia, INERTIA_MM4, field="post_inertia"),
            post_section_modulus_mm3=_convert(data.post_section_modulus, SECTION_MM3, field="post_section_modulus"),
            steel_elastic_modulus_mpa=_convert(data.steel_elastic_modulus, STRESS_MPA, field="steel_elastic_modulus"),
            steel_yield_strength_mpa=_convert(data.steel_yield_strength, STRESS_MPA, field="steel_yield_strength"),
            effective_length_factor=_convert(data.effective_length_factor, DIMENSIONLESS, field="effective_length_factor"),
            slenderness_limit=_convert(data.slenderness_limit, DIMENSIONLESS, field="slenderness_limit"),
            maximum_post_spacing_m=_convert(data.maximum_post_spacing, LENGTH_M, field="maximum_post_spacing"),
            load_cases=_cases(data.load_cases),
        )
    )
    return _wrap(
        request, trace_id, solved,
        input_summary={
            "system": "steel_post_infill",
            "height": Quantity(value=_convert(data.height, LENGTH_M, field="height"), unit="m"),
            "support_spacing": Quantity(value=_convert(data.support_spacing, LENGTH_M, field="support_spacing"), unit="m"),
            "opening_ratio": Quantity(value=_convert(data.opening_ratio, DIMENSIONLESS, field="opening_ratio"), unit="1"),
        },
        standards=["CN-2026.1", "GB 50017-2017 candidate mapping"],
    )


def calculate_plain_masonry_wall(request: CalculationRequest, trace_id: str) -> CalculationResult:
    data: PlainMasonryWallInputs = _typed(request, PlainMasonryWallInputs)
    solved = calculate_low_masonry_wall(
        LowMasonryWallInput(
            height_m=_convert(data.height, LENGTH_M, field="height"),
            length_m=_convert(data.length, LENGTH_M, field="length"),
            thickness_mm=_convert(data.thickness, LENGTH_MM, field="thickness"),
            support_spacing_m=_convert(data.support_spacing, LENGTH_M, field="support_spacing"),
            opening_ratio=_convert(data.opening_ratio, DIMENSIONLESS, field="opening_ratio"),
            masonry_unit_weight_kn_m3=_convert(data.masonry_unit_weight, UNIT_WEIGHT, field="masonry_unit_weight"),
            masonry_bending_strength_mpa=_convert(data.masonry_bending_strength, STRESS_MPA, field="masonry_bending_strength"),
            masonry_shear_strength_mpa=_convert(data.masonry_shear_strength, STRESS_MPA, field="masonry_shear_strength"),
            masonry_compression_strength_mpa=_convert(data.masonry_compression_strength, STRESS_MPA, field="masonry_compression_strength"),
            slenderness_limit=_convert(data.slenderness_limit, DIMENSIONLESS, field="slenderness_limit"),
            minimum_thickness_mm=_convert(data.minimum_thickness, LENGTH_MM, field="minimum_thickness"),
            maximum_height_m=_convert(data.maximum_height, LENGTH_M, field="maximum_height"),
            load_cases=_cases(data.load_cases),
        )
    )
    return _wrap(
        request, trace_id, solved,
        input_summary={
            "system": "plain_masonry",
            "height": Quantity(value=_convert(data.height, LENGTH_M, field="height"), unit="m"),
            "thickness": Quantity(value=_convert(data.thickness, LENGTH_MM, field="thickness"), unit="mm"),
            "opening_ratio": Quantity(value=_convert(data.opening_ratio, DIMENSIONLESS, field="opening_ratio"), unit="1"),
        },
        standards=["CN-2026.1", "GB 50003-2011 candidate mapping"],
    )
