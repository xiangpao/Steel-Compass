from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .bridge import (
    BridgeActions,
    BridgeComfortSettings,
    BridgeGeometry,
    SteelBeamSection,
    SteelTimberBridgeInput,
    TimberDeck,
    calculate_steel_timber_bridge,
)
from .bridge_rc import (
    RCBridgeGeometry,
    RCBridgeLoads,
    RCBridgeMaterial,
    RCBridgeModel,
    RCBridgeReinforcement,
    RCBridgeServiceLimits,
    RCBridgeSpanLoad,
    RCBridgeSupport,
    analyze_rc_pedestrian_bridge,
)
from .errors import CalculationInputError
from .gravity_retaining import (
    GravityRetainingInput,
    calculate_gravity_retaining_wall as solve_gravity_retaining_wall,
)
from .pile_group import (
    InvestigatedPileCapacities,
    PileCapGeometry,
    PileCapMaterial,
    PileDefinition,
    PileGroupActions,
    PileGroupModel,
    analyze_rigid_pile_group,
)
from .pool_structure import (
    PoolMaterials,
    PoolReinforcement,
    PoolWaterLevels,
    RectangularPoolGeometry,
    RectangularPoolInput,
    calculate_rectangular_pool,
)
from .schemas import (
    BridgeRCInputs,
    BridgeSteelTimberInputs,
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    GravityRetainingWallInputs,
    LoadCombinationResult,
    LoadDirection,
    PileGroupCapInputs,
    PoolStructureInputs,
    Quantity,
    ReactionEnvelope,
    TypedInputValue,
)


def _unit(value: str) -> str:
    return (
        value.strip()
        .replace("²", "2")
        .replace("³", "3")
        .replace("·", "*")
        .replace("路", "*")
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


def _count(value: TypedInputValue, *, field: str) -> int:
    numeric = _convert(value, {"1": 1.0}, field=field)
    rounded = round(numeric)
    if abs(numeric - rounded) > 1e-9:
        raise CalculationInputError(
            "invalid_count", f"{field} 必须是整数。", field=field
        )
    return int(rounded)


LENGTH_M = {"m": 1.0, "mm": 0.001}
LENGTH_MM = {"mm": 1.0, "m": 1000.0}
AREA_MM2 = {"mm2": 1.0, "m2": 1.0e6}
INERTIA_MM4 = {"mm4": 1.0, "m4": 1.0e12}
SECTION_MM3 = {"mm3": 1.0, "m3": 1.0e9}
FORCE_KN = {"kn": 1.0, "n": 0.001}
FORCE_N = {"n": 1.0, "kn": 1000.0}
MOMENT_KNM = {"kn*m": 1.0, "n*mm": 1.0e-6}
PRESSURE_KPA = {"kpa": 1.0, "kn/m2": 1.0}
STRESS_MPA = {"mpa": 1.0, "gpa": 1000.0}
LINE_KN_M = {"kn/m": 1.0, "n/mm": 1.0}
UNIT_WEIGHT = {"kn/m3": 1.0}
AREA_PER_M = {"mm2/m": 1.0}
ANGLE_DEG = {"deg": 1.0}
FREQUENCY_HZ = {"hz": 1.0}
ACCELERATION = {"m/s2": 1.0}
DIMENSIONLESS = {"1": 1.0}


def _components(
    *,
    n: float = 0.0,
    vx: float = 0.0,
    vy: float = 0.0,
    mx: float = 0.0,
    my: float = 0.0,
    torsion: float = 0.0,
) -> dict[str, Quantity]:
    return {
        "N": Quantity(value=n, unit="kN"),
        "Vx": Quantity(value=vx, unit="kN"),
        "Vy": Quantity(value=vy, unit="kN"),
        "Mx": Quantity(value=mx, unit="kN*m"),
        "My": Quantity(value=my, unit="kN*m"),
        "T": Quantity(value=torsion, unit="kN*m"),
    }


def _check(
    *,
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    passed: bool,
    reference: str,
    combination: str | None = None,
    note: str | None = None,
) -> CheckResult:
    return CheckResult(
        name=name,
        demand=Quantity(value=max(float(demand), 0.0), unit=unit),
        capacity=Quantity(value=max(float(capacity), 0.0), unit=unit),
        utilization=max(float(demand) / max(float(capacity), 1e-12), 0.0),
        passed=bool(passed),
        reference=reference,
        governing_combination=combination,
        note=note,
    )


def _result(
    request: CalculationRequest,
    trace_id: str,
    *,
    checks: list[CheckResult],
    combinations: list[LoadCombinationResult],
    reactions: dict[str, Quantity],
    envelopes: list[ReactionEnvelope],
    input_summary: dict[str, Quantity | str | bool],
    assumptions: list[str],
    applicability: list[str],
    step_name: str,
) -> CalculationResult:
    governing = max(checks, key=lambda item: item.utilization) if checks else None
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status="passed" if all(item.passed for item in checks) else "failed",
        result_class=(
            "quick_estimate" if request.mode.value == "quick" else "professional_check"
        ),
        verification_status="unverified",
        standards=["CN-2026.6", "参数化基础设施底座（未独立验证）"],
        input_summary=input_summary,
        combinations=combinations,
        reactions=reactions,
        reaction_envelopes=envelopes,
        steps=[
            CalculationStep(
                name=step_name,
                equation="typed inputs -> parameterized solver -> traceable result",
                substitution=f"checks={len(checks)}, combinations={len(combinations)}",
                result=Quantity(
                    value=governing.utilization if governing else 0.0, unit="1"
                ),
                reference="Schema 3.2 参数化计算接口",
            )
        ],
        checks=checks,
        governing_check=governing.name if governing else None,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="infrastructure_solver_unverified",
                message="该基础设施模块尚未完成规范映射和独立验证。",
            )
        ],
        assumptions=assumptions,
        applicability=applicability,
        catalog_versions={"schema": request.schema_version},
    )


