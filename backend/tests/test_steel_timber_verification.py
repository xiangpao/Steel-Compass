from __future__ import annotations

import inspect

import pytest

from app.core.engine import MODULE_VERIFICATION, calculate
from app.core.schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    LoadDirection,
    LoadItem,
    LoadKind,
)
from verification.steel_timber_evidence import EVIDENCE_RECORDS
from verification.steel_timber_references import (
    screening_passes,
    solve_baseplate_anchor,
    solve_cantilever_post,
    solve_hollow_rect_section,
    solve_steel_column,
    solve_symmetric_portal_equilibrium,
    solve_timber_column,
    solve_udl_beam,
)


MODULES = tuple(EVIDENCE_RECORDS)


def _request(module: CalculationModule, inputs: dict, loads: list[LoadItem]) -> CalculationRequest:
    return CalculationRequest(
        mode=CalculationMode.QUICK,
        module=module,
        project_name=f"verification-{module.value}",
        confirmed_assumptions=True,
        inputs=inputs,
        loads=loads,
    )


def _check(result, name: str):
    return next(item for item in result.checks if item.name == name)


def test_reference_module_has_no_production_engine_imports() -> None:
    from verification import steel_timber_references

    source = inspect.getsource(steel_timber_references)
    assert "app.core" not in source


def test_evidence_manifest_is_complete_and_verified() -> None:
    assert set(EVIDENCE_RECORDS) == {
        "steel_beam",
        "steel_column",
        "portal_frame",
        "steel_baseplate_anchor",
        "steel_cantilever_post",
        "timber_beam",
        "timber_column",
        "timber_deck_panel",
    }
    for module, record in EVIDENCE_RECORDS.items():
        assert record.module == module
        if module in ("steel_beam", "steel_column", "portal_frame", "steel_baseplate_anchor"):
            assert record.verification_status == "verified"
            assert record.reviewer == "Advanced Structural Engineering Audit Group"
            assert record.review_date == "2026-08-07"
        assert record.applicability
        assert record.formula_mapping
        assert record.standard_mapping
        assert record.golden_case
        assert record.boundary_cases


@pytest.mark.parametrize("module", MODULES)
def test_099_101_screening_flip_framework(module: str) -> None:
    # The module parameter makes the same exact boundary oracle an explicit
    # release-gate entry for every evidence record.
    assert module in EVIDENCE_RECORDS
    assert screening_passes(demand=99.0, capacity=100.0)
    assert screening_passes(demand=100.0, capacity=100.0)
    assert not screening_passes(demand=101.0, capacity=100.0)


def test_steel_beam_golden_case_matches_production_mechanics() -> None:
    result = calculate(
        _request(
            CalculationModule.STEEL_BEAM,
            {
                "steel_grade": "Q355B",
                "section_type": "CUSTOM",
                "section_name": "verification section",
                "area_mm2": 10_000,
                "ix_mm4": 1_500_000_000,
                "iy_mm4": 100_000_000,
                "wx_mm3": 15_000_000,
                "wy_mm3": 2_000_000,
                "depth_mm": 200,
                "width_mm": 100,
                "shear_area_mm2": 5_000,
                "local_slenderness": 0,
                "t_mm": 6,
                "span_m": 10,
                "support": "simple",
                "tributary_width_m": 1,
                "include_self_weight": False,
                "lateral_restrained": True,
            },
            [LoadItem(kind=LoadKind.DEAD, value=10, unit="kN/m", source="golden")],
        )
    )
    uls = max(
        (item for item in result.combinations if item.limit_state == "ULS"),
        key=lambda item: abs(item.total.value),
    )
    sls = next(
        item
        for item in result.combinations
        if item.limit_state == "SLS" and item.sls_type == "standard"
    )
    reference = solve_udl_beam(
        support="simple",
        uls_line_load_kn_m=abs(uls.total.value),
        sls_line_load_kn_m=abs(sls.total.value),
        span_m=10,
        elastic_modulus_mpa=206_000,
        inertia_mm4=1_500_000_000,
        section_modulus_mm3=15_000_000,
        shear_area_mm2=5_000,
        bending_strength_mpa=305,
        shear_strength_mpa=175,
    )
    assert _check(result, "抗弯承载力").demand.value == pytest.approx(reference.maximum_moment_kn_m)
    assert _check(result, "抗剪承载力").demand.value == pytest.approx(reference.maximum_shear_kn)
    assert _check(result, "挠度").demand.value == pytest.approx(reference.maximum_deflection_mm)
    assert reference.maximum_deflection_mm == pytest.approx(4.21386, rel=1e-5)


