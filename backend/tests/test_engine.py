from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.engine import calculate
from app.core.errors import CalculationInputError
from app.core.scenarios import SCENARIOS
from app.core.schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    LoadItem,
    LoadDirection,
    LoadKind,
)


def scenario_request(index: int) -> CalculationRequest:
    scenario = SCENARIOS[index]
    return CalculationRequest(
        mode=CalculationMode.QUICK,
        module=scenario.module,
        project_name=scenario.title,
        confirmed_assumptions=True,
        inputs=scenario.inputs,
        loads=scenario.loads,
    )


@pytest.mark.parametrize("index", range(len(SCENARIOS)))
def test_all_quick_scenarios_are_calculable(index: int) -> None:
    result = calculate(scenario_request(index))
    assert result.trace_id
    assert result.checks
    assert result.governing_check
    assert result.status in {"passed", "failed"}
    assert all(item.demand.unit for item in result.checks)


def test_simple_steel_beam_matches_hand_calculation() -> None:
    request = CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
        project_name="benchmark",
        confirmed_assumptions=True,
        inputs={
            "steel_grade": "Q355B",
            "section_type": "RHS",
            "h_mm": 200,
            "b_mm": 100,
            "t_mm": 6,
            "span_m": 4,
            "support": "simple",
            "tributary_width_m": 1,
            "include_self_weight": False,
            "lateral_restrained": True,
        },
        loads=[
            LoadItem(kind=LoadKind.DEAD, value=2, unit="kN/m", source="test")
        ],
    )
    result = calculate(request)
    bending_step = next(item for item in result.steps if item.name == "最大弯矩")
    # ULS: 1.3 * 2.0 = 2.6 kN/m; M=qL²/8=5.2 kN·m.
    assert bending_step.result.value == pytest.approx(5.2)
    # Legacy reaction output is characteristic/SLS so a downstream node can
    # apply its own combination exactly once; ULS remains in reaction_envelopes.
    assert result.reactions["left_vertical"].value == pytest.approx(4.0)
    uls_left = next(
        item
        for item in result.reaction_envelopes
        if item.name == "left_support" and item.limit_state == "ULS"
    )
    assert uls_left.components["Vy"].value == pytest.approx(5.2)


def test_skyciv_public_beam_deflection_example_with_engine_modulus() -> None:
    """Cross-check the public SkyCiv 10 m / 10 kN/m beam example.

    SkyCiv publishes E=200 GPa, I=0.0015 m4 and 4.34 mm.  The engine uses
    the Chinese structural-steel modulus E=206 GPa, so the same mechanical
    model must return 4.21386 mm.  This compares mechanics only, not a foreign
    design-code resistance check.
    Source: https://skyciv.com/docs/tutorials/beam-tutorials/what-is-deflection/
    """
    request = CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BEAM,
        project_name="SkyCiv public deflection benchmark",
        confirmed_assumptions=True,
        inputs={
            "steel_grade": "Q355B",
            "section_type": "CUSTOM",
            "section_name": "SkyCiv benchmark section",
            "area_mm2": 10000,
            "ix_mm4": 1_500_000_000,
            "iy_mm4": 100_000_000,
            "wx_mm3": 15_000_000,
            "wy_mm3": 2_000_000,
            "depth_mm": 200,
            "width_mm": 100,
            "shear_area_mm2": 5000,
            "local_slenderness": 0,
            "span_m": 10,
            "support": "simple",
            "tributary_width_m": 1,
            "include_self_weight": False,
            "lateral_restrained": True,
        },
        loads=[
            LoadItem(kind=LoadKind.DEAD, value=10, unit="kN/m", source="SkyCiv")
        ],
    )
    result = calculate(request)
    deflection = next(item for item in result.checks if item.name == "挠度")
    expected_mm = 5 * 10 * 10_000**4 / (384 * 206_000 * 1_500_000_000)
    assert deflection.demand.value == pytest.approx(expected_mm, rel=1e-6)
    assert expected_mm == pytest.approx(4.21386, rel=1e-5)


@pytest.mark.parametrize(
    "module",
    [CalculationModule.CONCRETE_BEAM, CalculationModule.TIMBER_BEAM],
)
def test_beam_modules_publish_support_reactions(
    module: CalculationModule,
) -> None:
    scenario = next(item for item in SCENARIOS if item.module is module)
    result = calculate(
        CalculationRequest(
            mode=CalculationMode.QUICK,
            module=module,
            project_name=scenario.title,
            confirmed_assumptions=True,
            inputs=scenario.inputs,
            loads=scenario.loads,
        )
    )
    assert result.reactions["left_vertical"].value > 0
    assert result.reactions["right_vertical"].value > 0