def _typed(request: CalculationRequest, expected: type[Any]) -> Any:
    if not isinstance(request.typed_inputs, expected):
        raise CalculationInputError(
            "typed_input_module_mismatch",
            f"{request.module.value} 必须使用对应的 Schema 3.2 typed_inputs。",
            field="typed_inputs",
        )
    return request.typed_inputs


def calculate_pool_structure(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: PoolStructureInputs = _typed(request, PoolStructureInputs)
    geometry = data.geometry
    materials = data.materials
    reinforcement = data.reinforcement
    levels = data.water_levels
    solved = calculate_rectangular_pool(
        RectangularPoolInput(
            geometry=RectangularPoolGeometry(
                inside_length_m=_convert(geometry.inside_length, LENGTH_M, field="geometry.inside_length"),
                inside_width_m=_convert(geometry.inside_width, LENGTH_M, field="geometry.inside_width"),
                wall_height_m=_convert(geometry.wall_height, LENGTH_M, field="geometry.wall_height"),
                wall_thickness_mm=_convert(geometry.wall_thickness, LENGTH_MM, field="geometry.wall_thickness"),
                base_thickness_mm=_convert(geometry.base_thickness, LENGTH_MM, field="geometry.base_thickness"),
                base_projection_m=_convert(geometry.base_projection, LENGTH_M, field="geometry.base_projection"),
                retained_soil_height_m=_convert(geometry.retained_soil_height, LENGTH_M, field="geometry.retained_soil_height"),
                wall_horizontal_span_m=_optional(geometry.wall_horizontal_span, LENGTH_M, field="geometry.wall_horizontal_span"),
            ),
            materials=PoolMaterials(
                concrete_unit_weight_kn_m3=_convert(materials.concrete_unit_weight, UNIT_WEIGHT, field="materials.concrete_unit_weight"),
                water_unit_weight_kn_m3=_convert(materials.water_unit_weight, UNIT_WEIGHT, field="materials.water_unit_weight"),
                soil_unit_weight_kn_m3=_convert(materials.soil_unit_weight, UNIT_WEIGHT, field="materials.soil_unit_weight"),
                soil_friction_angle_deg=_convert(materials.soil_friction_angle, ANGLE_DEG, field="materials.soil_friction_angle"),
                surcharge_kpa=_convert(materials.surcharge, PRESSURE_KPA, field="materials.surcharge"),
                allowable_bearing_kpa=_convert(materials.allowable_bearing, PRESSURE_KPA, field="materials.allowable_bearing"),
                concrete_fc_mpa=_convert(materials.concrete_fc, STRESS_MPA, field="materials.concrete_fc"),
                concrete_ft_mpa=_convert(materials.concrete_ft, STRESS_MPA, field="materials.concrete_ft"),
                rebar_fy_mpa=_convert(materials.rebar_fy, STRESS_MPA, field="materials.rebar_fy"),
                rebar_es_mpa=_convert(materials.rebar_es, STRESS_MPA, field="materials.rebar_es"),
            ),
            reinforcement=PoolReinforcement(
                wall_vertical_as_mm2_per_m=_convert(reinforcement.wall_vertical_as, AREA_PER_M, field="reinforcement.wall_vertical_as"),
                wall_horizontal_as_mm2_per_m=_convert(reinforcement.wall_horizontal_as, AREA_PER_M, field="reinforcement.wall_horizontal_as"),
                base_x_as_mm2_per_m=_convert(reinforcement.base_x_as, AREA_PER_M, field="reinforcement.base_x_as"),
                base_y_as_mm2_per_m=_convert(reinforcement.base_y_as, AREA_PER_M, field="reinforcement.base_y_as"),
                wall_bar_diameter_mm=_convert(reinforcement.wall_bar_diameter, LENGTH_MM, field="reinforcement.wall_bar_diameter"),
                base_bar_diameter_mm=_convert(reinforcement.base_bar_diameter, LENGTH_MM, field="reinforcement.base_bar_diameter"),
                wall_cover_mm=_convert(reinforcement.wall_cover, LENGTH_MM, field="reinforcement.wall_cover"),
                base_cover_mm=_convert(reinforcement.base_cover, LENGTH_MM, field="reinforcement.base_cover"),
                minimum_reinforcement_ratio=_convert(reinforcement.minimum_reinforcement_ratio, DIMENSIONLESS, field="reinforcement.minimum_reinforcement_ratio"),
                crack_width_limit_mm=_convert(reinforcement.crack_width_limit, LENGTH_MM, field="reinforcement.crack_width_limit"),
            ),
            water_levels=PoolWaterLevels(
                full_internal_depth_m=_convert(levels.full_internal_depth, LENGTH_M, field="water_levels.full_internal_depth"),
                empty_external_head_m=_convert(levels.empty_external_head, LENGTH_M, field="water_levels.empty_external_head"),
                full_external_head_m=_optional(levels.full_external_head, LENGTH_M, field="water_levels.full_external_head"),
            ),
            additional_ballast_kn=_convert(data.additional_ballast, FORCE_KN, field="additional_ballast"),
            antifloat_factor=_convert(data.antifloat_factor, DIMENSIONLESS, field="antifloat_factor"),
        )
    )
    checks = [
        _check(
            name=item.name,
            demand=item.demand,
            capacity=item.capacity,
            unit=item.unit,
            passed=item.passed,
            reference=item.reference_basis,
            combination=item.controlling_combination_id,
        )
        for item in solved.checks
    ]
    combinations: list[LoadCombinationResult] = []
    envelopes: list[ReactionEnvelope] = []
    for item in solved.combinations:
        net_vertical = item.base.net_vertical_kn
        # effect_components are external actions; envelopes are support
        # reactions, so their component-wise sum is zero.
        components = _components(n=-net_vertical)
        reaction_components = _components(n=net_vertical)
        combinations.append(
            LoadCombinationResult(
                name=item.combination_id,
                combination_id=item.combination_id,
                limit_state=item.limit_state,
                factors=item.factors,
                factored_by_kind={},
                total=Quantity(value=net_vertical, unit="kN"),
                effect_components=components,  # type: ignore[arg-type]
            )
        )
        envelopes.append(
            ReactionEnvelope(
                name="pool-base",
                limit_state=item.limit_state,
                combination_id=item.combination_id,
                combination_name=item.combination_id,
                direction=(LoadDirection.GRAVITY if net_vertical >= 0 else LoadDirection.UPLIFT),
                components=reaction_components,  # type: ignore[arg-type]
            )
        )
    return _result(
        request,
        trace_id,
        checks=checks,
        combinations=combinations,
        reactions={"base.N": Quantity(value=envelopes[0].components["N"].value, unit="kN")},
        envelopes=envelopes,
        input_summary={
            "inside_length": Quantity(
                value=_convert(
                    geometry.inside_length,
                    LENGTH_M,
                    field="geometry.inside_length",
                ),
                unit="m",
            ),
            "combination_count": Quantity(value=len(combinations), unit="1"),
        },
        assumptions=list(solved.assumptions),
        applicability=list(solved.applicability),
        step_name="矩形RC水池组合分析",
    )


def calculate_pile_group_cap(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: PileGroupCapInputs = _typed(request, PileGroupCapInputs)
    cap, material, effects = data.cap, data.material, data.effects
    solved = analyze_rigid_pile_group(
        PileGroupModel(
            piles=tuple(
                PileDefinition(
                    item.id,
                    _convert(item.x, LENGTH_MM, field=f"piles.{item.id}.x"),
                    _convert(item.y, LENGTH_MM, field=f"piles.{item.id}.y"),
                    _convert(item.diameter_or_side, LENGTH_MM, field=f"piles.{item.id}.diameter_or_side"),
                    item.pile_type,
                )
                for item in data.piles
            ),
            capacities=InvestigatedPileCapacities(
                _convert(data.capacities.compression, FORCE_KN, field="capacities.compression"),
                _convert(data.capacities.uplift, FORCE_KN, field="capacities.uplift"),
                _convert(data.capacities.horizontal, FORCE_KN, field="capacities.horizontal"),
                data.capacities.source,
            ),
            cap=PileCapGeometry(
                _convert(cap.length_x, LENGTH_MM, field="cap.length_x"),
                _convert(cap.width_y, LENGTH_MM, field="cap.width_y"),
                _convert(cap.thickness, LENGTH_MM, field="cap.thickness"),
                _convert(cap.column_x, LENGTH_MM, field="cap.column_x"),
                _convert(cap.column_y, LENGTH_MM, field="cap.column_y"),
                _convert(cap.cover, LENGTH_MM, field="cap.cover"),
                _convert(cap.bar_diameter, LENGTH_MM, field="cap.bar_diameter"),
            ),
            material=PileCapMaterial(
                _convert(material.concrete_ft, STRESS_MPA, field="material.concrete_ft"),
                _convert(material.rebar_fy, STRESS_MPA, field="material.rebar_fy"),
                _convert(material.provided_rebar_x, AREA_PER_M, field="material.provided_rebar_x"),
                _convert(material.provided_rebar_y, AREA_PER_M, field="material.provided_rebar_y"),
                _convert(material.minimum_reinforcement_ratio, DIMENSIONLESS, field="material.minimum_reinforcement_ratio"),
            ),
            actions=PileGroupActions(
                _convert(effects.axial, FORCE_KN, field="effects.axial"),
                _convert(effects.shear_x, FORCE_KN, field="effects.shear_x"),
                _convert(effects.shear_y, FORCE_KN, field="effects.shear_y"),
                _convert(effects.moment_x, MOMENT_KNM, field="effects.moment_x"),
                _convert(effects.moment_y, MOMENT_KNM, field="effects.moment_y"),
                _convert(effects.torsion, MOMENT_KNM, field="effects.torsion"),
            ),
        )
    )
    checks = [
        _check(
            name=item.name,
            demand=item.demand,
            capacity=item.capacity,
            unit=item.unit,
            passed=item.passed,
            reference="勘察承载力输入与刚性承台筛查",
            combination=data.combination_id,
            note=item.note,
        )
        for item in solved.group_capacity_checks + solved.cap_checks
    ]
    envelopes: list[ReactionEnvelope] = []
    reactions: dict[str, Quantity] = {}
    for pile_id, item in solved.pile_reactions.items():
        axial = item.compression_kn - item.uplift_kn
        components = _components(
            n=axial,
            vx=item.horizontal_x_kn,
            vy=item.horizontal_y_kn,
        )
        envelopes.append(
            ReactionEnvelope(
                name=pile_id,
                limit_state=data.limit_state,
                combination_id=data.combination_id,
                combination_name=data.combination_name,
                direction=(LoadDirection.GRAVITY if axial >= 0 else LoadDirection.UPLIFT),
                components=components,  # type: ignore[arg-type]
            )
        )
        reactions[f"{pile_id}.N"] = Quantity(value=axial, unit="kN")
    total_components = _components(
        n=solved.balance.n_kn,
        vx=solved.balance.vx_kn,
        vy=solved.balance.vy_kn,
        mx=solved.balance.mx_kn_m,
        my=solved.balance.my_kn_m,
        torsion=solved.balance.torsion_kn_m,
    )
    combination = LoadCombinationResult(
        name=data.combination_name,
        combination_id=data.combination_id,
        limit_state=data.limit_state,
        factors={},
        factored_by_kind={},
        total=Quantity(value=solved.balance.n_kn, unit="kN"),
        effect_components=total_components,  # type: ignore[arg-type]
    )
    return _result(
        request,
        trace_id,
        checks=checks,
        combinations=[combination],
        reactions=reactions,
        envelopes=envelopes,
        input_summary={
            "pile_count": Quantity(value=len(data.piles), unit="1"),
            "capacity_source": solved.capacity_source,
        },
        assumptions=list(solved.method_notes),
        applicability=["勘察承载力驱动的非共线刚性承台桩群"] + list(solved.exclusions),
        step_name="刚性承台桩群六分量分配",
    )


def _steel_section(data: Any, field: str) -> SteelBeamSection:
    return SteelBeamSection(
        area_mm2=_convert(data.area, AREA_MM2, field=f"{field}.area"),
        inertia_mm4=_convert(data.inertia, INERTIA_MM4, field=f"{field}.inertia"),
        section_modulus_mm3=_convert(data.section_modulus, SECTION_MM3, field=f"{field}.section_modulus"),
        shear_area_mm2=_convert(data.shear_area, AREA_MM2, field=f"{field}.shear_area"),
        yield_strength_mpa=_convert(data.yield_strength, STRESS_MPA, field=f"{field}.yield_strength"),
        elastic_modulus_mpa=_convert(data.elastic_modulus, STRESS_MPA, field=f"{field}.elastic_modulus"),
        unit_weight_kn_m3=_convert(data.unit_weight, UNIT_WEIGHT, field=f"{field}.unit_weight"),
    )


def calculate_bridge_steel_timber(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: BridgeSteelTimberInputs = _typed(request, BridgeSteelTimberInputs)
    geometry, actions, timber, comfort = (
        data.geometry,
        data.actions,
        data.timber_deck,
        data.comfort,
    )
    solved = calculate_steel_timber_bridge(
        SteelTimberBridgeInput(
            geometry=BridgeGeometry(
                _count(geometry.span_count, field="geometry.span_count"),
                _convert(geometry.span_length, LENGTH_M, field="geometry.span_length"),
                _convert(geometry.deck_width, LENGTH_M, field="geometry.deck_width"),
                _convert(geometry.crossbeam_spacing, LENGTH_M, field="geometry.crossbeam_spacing"),
                _count(geometry.longitudinal_girder_count, field="geometry.longitudinal_girder_count"),
            ),
            actions=BridgeActions(
                _convert(actions.crowd_load, PRESSURE_KPA, field="actions.crowd_load"),
                _convert(actions.additional_dead_load, PRESSURE_KPA, field="actions.additional_dead_load"),
                _convert(actions.railing_dead_load_per_side, LINE_KN_M, field="actions.railing_dead_load_per_side"),
                _convert(actions.wind_line_load, LINE_KN_M, field="actions.wind_line_load"),
                tuple(
                    _convert(item, DIMENSIONLESS, field=f"actions.span_live_load_factors.{index}")
                    for index, item in enumerate(actions.span_live_load_factors or [])
                ) or None,
            ),
            timber_deck=TimberDeck(
                _convert(timber.thickness, LENGTH_MM, field="timber_deck.thickness"),
                _convert(timber.elastic_modulus, STRESS_MPA, field="timber_deck.elastic_modulus"),
                _convert(timber.bending_strength, STRESS_MPA, field="timber_deck.bending_strength"),
                _convert(timber.shear_strength, STRESS_MPA, field="timber_deck.shear_strength"),
                _convert(timber.unit_weight, UNIT_WEIGHT, field="timber_deck.unit_weight"),
                _convert(timber.deflection_limit_ratio, DIMENSIONLESS, field="timber_deck.deflection_limit_ratio"),
            ),
            crossbeam_section=_steel_section(data.crossbeam_section, "crossbeam_section"),
            longitudinal_section=_steel_section(data.longitudinal_section, "longitudinal_section"),
            comfort=BridgeComfortSettings(
                _convert(comfort.damping_ratio, DIMENSIONLESS, field="comfort.damping_ratio"),
                _convert(comfort.walking_frequency, FREQUENCY_HZ, field="comfort.walking_frequency"),
                _convert(comfort.pedestrian_dynamic_force, FORCE_N, field="comfort.pedestrian_dynamic_force"),
                _convert(comfort.acceleration_limit, ACCELERATION, field="comfort.acceleration_limit"),
            ),
            foundation_types=tuple(data.foundation_types) if data.foundation_types else None,
        )
    )
    checks = [
        _check(
            name=item.name,
            demand=item.demand,
            capacity=item.capacity,
            unit=item.unit,
            passed=item.passed,
            reference=item.basis,
            combination=item.controlling_combination_id,
        )
        for item in solved.checks
    ]
    combinations: list[LoadCombinationResult] = []
    envelopes: list[ReactionEnvelope] = []
    reactions: dict[str, Quantity] = {}
    for item in solved.combinations:
        components = _components(
            n=-item.total_vertical_load_kn,
            vx=-item.total_wind_load_kn,
        )
        combinations.append(
            LoadCombinationResult(
                name=item.combination_id,
                combination_id=item.combination_id,
                limit_state=item.limit_state,
                factors=item.factors,
                factored_by_kind={},
                total=Quantity(value=item.total_vertical_load_kn, unit="kN"),
                effect_components=components,  # type: ignore[arg-type]
            )
        )
        for reaction in item.support_reactions:
            reaction_components = _components(**{
                "n": reaction.n_vertical_kn,
                "vx": reaction.vx_kn,
                "vy": reaction.vy_kn,
                "mx": reaction.mx_kn_m,
                "my": reaction.my_kn_m,
                "torsion": reaction.torsion_kn_m,
            })
            envelopes.append(
                ReactionEnvelope(
                    name=reaction.support_id,
                    limit_state=item.limit_state,
                    combination_id=item.combination_id,
                    combination_name=item.combination_id,
                    direction=(
                        LoadDirection.X_NEGATIVE
                        if reaction.vx_kn < 0
                        else LoadDirection.X_POSITIVE
                        if reaction.vx_kn > 0
                        else LoadDirection.GRAVITY
                    ),
                    components=reaction_components,  # type: ignore[arg-type]
                )
            )
            reactions[f"{item.combination_id}.{reaction.support_id}.N"] = Quantity(
                value=reaction.n_vertical_kn, unit="kN"
            )
    return _result(
        request,
        trace_id,
        checks=checks,
        combinations=combinations,
        reactions=reactions,
        envelopes=envelopes,
        input_summary={
            "span_count": Quantity(value=_count(geometry.span_count, field="geometry.span_count"), unit="1"),
            "system": "steel_timber",
        },
        assumptions=list(solved.assumptions),
        applicability=list(solved.applicability),
        step_name="钢梁木桥面参数化人行桥",
    )


def calculate_bridge_rc(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: BridgeRCInputs = _typed(request, BridgeRCInputs)
    geometry, material, reinforcement, loads, limits = (
        data.geometry,
        data.material,
        data.reinforcement,
        data.loads,
        data.service_limits,
    )
    solved = analyze_rc_pedestrian_bridge(
        RCBridgeModel(
            geometry=RCBridgeGeometry(
                _count(geometry.span_count, field="geometry.span_count"),
                _convert(geometry.span_length, LENGTH_M, field="geometry.span_length"),
                _convert(geometry.deck_width, LENGTH_M, field="geometry.deck_width"),
                _convert(geometry.deck_elevation, LENGTH_M, field="geometry.deck_elevation"),
                _convert(geometry.slab_thickness, LENGTH_MM, field="geometry.slab_thickness"),
                _count(geometry.girder_count, field="geometry.girder_count"),
                _convert(geometry.girder_width, LENGTH_MM, field="geometry.girder_width"),
                _convert(geometry.girder_height, LENGTH_MM, field="geometry.girder_height"),
            ),
            material=RCBridgeMaterial(
                _convert(material.concrete_elastic_modulus, STRESS_MPA, field="material.concrete_elastic_modulus"),
                _convert(material.concrete_compressive_strength, STRESS_MPA, field="material.concrete_compressive_strength"),
                _convert(material.concrete_tensile_strength, STRESS_MPA, field="material.concrete_tensile_strength"),
                _convert(material.rebar_yield_strength, STRESS_MPA, field="material.rebar_yield_strength"),
                _convert(material.concrete_density, UNIT_WEIGHT, field="material.concrete_density"),
                _convert(material.minimum_reinforcement_ratio, DIMENSIONLESS, field="material.minimum_reinforcement_ratio"),
                _convert(material.maximum_reinforcement_ratio, DIMENSIONLESS, field="material.maximum_reinforcement_ratio"),
            ),
            reinforcement=RCBridgeReinforcement(
                _convert(reinforcement.cover, LENGTH_MM, field="reinforcement.cover"),
                _convert(reinforcement.slab_bar_diameter, LENGTH_MM, field="reinforcement.slab_bar_diameter"),
                _convert(reinforcement.slab_bar_spacing, LENGTH_MM, field="reinforcement.slab_bar_spacing"),
                _convert(reinforcement.girder_bottom_area, AREA_MM2, field="reinforcement.girder_bottom_area"),
                _convert(reinforcement.girder_top_area, AREA_MM2, field="reinforcement.girder_top_area"),
                _convert(reinforcement.girder_stirrup_area, AREA_MM2, field="reinforcement.girder_stirrup_area"),
                _convert(reinforcement.girder_stirrup_spacing, LENGTH_MM, field="reinforcement.girder_stirrup_spacing"),
            ),
            loads=RCBridgeLoads(
                tuple(
                    RCBridgeSpanLoad(
                        _convert(item.additional_dead, PRESSURE_KPA, field=f"loads.spans.{index}.additional_dead"),
                        _convert(item.crowd, PRESSURE_KPA, field=f"loads.spans.{index}.crowd"),
                    )
                    for index, item in enumerate(loads.spans)
                ),
                _convert(loads.railing_left, LINE_KN_M, field="loads.railing_left"),
                _convert(loads.railing_right, LINE_KN_M, field="loads.railing_right"),
                _convert(loads.wind_pressure, PRESSURE_KPA, field="loads.wind_pressure"),
                _convert(loads.wind_exposed_height, LENGTH_M, field="loads.wind_exposed_height"),
            ),
            supports=tuple(
                RCBridgeSupport(
                    item.id,
                    _count(item.node_index, field=f"supports.{item.id}.node_index"),
                    item.foundation_type,
                )
                for item in data.supports
            ),
            service_limits=RCBridgeServiceLimits(
                _convert(limits.crack_width_limit, LENGTH_MM, field="service_limits.crack_width_limit"),
                _convert(limits.minimum_vertical_frequency, FREQUENCY_HZ, field="service_limits.minimum_vertical_frequency"),
                _convert(limits.slab_deflection_ratio, DIMENSIONLESS, field="service_limits.slab_deflection_ratio"),
                _convert(limits.girder_deflection_ratio, DIMENSIONLESS, field="service_limits.girder_deflection_ratio"),
                _convert(limits.cracked_stiffness_factor, DIMENSIONLESS, field="service_limits.cracked_stiffness_factor"),
            ),
        )
    )
    checks = [
        _check(
            name=item.name,
            demand=item.demand,
            capacity=item.capacity,
            unit=item.unit,
            passed=item.passed,
            reference="RC板梁桥参数化筛查",
        )
        for item in solved.slab_checks + solved.girder_checks
    ]
    combinations: list[LoadCombinationResult] = []
    envelopes: list[ReactionEnvelope] = []
    reactions: dict[str, Quantity] = {}
    for item in solved.combinations:
        components = _components(
            n=-item.applied_vertical_kn,
            vx=-item.applied_wind_kn,
            my=-item.applied_wind_moment_kn_m,
            torsion=-item.applied_railing_torsion_kn_m,
        )
        combinations.append(
            LoadCombinationResult(
                name=item.id,
                combination_id=item.id,
                limit_state=item.limit_state,
                factors={
                    "permanent": item.permanent_factor,
                    "crowd": item.crowd_factor,
                    "wind": item.wind_factor,
                },
                factored_by_kind={},
                total=Quantity(value=item.applied_vertical_kn, unit="kN"),
                effect_components=components,  # type: ignore[arg-type]
            )
        )
    for reaction in solved.reactions:
        components = _components(
            n=reaction.n_kn,
            vx=reaction.vx_kn,
            vy=reaction.vy_kn,
            mx=reaction.mx_kn_m,
            my=reaction.my_kn_m,
            torsion=reaction.torsion_kn_m,
        )
        envelopes.append(
            ReactionEnvelope(
                name=reaction.support,
                limit_state=reaction.limit_state,
                combination_id=reaction.combination_id,
                combination_name=reaction.combination_id,
                direction=(LoadDirection.X_POSITIVE if reaction.vx_kn else LoadDirection.GRAVITY),
                components=components,  # type: ignore[arg-type]
            )
        )
        reactions[f"{reaction.combination_id}.{reaction.support}.N"] = Quantity(
            value=reaction.n_kn, unit="kN"
        )
    return _result(
        request,
        trace_id,
        checks=checks,
        combinations=combinations,
        reactions=reactions,
        envelopes=envelopes,
        input_summary={
            "span_count": Quantity(value=_count(geometry.span_count, field="geometry.span_count"), unit="1"),
            "system": "reinforced_concrete",
        },
        assumptions=["RC桥面板与等截面RC纵梁按参数化线弹性模型计算。"],
        applicability=list(solved.applicability) + list(solved.exclusions),
        step_name="全混凝土板梁人行桥",
    )


def calculate_gravity_retaining_wall(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: GravityRetainingWallInputs = _typed(
        request, GravityRetainingWallInputs
    )
    solved = solve_gravity_retaining_wall(
        GravityRetainingInput(
            combination_id=data.combination_id,
            combination_name=data.combination_name,
            limit_state=data.limit_state,
            retained_height_m=_convert(
                data.retained_height, LENGTH_M, field="retained_height"
            ),
            base_width_m=_convert(data.base_width, LENGTH_M, field="base_width"),
            base_slab_thickness_m=_convert(
                data.base_slab_thickness,
                LENGTH_M,
                field="base_slab_thickness",
            ),
            wall_bottom_thickness_m=_convert(
                data.wall_bottom_thickness,
                LENGTH_M,
                field="wall_bottom_thickness",
            ),
            wall_top_thickness_m=_convert(
                data.wall_top_thickness,
                LENGTH_M,
                field="wall_top_thickness",
            ),
            toe_projection_m=_convert(
                data.toe_projection, LENGTH_M, field="toe_projection"
            ),
            wall_unit_weight_kn_m3=_convert(
                data.wall_unit_weight, UNIT_WEIGHT, field="wall_unit_weight"
            ),
            soil_unit_weight_kn_m3=_convert(
                data.soil_unit_weight, UNIT_WEIGHT, field="soil_unit_weight"
            ),
            soil_friction_angle_deg=_convert(
                data.soil_friction_angle,
                ANGLE_DEG,
                field="soil_friction_angle",
            ),
            surcharge_kpa=_convert(data.surcharge, PRESSURE_KPA, field="surcharge"),
            base_friction_coefficient=_convert(
                data.base_friction_coefficient,
                DIMENSIONLESS,
                field="base_friction_coefficient",
            ),
            soil_bearing_capacity_kpa=_convert(
                data.soil_bearing_capacity,
                PRESSURE_KPA,
                field="soil_bearing_capacity",
            ),
            material_compressive_design_kpa=_convert(
                data.material_compressive_design,
                PRESSURE_KPA,
                field="material_compressive_design",
            ),
            water_depth_behind_m=_convert(
                data.water_depth_behind,
                LENGTH_M,
                field="water_depth_behind",
            ),
            water_unit_weight_kn_m3=_convert(
                data.water_unit_weight, UNIT_WEIGHT, field="water_unit_weight"
            ),
            uplift_head_toe_m=_convert(
                data.uplift_head_toe, LENGTH_M, field="uplift_head_toe"
            ),
            uplift_head_heel_m=_convert(
                data.uplift_head_heel, LENGTH_M, field="uplift_head_heel"
            ),
            sliding_safety_factor=_convert(
                data.sliding_safety_factor,
                DIMENSIONLESS,
                field="sliding_safety_factor",
            ),
            overturning_safety_factor=_convert(
                data.overturning_safety_factor,
                DIMENSIONLESS,
                field="overturning_safety_factor",
            ),
        )
    )
    checks = [
        _check(
            name=item.name,
            demand=item.demand.value,
            capacity=item.capacity.value,
            unit=item.demand.unit,
            passed=item.passed,
            reference=item.reference,
            combination=item.combination_id,
            note=item.note,
        )
        for item in solved.checks
    ]
    envelope = solved.reaction_envelopes[0]
    external_components = {
        key: Quantity(value=-value.value, unit=value.unit)
        for key, value in envelope.components.items()
    }
    combination = LoadCombinationResult(
        name=data.combination_name,
        combination_id=data.combination_id,
        limit_state=data.limit_state,
        factors={},
        factored_by_kind={},
        total=Quantity(value=solved.effective_vertical_kn_per_m, unit="kN/m"),
        effect_components=external_components,  # type: ignore[arg-type]
    )
    return _result(
        request,
        trace_id,
        checks=checks,
        combinations=[combination],
        reactions={
            "base.N": envelope.components["N"],
            "base.Vx": envelope.components["Vx"],
            "base.My": envelope.components["My"],
        },
        envelopes=[envelope],
        input_summary={
            "retained_height": Quantity(
                value=_convert(
                    data.retained_height, LENGTH_M, field="retained_height"
                ),
                unit="m",
            ),
            "wall_type": "gravity",
        },
        assumptions=list(solved.assumptions),
        applicability=list(solved.applicability)
        + [f"警告：{message}" for message in solved.warnings],
        step_name="重力式挡土墙每延米静力分析",
    )