def test_steel_column_golden_case_matches_current_bounded_method() -> None:
    section = solve_hollow_rect_section(depth_mm=180, width_mm=180, thickness_mm=8)
    result = calculate(
        _request(
            CalculationModule.STEEL_COLUMN,
            {
                "steel_grade": "Q355B",
                "section_type": "SHS",
                "b_mm": 180,
                "t_mm": 8,
                "height_m": 3,
                "effective_length_factor": 1,
                "design_moment_kn_m": 8,
            },
            [LoadItem(kind=LoadKind.DEAD, value=100, unit="kN", source="golden")],
        )
    )
    axial = max(
        (item for item in result.combinations if item.limit_state == "ULS"),
        key=lambda item: abs(item.total.value),
    ).total.value
    reference = solve_steel_column(
        axial_kn=abs(axial),
        moment_kn_m=8,
        height_m=3,
        effective_length_factor=1,
        area_mm2=section.area_mm2,
        minimum_radius_mm=min(section.rx_mm, section.ry_mm),
        section_modulus_mm3=section.wx_mm3,
        design_strength_mpa=305,
        yield_strength_mpa=355,
    )
    assert _check(result, "轴压稳定承载力").capacity.value == pytest.approx(reference.axial_capacity_kn)
    assert _check(result, "长细比").demand.value == pytest.approx(reference.slenderness)
    assert _check(result, "压弯组合").demand.value == pytest.approx(reference.interaction)


def test_portal_frame_golden_case_satisfies_independent_equilibrium() -> None:
    result = calculate(
        _request(
            CalculationModule.PORTAL_FRAME,
            {
                "steel_grade": "Q355B",
                "span_m": 5,
                "height_m": 3,
                "base_support": "fixed",
                "wind_area_m2": 15,
                "beam_section": {"section_type": "RHS", "h_mm": 300, "b_mm": 150, "t_mm": 6},
                "column_section": {"section_type": "SHS", "b_mm": 180, "t_mm": 8},
            },
            [LoadItem(kind=LoadKind.DEAD, value=2, unit="kN/m", source="golden")],
        )
    )
    sls_combo = next(
        item
        for item in result.combinations
        if item.limit_state == "SLS" and item.sls_type == "standard"
    )
    reference = solve_symmetric_portal_equilibrium(line_load_kn_m=abs(sls_combo.total.value), span_m=5)
    sls_reactions = [
        item
        for item in result.reaction_envelopes
        if item.limit_state == "SLS"
        and item.combination_id == sls_combo.combination_id
    ]
    assert sum(item.components["N"].value for item in sls_reactions) == pytest.approx(reference.total_vertical_load_kn, rel=1e-8)
    assert sls_reactions[0].components["N"].value == pytest.approx(reference.reaction_left_kn, rel=1e-8)
    assert sls_reactions[1].components["N"].value == pytest.approx(reference.reaction_right_kn, rel=1e-8)


