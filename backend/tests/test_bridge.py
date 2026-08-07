from __future__ import annotations

import pytest

from app.core.bridge import (
    BridgeActions,
    BridgeComfortSettings,
    BridgeGeometry,
    SteelBeamSection,
    SteelTimberBridgeInput,
    TimberDeck,
    calculate_steel_timber_bridge,
)
from app.core.errors import CalculationInputError


def section(*, modulus: float = 1_200_000.0, inertia: float = 240_000_000.0) -> SteelBeamSection:
    return SteelBeamSection(
        area_mm2=9_000.0,
        inertia_mm4=inertia,
        section_modulus_mm3=modulus,
        shear_area_mm2=5_000.0,
    )


def bridge_input(
    *,
    spans: int = 1,
    load_pattern: tuple[float, ...] | None = None,
    wind: float = 0.8,
    cross_section: SteelBeamSection | None = None,
    longitudinal_section: SteelBeamSection | None = None,
    comfort: BridgeComfortSettings | None = None,
) -> SteelTimberBridgeInput:
    return SteelTimberBridgeInput(
        geometry=BridgeGeometry(
            span_count=spans,
            span_length_m=8.0,
            deck_width_m=3.0,
            crossbeam_spacing_m=1.0,
            longitudinal_girder_count=3,
        ),
        actions=BridgeActions(
            crowd_load_kpa=3.5,
            additional_dead_load_kpa=0.8,
            railing_dead_load_kn_m_per_side=0.5,
            wind_line_load_kn_m=wind,
            span_live_load_factors=load_pattern,
        ),
        timber_deck=TimberDeck(
            thickness_mm=80.0,
            elastic_modulus_mpa=11_000.0,
            bending_strength_mpa=18.0,
            shear_strength_mpa=2.0,
        ),
        crossbeam_section=cross_section or section(),
        longitudinal_section=longitudinal_section or section(inertia=600_000_000.0),
        comfort=comfort or BridgeComfortSettings(),
        foundation_types=("shallow",) + ("pile",) * max(spans - 1, 0) + ("shallow",),
    )


def combination(result, combination_id: str):
    return next(item for item in result.combinations if item.combination_id == combination_id)


def check(result, name: str):
    return next(item for item in result.checks if item.name == name)


def test_single_span_transfers_all_layers_to_two_abutments() -> None:
    result = calculate_steel_timber_bridge(bridge_input())
    service = combination(result, "sls-service")
    assert len(service.support_reactions) == 2
    assert [item.role for item in service.support_reactions] == [
        "left_abutment",
        "right_abutment",
    ]
    assert all(item.n_vertical_kn > 0 for item in service.support_reactions)
    assert service.vertical_balance_error_kn == pytest.approx(0.0, abs=1e-9)
    assert result.equivalent_crossbeam_count == pytest.approx(8.0)
    assert result.verification_status == "unverified"


def test_equal_multi_span_has_piers_and_continuous_longitudinal_response() -> None:
    result = calculate_steel_timber_bridge(bridge_input(spans=3))
    service = combination(result, "sls-service")
    assert len(service.support_reactions) == 4
    assert [item.role for item in service.support_reactions] == [
        "left_abutment",
        "pier",
        "pier",
        "right_abutment",
    ]
    assert service.longitudinal_girder.controlling_member.startswith("longitudinal-")
    assert service.vertical_balance_error_kn == pytest.approx(0.0, abs=1e-9)


def test_asymmetric_span_loading_produces_asymmetric_support_reactions() -> None:
    symmetric = calculate_steel_timber_bridge(
        bridge_input(spans=2, load_pattern=(1.0, 1.0))
    )
    asymmetric = calculate_steel_timber_bridge(
        bridge_input(spans=2, load_pattern=(1.0, 0.0))
    )
    symmetric_reactions = combination(symmetric, "uls-crowd").support_reactions
    asymmetric_reactions = combination(asymmetric, "uls-crowd").support_reactions
    assert symmetric_reactions[0].n_vertical_kn == pytest.approx(
        symmetric_reactions[-1].n_vertical_kn, rel=1e-10
    )
    assert asymmetric_reactions[0].n_vertical_kn != pytest.approx(
        asymmetric_reactions[-1].n_vertical_kn, rel=1e-3
    )


