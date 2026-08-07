from __future__ import annotations

from dataclasses import replace
from math import pi, sqrt

import pytest

from app.core.errors import CalculationInputError
from app.core.site_walls import (
    CastInPlaceRCWallInput,
    LowMasonryWallInput,
    SteelPostInfillWallInput,
    WallLoadCase,
    calculate_cast_in_place_rc_wall,
    calculate_low_masonry_wall,
    calculate_steel_post_infill_wall,
)


CASES = (
    WallLoadCase("ULS-W+", "positive wind", "ULS", 0.8, 0.2),
    WallLoadCase("ULS-W-", "negative wind", "ULS", -0.6, 0.2),
)


def rc_input(**changes: object) -> CastInPlaceRCWallInput:
    values = dict(
        height_m=1.8, length_m=6.0, thickness_mm=180.0, support_spacing_m=3.0,
        opening_ratio=0.1, concrete_unit_weight_kn_m3=25.0,
        concrete_fc_mpa=14.3, concrete_ft_mpa=1.43, rebar_fy_mpa=360.0,
        vertical_rebar_mm2_per_m=1200.0, horizontal_rebar_mm2_per_m=1200.0,
        cover_mm=30.0, bar_diameter_mm=12.0, load_cases=CASES,
    )
    values.update(changes)
    return CastInPlaceRCWallInput(**values)  # type: ignore[arg-type]


def steel_input(**changes: object) -> SteelPostInfillWallInput:
    values = dict(
        height_m=2.0, length_m=8.0, support_spacing_m=2.0, opening_ratio=0.1,
        infill_dead_load_kpa=0.5, post_self_weight_kn_m=0.12,
        post_area_mm2=3000.0, post_inertia_mm4=8.0e6,
        post_section_modulus_mm3=8.0e4, steel_elastic_modulus_mpa=206000.0,
        steel_yield_strength_mpa=235.0, load_cases=CASES,
        effective_length_factor=1.0,
    )
    values.update(changes)
    return SteelPostInfillWallInput(**values)  # type: ignore[arg-type]


def masonry_input(**changes: object) -> LowMasonryWallInput:
    values = dict(
        height_m=1.0, length_m=6.0, thickness_mm=240.0, support_spacing_m=3.0,
        opening_ratio=0.1, masonry_unit_weight_kn_m3=19.0,
        masonry_bending_strength_mpa=0.4, masonry_shear_strength_mpa=0.15,
        masonry_compression_strength_mpa=2.0, load_cases=CASES,
    )
    values.update(changes)
    return LowMasonryWallInput(**values)  # type: ignore[arg-type]


def assert_six_component_signed_reactions(result) -> None:
    assert len(result.combinations) == 2
    positive, negative = result.combinations
    assert positive.shear_kn > 0 and positive.moment_kn_m > 0
    assert negative.shear_kn < 0 and negative.moment_kn_m < 0
    assert positive.reaction.direction.value == "x_positive"
    assert negative.reaction.direction.value == "x_negative"
    for item in result.combinations:
        assert set(item.reaction.components) == {"N", "Vx", "Vy", "Mx", "My", "T"}
        assert item.reaction.components["N"].value == pytest.approx(item.axial_kn)
        assert item.reaction.components["Vx"].value == pytest.approx(item.shear_kn)
        assert item.reaction.components["My"].value == pytest.approx(item.moment_kn_m)


def test_rc_wall_matches_independent_closed_form_and_reactions() -> None:
    data = rc_input()
    result = calculate_cast_in_place_rc_wall(data)
    solid = 0.9
    expected_line = 25.0 * 0.18 * 1.8 * solid + 0.2 * 1.8 * solid
    expected_shear = 0.8 * 1.8 * solid
    expected_moment = 0.8 * 1.8**2 / 2.0 * solid
    depth = 180.0 - 30.0 - 12.0 / 2.0
    x = 360.0 * 1200.0 / (14.3 * 1000.0)
    expected_capacity = 360.0 * 1200.0 * (depth - min(x, 0.45 * depth) / 2.0) / 1.0e6
    positive = result.combinations[0]
    assert positive.foundation_line_load_kn_m == pytest.approx(expected_line)
    assert positive.member_shear_kn == pytest.approx(expected_shear)
    assert positive.member_moment_kn_m == pytest.approx(expected_moment)
    assert result.checks[0].capacity == pytest.approx(expected_capacity)
    assert result.checks[1].capacity == pytest.approx(0.7 * 1.43 * 1000 * depth / 1000)
    assert result.verification_status == "unverified"
    assert_six_component_signed_reactions(result)