def test_baseplate_golden_case_matches_independent_strip_and_anchor_group() -> None:
    upstream = [
        {
            "name": "left_base",
            "limit_state": "ULS",
            "combination_name": "ULS-wind-leading",
            "direction": "gravity",
            "components": {
                "N": {"value": 105, "unit": "kN"},
                "Vx": {"value": 8, "unit": "kN"},
                "My": {"value": 14, "unit": "kN·m"},
            },
        }
    ]
    result = calculate(
        _request(
            CalculationModule.STEEL_BASEPLATE_ANCHOR,
            {
                "plate_length_mm": 360,
                "plate_width_mm": 360,
                "plate_thickness_mm": 24,
                "column_depth_mm": 200,
                "column_width_mm": 200,
                "steel_grade": "Q355B",
                "concrete_bearing_capacity_mpa": 10,
                "anchor_count": 4,
                "anchor_diameter_mm": 20,
                "anchor_grade": "5.8",
                "anchor_spacing_mm": 260,
                "anchor_edge_mm": 50,
                "weld_throat_mm": 8,
                "upstream_reaction_envelopes": upstream,
            },
            [],
        )
    )
    reference = solve_baseplate_anchor(
        axial_kn=105,
        shear_x_kn=8,
        shear_y_kn=0,
        moment_x_kn_m=0,
        moment_y_kn_m=14,
        plate_length_mm=360,
        plate_width_mm=360,
        plate_thickness_mm=24,
        column_depth_mm=200,
        column_width_mm=200,
        anchor_count=4,
        anchor_diameter_mm=20,
        anchor_spacing_mm=260,
        anchor_fu_mpa=500,
        plate_design_strength_mpa=295,
        weld_throat_mm=8,
        weld_shear_strength_mpa=170,
    )
    assert _check(result, "底板下混凝土局部承压（快算）").demand.value == pytest.approx(reference.bearing_pressure_mpa)
    assert _check(result, "底板悬臂弯曲").demand.value == pytest.approx(reference.plate_stress_mpa)
    assert _check(result, "锚栓钢材拉剪组合").demand.value == pytest.approx(reference.anchor_interaction)
    assert _check(result, "柱底角焊缝承载力（快算）").capacity.value == pytest.approx(reference.weld_capacity_kn)


def test_cantilever_post_golden_case_matches_static_equilibrium() -> None:
    result = calculate(
        _request(
            CalculationModule.STEEL_CANTILEVER_POST,
            {
                "steel_grade": "Q355B",
                "section_type": "SHS",
                "b_mm": 180,
                "t_mm": 8,
                "height_m": 2.8,
                "panel_area_m2": 1.5,
                "panel_cg_height_m": 2.1,
                "panel_eccentricity_m": 0.2,
            },
            [LoadItem(kind=LoadKind.WIND, value=0.6, unit="kN/m2", source="golden", direction=LoadDirection.X_POSITIVE)],
        )
    )
    reference = solve_cantilever_post(force_kn=0.9, lever_arm_m=2.1, eccentricity_m=0.2)
    assert result.reactions["base_horizontal"].value == pytest.approx(reference.shear_kn)
    assert result.reactions["base_moment"].value == pytest.approx(reference.moment_kn_m)
    sls = next(
        item
        for item in result.reaction_envelopes
        if item.limit_state == "SLS" and item.sls_type == "standard"
    )
    sls_reference = solve_cantilever_post(
        force_kn=abs(sls.components["Vx"].value),
        lever_arm_m=2.1,
        eccentricity_m=0.2,
    )
    assert sls.components["T"].value == pytest.approx(sls_reference.torsion_kn_m)


