from __future__ import annotations

import ast
from math import pi
from pathlib import Path
from typing import Any

import pytest

from app.core import SCHEMA_VERSION
from app.core.engine import MODULE_VERIFICATION, calculate
from app.core.schemas import (
    CalculationModule,
    CalculationRequest,
    LoadDirection,
    LoadItem,
    LoadKind,
)
from verification.rc_geotech_evidence import (
    RC_GEOTECH_EVIDENCE,
    evidence_is_signed,
)
from verification.rc_geotech_references import (
    bar_area,
    cantilever_retaining_wall,
    effective_foundation_weight,
    masonry_wall_strip,
    rc_rectangular_column,
    rc_rectangular_flexure,
    rc_wall_cantilever,
    simple_span_udl,
    spread_footing_pressure,
    strip_footing_pressure,
    threshold_passes,
)


MODULES = (
    CalculationModule.CONCRETE_BEAM,
    CalculationModule.CONCRETE_SLAB,
    CalculationModule.CONCRETE_COLUMN,
    CalculationModule.MASONRY_WALL,
    CalculationModule.RC_WALL,
    CalculationModule.SPREAD_FOOTING,
    CalculationModule.STRIP_FOOTING,
    CalculationModule.RETAINING_WALL,
)


def _load(
    *,
    kind: LoadKind,
    value: float,
    unit: str,
    direction: LoadDirection = LoadDirection.GRAVITY,
) -> LoadItem:
    values: dict[str, Any] = {
        "kind": kind,
        "value": value,
        "unit": unit,
        "source": "RC/geotechnical independent golden case",
        "direction": direction,
    }
    # Schema <=3.1 requires explicit confirmation.  Newer schemas remove this
    # UX gate; retaining this compatibility branch keeps old snapshots testable.
    if "confirmed" in LoadItem.model_fields:
        values["confirmed"] = True
    return LoadItem.model_validate(values)


def _request(
    module: CalculationModule,
    inputs: dict[str, Any],
    loads: list[LoadItem],
) -> CalculationRequest:
    values: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "quick",
        "module": module,
        "project_name": "RC/geotechnical independent golden case",
        "inputs": inputs,
        "loads": loads,
    }
    if "confirmed_assumptions" in CalculationRequest.model_fields:
        values["confirmed_assumptions"] = True
    return CalculationRequest.model_validate(values)


def _check(result: Any, name: str) -> Any:
    return next(item for item in result.checks if item.name == name)


def test_evidence_inventory_is_complete_but_unsigned() -> None:
    assert set(RC_GEOTECH_EVIDENCE) == {module.value for module in MODULES}
    for module in MODULES:
        record = RC_GEOTECH_EVIDENCE[module.value]
        assert record.applicability
        assert record.excluded_scope
        assert record.formula_mappings
        assert record.golden_case
        assert record.independent_reference
        assert record.boundary_cases
        assert record.open_gaps
        assert record.reviewer is None
        assert record.review_date is None
        assert not evidence_is_signed(record)
        assert MODULE_VERIFICATION[module] == "unverified"