def test_steel_post_wall_matches_independent_closed_form() -> None:
    data = steel_input()
    result = calculate_steel_post_infill_wall(data)
    positive = result.combinations[0]
    solid = 0.9
    line_wind = 0.8 * 2.0 * solid
    expected_axial = (0.5 + 0.2) * 2.0 * 2.0 * solid + 0.12 * 2.0
    radius = sqrt(8.0e6 / 3000.0)
    slenderness = 2.0 * 1000.0 / radius
    euler = pi**2 * 206000.0 * 8.0e6 / (2.0 * 1000.0) ** 2 / 1000.0
    assert positive.axial_kn == pytest.approx(expected_axial)
    assert positive.member_shear_kn == pytest.approx(line_wind * 2.0)
    assert positive.member_moment_kn_m == pytest.approx(line_wind * 2.0**2 / 2.0)
    checks = {item.key: item for item in result.checks}
    assert checks["steel_post_flexure"].capacity == pytest.approx(235.0 * 8.0e4 / 1.0e6)
    assert checks["steel_post_slenderness"].demand == pytest.approx(slenderness)
    assert checks["steel_post_axial_stability"].capacity == pytest.approx(min(euler, 235 * 3000 / 1000))
    assert_six_component_signed_reactions(result)


def test_low_masonry_wall_matches_independent_closed_form() -> None:
    result = calculate_low_masonry_wall(masonry_input())
    positive = result.combinations[0]
    solid = 0.9
    expected_line = 19.0 * 0.24 * 1.0 * solid + 0.2 * 1.0 * solid
    expected_moment = 0.8 * 1.0**2 / 2.0 * solid
    section_modulus = 1000.0 * 240.0**2 / 6.0
    checks = {item.key: item for item in result.checks}
    assert positive.foundation_line_load_kn_m == pytest.approx(expected_line)
    assert positive.member_moment_kn_m == pytest.approx(expected_moment)
    assert checks["masonry_wall_flexure"].capacity == pytest.approx(0.4 * section_modulus / 1.0e6)
    assert checks["masonry_wall_compression"].capacity == pytest.approx(2.0 * 240.0)
    assert result.verification_status == "unverified"
    assert_six_component_signed_reactions(result)


@pytest.mark.parametrize(
    "calculator, factory, field",
    [
        (calculate_cast_in_place_rc_wall, rc_input, "vertical_rebar_mm2_per_m"),
        (calculate_steel_post_infill_wall, steel_input, "post_section_modulus_mm3"),
        (calculate_low_masonry_wall, masonry_input, "masonry_bending_strength_mpa"),
    ],
)
def test_flexural_threshold_flips_at_099_and_101(calculator, factory, field) -> None:
    baseline = calculator(factory())
    demand = next(item for item in baseline.checks if "flexure" in item.key).demand
    if field == "vertical_rebar_mm2_per_m":
        # Solve by monotonic bisection because RC lever arm varies with As.
        low, high = 1.0, 100000.0
        for _ in range(100):
            mid = (low + high) / 2.0
            capacity = next(item for item in calculator(factory(**{field: mid})).checks if "flexure" in item.key).capacity
            if capacity < demand:
                low = mid
            else:
                high = mid
        exact = high
    else:
        current = getattr(factory(), field)
        current_capacity = next(item for item in baseline.checks if "flexure" in item.key).capacity
        exact = current * demand / current_capacity
    passing = calculator(factory(**{field: exact / 0.99}))
    failing = calculator(factory(**{field: exact / 1.01}))
    pass_check = next(item for item in passing.checks if "flexure" in item.key)
    fail_check = next(item for item in failing.checks if "flexure" in item.key)
    assert pass_check.utilization == pytest.approx(0.99, rel=2e-4)
    assert fail_check.utilization == pytest.approx(1.01, rel=2e-4)
    assert pass_check.passed
    assert not fail_check.passed


@pytest.mark.parametrize(
    "calculator, input_value, code",
    [
        (calculate_cast_in_place_rc_wall, rc_input(opening_ratio=0.151), "opening_ratio_out_of_scope"),
        (calculate_steel_post_infill_wall, steel_input(support_spacing_m=9.0), "support_spacing_exceeds_length"),
        (calculate_low_masonry_wall, masonry_input(load_cases=()), "missing_load_cases"),
        (calculate_cast_in_place_rc_wall, rc_input(thickness_mm=30.0, cover_mm=30.0), "invalid_effective_depth"),
    ],
)
def test_invalid_boundaries_are_structured(calculator, input_value, code) -> None:
    with pytest.raises(CalculationInputError) as exc_info:
        calculator(input_value)
    assert exc_info.value.code == code


def test_system_specific_failures_do_not_change_unverified_status() -> None:
    rc = calculate_cast_in_place_rc_wall(rc_input(vertical_rebar_mm2_per_m=100.0))
    steel = calculate_steel_post_infill_wall(steel_input(support_spacing_m=3.5))
    masonry = calculate_low_masonry_wall(masonry_input(height_m=1.6))
    assert rc.status == steel.status == masonry.status == "failed"
    assert rc.verification_status == steel.verification_status == masonry.verification_status == "unverified"
    assert all(result.missing_capabilities for result in (rc, steel, masonry))