def test_professional_mode_requires_explicit_load_source() -> None:
    with pytest.raises(ValidationError):
        CalculationRequest(
            mode=CalculationMode.PROFESSIONAL,
            module=CalculationModule.STEEL_BEAM,
            project_name="invalid",
            inputs={},
            loads=[],
        )


def test_pressure_is_rejected_for_axial_column() -> None:
    request = CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_COLUMN,
        project_name="bad-unit",
        confirmed_assumptions=True,
        inputs={
            "steel_grade": "Q355B",
            "section_type": "SHS",
            "b_mm": 180,
            "t_mm": 8,
            "height_m": 3,
            "effective_length_factor": 1,
            "design_moment_kn_m": 0,
        },
        loads=[
            LoadItem(kind=LoadKind.DEAD, value=1, unit="kN/m2", source="test")
        ],
    )
    with pytest.raises(CalculationInputError) as error:
        calculate(request)
    assert error.value.code == "unsupported_load_unit"


def test_unrestrained_h_beam_is_explicitly_unsupported() -> None:
    request = CalculationRequest(
        mode=CalculationMode.PROFESSIONAL,
        module=CalculationModule.STEEL_BEAM,
        project_name="ltb",
        inputs={
            "steel_grade": "Q355B",
            "section_type": "H",
            "h_mm": 300,
            "b_mm": 150,
            "tw_mm": 6,
            "tf_mm": 10,
            "span_m": 4,
            "support": "simple",
            "tributary_width_m": 1,
            "include_self_weight": True,
            "lateral_restrained": False,
        },
        loads=[LoadItem(kind=LoadKind.DEAD, value=1, unit="kN/m", source="test")],
    )
    with pytest.raises(CalculationInputError) as error:
        calculate(request)
    assert error.value.code == "unsupported_unrestrained_open_section"


def test_professional_result_is_gated_until_independently_verified() -> None:
    request = CalculationRequest(
        mode=CalculationMode.PROFESSIONAL,
        module=CalculationModule.STEEL_BEAM,
        project_name="verification-gate",
        inputs={
            "steel_grade": "Q355B",
            "section_type": "RHS",
            "h_mm": 200,
            "b_mm": 100,
            "t_mm": 6,
            "span_m": 4,
            "support": "simple",
            "tributary_width_m": 1,
            "include_self_weight": False,
            "lateral_restrained": True,
        },
        loads=[LoadItem(kind=LoadKind.DEAD, value=2, unit="kN/m", source="手算基准")],
    )
    result = calculate(request)
    assert result.status == "incomplete"
    assert result.result_class == "professional_check"
    assert result.verification_status == "unverified"
    assert any(
        warning.code == "independent_verification_pending"
        for warning in result.warnings
    )


def test_thicker_steel_uses_lower_design_strength_band() -> None:
    def run(thickness: float):
        return calculate(
            CalculationRequest(
                mode=CalculationMode.QUICK,
                module=CalculationModule.STEEL_BEAM,
                project_name="thickness-band",
                confirmed_assumptions=True,
                inputs={
                    "steel_grade": "Q355B",
                    "section_type": "RHS",
                    "h_mm": 300,
                    "b_mm": 200,
                    "t_mm": thickness,
                    "span_m": 3,
                    "support": "simple",
                    "tributary_width_m": 1,
                    "include_self_weight": False,
                    "lateral_restrained": True,
                },
                loads=[
                    LoadItem(
                        kind=LoadKind.DEAD,
                        value=1,
                        unit="kN/m",
                        source="test",
                        direction=LoadDirection.GRAVITY,
                    )
                ],
            )
        )

    thin = run(6)
    thick = run(25)
    assert thin.input_summary["design_strength"].value == pytest.approx(305)
    assert thick.input_summary["design_strength"].value == pytest.approx(295)


def test_concrete_slab_does_not_require_or_credit_fictitious_stirrups() -> None:
    result = calculate(
        CalculationRequest(
            mode=CalculationMode.QUICK,
            module=CalculationModule.CONCRETE_SLAB,
            project_name="slab-no-stirrups",
            confirmed_assumptions=True,
            inputs={
                "concrete_grade": "C30",
                "rebar_grade": "HRB400",
                "h_mm": 150,
                "cover_mm": 20,
                "bar_dia_mm": 12,
                "bar_spacing_mm": 150,
                "span_m": 2.5,
                "support": "simple",
            },
            loads=[LoadItem(kind=LoadKind.LIVE, value=3, unit="kN/m2", source="test")],
        )
    )
    assert "stirrup_grade" not in result.input_summary
    shear = next(item for item in result.checks if item.name == "受剪承载力")
    h0 = 150 - 20 - 12 / 2
    assert shear.capacity.value == pytest.approx(0.7 * 1.43 * 1000 * h0 / 1000)