def test_independent_reference_has_no_production_imports() -> None:
    source_path = (
        Path(__file__).parents[1] / "verification" / "rc_geotech_references.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(name == "app" or name.startswith("app.") for name in imported_modules)


@pytest.mark.parametrize("module", [item.value for item in MODULES])
def test_every_module_has_exact_099_101_threshold_fixture(module: str) -> None:
    assert module in RC_GEOTECH_EVIDENCE
    assert threshold_passes(demand=99.0, capacity=100.0)
    assert not threshold_passes(demand=101.0, capacity=100.0)


def test_concrete_beam_matches_independent_actions_and_flexure() -> None:
    result = calculate(
        _request(
            CalculationModule.CONCRETE_BEAM,
            {
                "span_m": 3.0,
                "support": "simple",
                "b_mm": 250,
                "h_mm": 450,
                "cover_mm": 30,
                "bar_dia_mm": 18,
                "bar_count": 3,
                "concrete_grade": "C30",
                "rebar_grade": "HRB400",
                "stirrup_grade": "HPB300",
                "stirrup_dia_mm": 8,
                "stirrup_legs": 2,
                "stirrup_spacing_mm": 200,
                "tributary_width_m": 1.0,
            },
            [_load(kind=LoadKind.DEAD, value=2.0, unit="kN/m2")],
        )
    )
    steel_area = bar_area(diameter_mm=18, count=3)
    flexure = rc_rectangular_flexure(
        width_mm=250,
        effective_depth_mm=450 - 30 - 18 / 2,
        steel_area_mm2=steel_area,
        concrete_design_strength_mpa=14.3,
        steel_design_strength_mpa=360,
        limiting_axis_ratio=0.518,
    )
    design_line = 1.3 * (2.0 + 25.0 * 0.25 * 0.45)
    service_line = 2.0 + 25.0 * 0.25 * 0.45
    design_actions = simple_span_udl(line_load_kn_m=design_line, span_m=3.0)
    service_actions = simple_span_udl(line_load_kn_m=service_line, span_m=3.0)
    assert _check(result, "受弯承载力").demand.value == pytest.approx(
        design_actions.moment_kn_m
    )
    assert _check(result, "受弯承载力").capacity.value == pytest.approx(
        flexure.moment_capacity_kn_m
    )
    assert result.reactions["left_vertical"].value == pytest.approx(
        service_actions.reaction_kn
    )


def test_concrete_slab_matches_independent_one_metre_strip() -> None:
    result = calculate(
        _request(
            CalculationModule.CONCRETE_SLAB,
            {
                "span_m": 3.0,
                "support": "simple",
                "h_mm": 150,
                "cover_mm": 20,
                "bar_dia_mm": 12,
                "bar_spacing_mm": 150,
                "concrete_grade": "C30",
                "rebar_grade": "HRB400",
            },
            [_load(kind=LoadKind.DEAD, value=1.0, unit="kN/m2")],
        )
    )
    steel_area = 1000.0 / 150.0 * bar_area(diameter_mm=12)
    flexure = rc_rectangular_flexure(
        width_mm=1000,
        effective_depth_mm=150 - 20 - 12 / 2,
        steel_area_mm2=steel_area,
        concrete_design_strength_mpa=14.3,
        steel_design_strength_mpa=360,
        limiting_axis_ratio=0.518,
    )
    design_actions = simple_span_udl(
        line_load_kn_m=1.3 * (1.0 + 25.0 * 0.15), span_m=3.0
    )
    assert _check(result, "受弯承载力").demand.value == pytest.approx(
        design_actions.moment_kn_m
    )
    assert _check(result, "受弯承载力").capacity.value == pytest.approx(
        flexure.moment_capacity_kn_m
    )
    expected_shear_capacity = 0.7 * 1.43 * 1000 * (150 - 20 - 6) / 1000
    assert _check(result, "受剪承载力").capacity.value == pytest.approx(
        expected_shear_capacity
    )


def test_concrete_column_matches_independent_rectangular_reference() -> None:
    result = calculate(
        _request(
            CalculationModule.CONCRETE_COLUMN,
            {
                "shape": "rectangular",
                "b_mm": 300,
                "h_mm": 300,
                "height_m": 3.0,
                "effective_length_factor": 1.0,
                "reinforcement_area_mm2": 1608,
                "design_moment_kn_m": 20,
                "concrete_grade": "C30",
                "rebar_grade": "HRB400",
            },
            [_load(kind=LoadKind.DEAD, value=100, unit="kN")],
        )
    )
    reference = rc_rectangular_column(
        width_mm=300,
        depth_mm=300,
        height_m=3.0,
        effective_length_factor=1.0,
        steel_area_mm2=1608,
        concrete_design_strength_mpa=14.3,
        steel_design_strength_mpa=360,
        axial_demand_kn=130,
        moment_demand_kn_m=20,
    )
    assert _check(result, "轴压承载力").capacity.value == pytest.approx(
        reference.axial_capacity_kn
    )
    assert _check(result, "偏压相互作用筛查").utilization == pytest.approx(
        reference.interaction
    )


def test_masonry_wall_matches_independent_wall_strip() -> None:
    result = calculate(
        _request(
            CalculationModule.MASONRY_WALL,
            {"height_m": 2.0, "column_spacing_m": 3.0, "thickness_mm": 240},
            [
                _load(
                    kind=LoadKind.WIND,
                    value=0.5,
                    unit="kN/m2",
                    direction=LoadDirection.X_POSITIVE,
                )
            ],
        )
    )
    reference = masonry_wall_strip(
        pressure_kpa=0.5,
        height_m=2.0,
        support_spacing_m=3.0,
        thickness_mm=240,
    )
    assert result.steps[0].result.value == pytest.approx(reference.line_load_kn_m)
    assert _check(result, "砌体墙片平面外弯曲").demand.value == pytest.approx(
        reference.bending_stress_mpa
    )
    assert _check(result, "墙片剪力").demand.value == pytest.approx(
        reference.shear_kn
    )


def test_rc_wall_matches_independent_wind_and_soil_reference() -> None:
    result = calculate(
        _request(
            CalculationModule.RC_WALL,
            {
                "height_m": 1.2,
                "thickness_mm": 180,
                "strip_width_m": 1.0,
                "bar_dia_mm": 12,
                "bar_spacing_mm": 200,
                "concrete_grade": "C30",
                "soil_height_m": 0.8,
                "soil_unit_weight_kn_m3": 18,
                "soil_friction_angle_deg": 30,
                "soil_surcharge_kpa": 2,
            },
            [
                _load(
                    kind=LoadKind.WIND,
                    value=0.3,
                    unit="kN/m2",
                    direction=LoadDirection.X_POSITIVE,
                )
            ],
        )
    )
    reference = rc_wall_cantilever(
        wind_pressure_kpa=0.3,
        wall_height_m=1.2,
        wall_thickness_mm=180,
        strip_width_m=1.0,
        bar_diameter_mm=12,
        bar_spacing_mm=200,
        soil_height_m=0.8,
        soil_unit_weight_kn_m3=18,
        friction_angle_deg=30,
        surcharge_kpa=2,
    )
    assert result.reactions["base_horizontal"].value == pytest.approx(
        reference.horizontal_force_kn_m
    )
    assert result.reactions["base_moment"].value == pytest.approx(
        reference.base_moment_kn_m_m
    )
    assert _check(result, "墙身受弯").capacity.value == pytest.approx(
        reference.flexural_capacity_kn_m_m
    )
    assert _check(result, "墙身受剪").capacity.value == pytest.approx(
        reference.shear_capacity_kn
    )


def test_rc_wall_rejects_reinforcement_below_the_independent_minimum() -> None:
    result = calculate(
        _request(
            CalculationModule.RC_WALL,
            {
                "height_m": 1.2,
                "thickness_mm": 180,
                "bar_dia_mm": 6,
                "bar_spacing_mm": 400,
            },
            [],
        )
    )
    provided = 1000 / 400 * pi * 6**2 / 4
    required = 0.0015 * 1000 * 180
    check = _check(result, "最小配筋")
    assert provided < required
    assert check.demand.value == pytest.approx(required)
    assert check.capacity.value == pytest.approx(provided)
    assert check.utilization == pytest.approx(required / provided)
    assert not check.passed


@pytest.mark.parametrize(
    ("provided_to_minimum", "expected_passed"),
    [(0.99, False), (1.01, True)],
)
def test_rc_wall_minimum_reinforcement_flips_at_unity(
    provided_to_minimum: float,
    expected_passed: bool,
) -> None:
    thickness = 180.0
    bar_diameter = 10.0
    required = 0.0015 * 1000 * thickness
    bar_area = pi * bar_diameter**2 / 4
    spacing = 1000 * bar_area / (required * provided_to_minimum)
    result = calculate(
        _request(
            CalculationModule.RC_WALL,
            {
                "height_m": 1.2,
                "thickness_mm": thickness,
                "bar_dia_mm": bar_diameter,
                "bar_spacing_mm": spacing,
            },
            [],
        )
    )
    check = _check(result, "最小配筋")

    assert check.demand.value == pytest.approx(required)
    assert check.capacity.value == pytest.approx(required * provided_to_minimum)
    assert check.utilization == pytest.approx(1 / provided_to_minimum)
    assert check.passed is expected_passed


def test_spread_footing_matches_independent_pressure_and_punching_geometry() -> None:
    inputs = {
        "length_m": 2.0,
        "width_m": 2.0,
        "thickness_mm": 500,
        "column_x_mm": 300,
        "column_y_mm": 300,
        "cover_mm": 50,
        "bar_dia_x_mm": 14,
        "bar_dia_y_mm": 14,
        "spacing_x_mm": 150,
        "spacing_y_mm": 150,
        "concrete_grade": "C30",
        "rebar_grade": "HRB400",
        "soil_capacity_kpa": 120,
        "base_friction_coefficient": 0.3,
        "embedment_m": 1.0,
        "soil_cover_m": 0.5,
        "moment_x_kn_m": 10,
        "moment_y_kn_m": 20,
    }
    result = calculate(
        _request(
            CalculationModule.SPREAD_FOOTING,
            inputs,
            [_load(kind=LoadKind.DEAD, value=100, unit="kN")],
        )
    )
    weights = effective_foundation_weight(
        plan_area_m2=4.0,
        thickness_m=0.5,
        embedment_m=1.0,
        soil_cover_m=0.5,
        groundwater_depth_m=5.0,
    )
    reference = spread_footing_pressure(
        service_column_load_kn=100,
        footing_weight_kn=weights.footing_kn + weights.cover_kn,
        length_m=2.0,
        width_m=2.0,
        moment_x_kn_m=10,
        moment_y_kn_m=20,
        column_x_mm=300,
        column_y_mm=300,
        effective_depth_mm=500 - 50 - 14 / 2,
    )
    assert result.reactions["N_service"].value == pytest.approx(
        reference.service_vertical_kn
    )
    assert _check(result, "地基承载力").demand.value == pytest.approx(
        reference.maximum_pressure_kpa
    )
    expected_punching_capacity = (
        0.7 * 1.43 * reference.punching_perimeter_mm * (500 - 50 - 7) / 1000
    )
    assert _check(result, "柱边冲切").capacity.value == pytest.approx(
        expected_punching_capacity
    )


def test_strip_footing_matches_independent_signed_eccentricity() -> None:
    result = calculate(
        _request(
            CalculationModule.STRIP_FOOTING,
            {
                "width_m": 1.2,
                "thickness_mm": 400,
                "wall_width_mm": 240,
                "wall_eccentricity_mm": -50,
                "moment_kn_m_per_m": 10,
                "embedment_m": 0.6,
                "soil_cover_m": 0,
                "soil_capacity_kpa": 120,
            },
            [_load(kind=LoadKind.DEAD, value=100, unit="kN/m")],
        )
    )
    weights = effective_foundation_weight(
        plan_area_m2=1.2,
        thickness_m=0.4,
        embedment_m=0.6,
        soil_cover_m=0,
        groundwater_depth_m=5.0,
    )
    reference = strip_footing_pressure(
        service_wall_load_kn_m=100,
        footing_weight_kn_m=weights.footing_kn,
        width_m=1.2,
        applied_moment_kn_m_m=10,
        wall_eccentricity_mm=-50,
    )
    assert result.reactions["N_service"].value == pytest.approx(
        reference.service_vertical_kn_m
    )
    pressure_step = next(step for step in result.steps if step.name == "偏心受压边缘压力")
    assert pressure_step.result.value == pytest.approx(
        max(reference.left_pressure_kpa, reference.right_pressure_kpa)
    )


def test_retaining_wall_matches_independent_soil_water_and_base_pressure() -> None:
    result = calculate(
        _request(
            CalculationModule.RETAINING_WALL,
            {
                "retained_height_m": 1.5,
                "stem_thickness_mm": 200,
                "base_width_m": 1.6,
                "toe_length_m": 0.45,
                "base_thickness_m": 0.35,
                "soil_unit_weight_kn_m3": 18,
                "soil_friction_angle_deg": 30,
                "surcharge_kpa": 5,
                "water_level_depth_m": 0.6,
                "submerged_depth_m": 0.2,
                "soil_capacity_kpa": 120,
                "base_friction_coefficient": 0.35,
                "stem_moment_capacity_kn_m_per_m": 80,
            },
            [],
        )
    )
    reference = cantilever_retaining_wall(
        retained_height_m=1.5,
        stem_thickness_m=0.2,
        base_width_m=1.6,
        toe_length_m=0.45,
        base_thickness_m=0.35,
        soil_unit_weight_kn_m3=18,
        friction_angle_deg=30,
        surcharge_kpa=5,
        water_depth_m=0.6,
    )
    assert result.reactions["base_vertical"].value == pytest.approx(
        reference.vertical_force_kn_m
    )
    assert result.reactions["base_horizontal"].value == pytest.approx(
        reference.horizontal_force_kn_m
    )
    assert result.reactions["base_moment"].value == pytest.approx(
        reference.overturning_moment_kn_m_m
    )
    assert _check(result, "基底承载力").demand.value == pytest.approx(
        max(reference.maximum_pressure_kpa, 0)
    )


@pytest.mark.parametrize(
    ("call", "kwargs"),
    [
        (simple_span_udl, {"line_load_kn_m": 1, "span_m": 0}),
        (
            rc_rectangular_flexure,
            {
                "width_mm": 0,
                "effective_depth_mm": 400,
                "steel_area_mm2": 1000,
                "concrete_design_strength_mpa": 14.3,
                "steel_design_strength_mpa": 360,
                "limiting_axis_ratio": 0.518,
            },
        ),
        (
            rc_rectangular_column,
            {
                "width_mm": 300,
                "depth_mm": 300,
                "height_m": 3,
                "effective_length_factor": 1,
                "steel_area_mm2": 100000,
                "concrete_design_strength_mpa": 14.3,
                "steel_design_strength_mpa": 360,
                "axial_demand_kn": 100,
                "moment_demand_kn_m": 0,
            },
        ),
        (
            masonry_wall_strip,
            {"pressure_kpa": -0.1, "height_m": 2, "support_spacing_m": 3, "thickness_mm": 240},
        ),
        (
            rc_wall_cantilever,
            {"wind_pressure_kpa": 0.3, "wall_height_m": 1, "wall_thickness_mm": 180, "strip_width_m": 1, "bar_diameter_mm": 12, "bar_spacing_mm": 200, "soil_height_m": 1.1},
        ),
        (
            effective_foundation_weight,
            {"plan_area_m2": 4, "thickness_m": 0.5, "embedment_m": 1, "soil_cover_m": 0.5, "groundwater_depth_m": -0.1},
        ),
        (
            spread_footing_pressure,
            {"service_column_load_kn": -100, "footing_weight_kn": 50, "length_m": 2, "width_m": 2, "moment_x_kn_m": 0, "moment_y_kn_m": 0, "column_x_mm": 300, "column_y_mm": 300, "effective_depth_mm": 440},
        ),
        (
            cantilever_retaining_wall,
            {"retained_height_m": 1.5, "stem_thickness_m": 0.2, "base_width_m": 1.6, "toe_length_m": 0.45, "base_thickness_m": 0.35, "soil_unit_weight_kn_m3": 18, "friction_angle_deg": 30, "surcharge_kpa": 0, "water_depth_m": 2},
        ),
    ],
)
def test_independent_references_reject_out_of_scope_inputs(call: Any, kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        call(**kwargs)