def test_positive_and_negative_wind_are_balanced_and_preserved() -> None:
    result = calculate_steel_timber_bridge(bridge_input(spans=2, wind=0.9))
    positive = combination(result, "uls-wind-positive")
    negative = combination(result, "uls-wind-negative")
    assert positive.total_wind_load_kn == pytest.approx(-negative.total_wind_load_kn)
    assert positive.total_wind_load_kn > 0
    assert sum(item.vx_kn for item in positive.support_reactions) == pytest.approx(
        positive.total_wind_load_kn
    )
    assert sum(item.vx_kn for item in negative.support_reactions) == pytest.approx(
        negative.total_wind_load_kn
    )
    assert positive.lateral_balance_error_kn == pytest.approx(0.0, abs=1e-12)
    assert negative.lateral_balance_error_kn == pytest.approx(0.0, abs=1e-12)
    assert all(len(item.components_6dof) == 6 for item in positive.support_reactions)


def test_all_combinations_preserve_vertical_and_lateral_balance() -> None:
    result = calculate_steel_timber_bridge(
        bridge_input(spans=3, load_pattern=(1.0, 0.4, 0.8))
    )
    for item in result.combinations:
        assert item.vertical_balance_error_kn == pytest.approx(0.0, abs=1e-8)
        assert item.lateral_balance_error_kn == pytest.approx(0.0, abs=1e-8)


@pytest.mark.parametrize(("target", "passed"), [(0.99, True), (1.01, False)])
def test_crossbeam_bending_flips_at_099_and_101(target: float, passed: bool) -> None:
    baseline = calculate_steel_timber_bridge(bridge_input())
    demand = check(baseline, "钢横梁抗弯").demand
    fy = 305.0
    tuned_modulus = demand * 1.0e6 / (fy * target)
    result = calculate_steel_timber_bridge(
        bridge_input(cross_section=section(modulus=tuned_modulus))
    )
    bending = check(result, "钢横梁抗弯")
    assert bending.utilization == pytest.approx(target, rel=1e-9)
    assert bending.passed is passed


@pytest.mark.parametrize(("target", "passed"), [(0.99, True), (1.01, False)])
def test_comfort_acceleration_flips_at_boundary(target: float, passed: bool) -> None:
    baseline = calculate_steel_timber_bridge(bridge_input())
    acceleration = baseline.comfort.simplified_peak_acceleration_m_s2
    settings = BridgeComfortSettings(acceleration_limit_m_s2=acceleration / target)
    result = calculate_steel_timber_bridge(bridge_input(comfort=settings))
    comfort_check = check(result, "竖向人行舒适度")
    assert result.comfort.basic_frequency_hz > 0
    assert comfort_check.utilization == pytest.approx(target, rel=1e-10)
    assert comfort_check.passed is passed
    assert "not a time-history" in result.comfort.method


def test_foundation_reaction_packages_do_not_design_foundations() -> None:
    result = calculate_steel_timber_bridge(bridge_input(spans=2))
    reactions = combination(result, "uls-crowd").support_reactions
    assert [item.foundation_type for item in reactions] == [
        "shallow",
        "pile",
        "shallow",
    ]
    assert all(item.mx_kn_m == 0 and item.my_kn_m == 0 for item in reactions)


@pytest.mark.parametrize(
    ("bridge", "code"),
    [
        (bridge_input(spans=1, load_pattern=(1.0, 1.0)), "invalid_span_load_factors"),
        (
            SteelTimberBridgeInput(
                geometry=BridgeGeometry(1, 8.0, 3.0, 1.0, 1),
                actions=BridgeActions(3.5),
                timber_deck=TimberDeck(80, 11_000, 18, 2),
                crossbeam_section=section(),
                longitudinal_section=section(),
            ),
            "girder_count_out_of_scope",
        ),
        (
            SteelTimberBridgeInput(
                geometry=BridgeGeometry(1, 8.0, 3.0, 9.0, 2),
                actions=BridgeActions(3.5),
                timber_deck=TimberDeck(80, 11_000, 18, 2),
                crossbeam_section=section(),
                longitudinal_section=section(),
            ),
            "crossbeam_spacing_out_of_scope",
        ),
        (
            SteelTimberBridgeInput(
                geometry=BridgeGeometry(1, 8.0, 3.0, 1.0, 2),
                actions=BridgeActions(3.5),
                timber_deck=TimberDeck(80, 11_000, 18, 2),
                crossbeam_section=section(inertia=0),
                longitudinal_section=section(),
            ),
            "invalid_bridge_input",
        ),
    ],
)
def test_invalid_inputs_return_structured_errors(
    bridge: SteelTimberBridgeInput, code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        calculate_steel_timber_bridge(bridge)
    assert caught.value.code == code
    assert caught.value.as_dict()["code"] == code