@pytest.mark.parametrize(
    ("module", "inputs", "load", "support", "e", "fm", "fv"),
    [
        (CalculationModule.TIMBER_BEAM, {"timber_grade": "TC13", "b_mm": 100, "h_mm": 200, "span_m": 3, "support": "simple", "tributary_width_m": 1}, 2.0, "simple", 9_000, 13.0, 1.4),
        (CalculationModule.TIMBER_DECK_PANEL, {"timber_grade": "TC13", "span_m": 1.2, "thickness_mm": 50, "strip_width_m": 1.0}, 2.0, "simple", 9_000, 13.0, 1.4),
    ],
)
def test_timber_beam_and_deck_golden_cases_match_closed_form(module, inputs, load, support, e, fm, fv) -> None:
    result = calculate(_request(module, inputs, [LoadItem(kind=LoadKind.LIVE, value=load, unit="kN/m2", source="golden")]))
    uls = max((item for item in result.combinations if item.limit_state == "ULS"), key=lambda item: abs(item.total.value))
    sls = max((item for item in result.combinations if item.limit_state == "SLS"), key=lambda item: abs(item.total.value))
    if module is CalculationModule.TIMBER_BEAM:
        width, depth, span = 100.0, 200.0, 3.0
        names = ("抗弯承载力", "抗剪承载力", "挠度")
    else:
        width, depth, span = 1000.0, 50.0, 1.2
        names = ("铺板抗弯", "铺板抗剪", "铺板挠度")
    inertia = width * depth**3 / 12
    reference = solve_udl_beam(
        support=support,
        uls_line_load_kn_m=abs(uls.total.value),
        sls_line_load_kn_m=abs(sls.total.value),
        span_m=span,
        elastic_modulus_mpa=e,
        inertia_mm4=inertia,
        section_modulus_mm3=width * depth**2 / 6,
        shear_area_mm2=2 * width * depth / 3,
        bending_strength_mpa=fm,
        shear_strength_mpa=fv,
    )
    assert _check(result, names[0]).demand.value == pytest.approx(reference.maximum_moment_kn_m)
    assert _check(result, names[1]).demand.value == pytest.approx(reference.maximum_shear_kn)
    assert _check(result, names[2]).demand.value == pytest.approx(reference.maximum_deflection_mm)


def test_timber_column_golden_case_matches_current_bounded_method() -> None:
    result = calculate(
        _request(
            CalculationModule.TIMBER_COLUMN,
            {"timber_grade": "TC13", "b_mm": 120, "h_mm": 120, "height_m": 2.8, "effective_length_factor": 1.0},
            [LoadItem(kind=LoadKind.DEAD, value=20, unit="kN", source="golden")],
        )
    )
    axial = max(
        (item for item in result.combinations if item.limit_state == "ULS"),
        key=lambda item: abs(item.total.value),
    ).total.value
    reference = solve_timber_column(
        axial_kn=abs(axial),
        width_mm=120,
        depth_mm=120,
        height_m=2.8,
        effective_length_factor=1,
        elastic_modulus_mpa=9_000,
        compression_strength_mpa=10,
    )
    assert _check(result, "轴压稳定承载力").capacity.value == pytest.approx(reference.axial_capacity_kn)
    assert _check(result, "长细比").demand.value == pytest.approx(reference.slenderness)


@pytest.mark.parametrize(
    "call",
    [
        lambda: solve_hollow_rect_section(depth_mm=20, width_mm=20, thickness_mm=10),
        lambda: solve_udl_beam(support="simple", uls_line_load_kn_m=-1, sls_line_load_kn_m=1, span_m=1, elastic_modulus_mpa=1, inertia_mm4=1, section_modulus_mm3=1, shear_area_mm2=1, bending_strength_mpa=1, shear_strength_mpa=1),
        lambda: solve_timber_column(axial_kn=1, width_mm=100, depth_mm=100, height_m=0, effective_length_factor=1, elastic_modulus_mpa=9_000, compression_strength_mpa=10),
        lambda: solve_baseplate_anchor(axial_kn=1, shear_x_kn=0, shear_y_kn=0, moment_x_kn_m=0, moment_y_kn_m=0, plate_length_mm=300, plate_width_mm=300, plate_thickness_mm=20, column_depth_mm=200, column_width_mm=200, anchor_count=5, anchor_diameter_mm=20, anchor_spacing_mm=200, anchor_fu_mpa=500, plate_design_strength_mpa=295, weld_throat_mm=6, weld_shear_strength_mpa=170),
        lambda: solve_cantilever_post(force_kn=1, lever_arm_m=-1),
        lambda: screening_passes(demand=-1, capacity=1),
    ],
)
def test_reference_boundaries_reject_out_of_domain_inputs(call) -> None:
    with pytest.raises(ValueError):
        call()


def test_production_verification_gate_is_unchanged() -> None:
    for module_name in MODULES:
        assert MODULE_VERIFICATION[CalculationModule(module_name)] == "unverified"
