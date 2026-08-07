from __future__ import annotations

from math import tan, radians

import pytest

from app.core.errors import CalculationInputError
from app.core.pool_structure import (
    PoolMaterials,
    PoolReinforcement,
    PoolWaterLevels,
    RectangularPoolGeometry,
    RectangularPoolInput,
    calculate_rectangular_pool,
)


def pool_input(
    *,
    internal_depth: float = 2.0,
    external_empty: float = 0.0,
    external_full: float | None = None,
    soil_height: float = 0.0,
    ballast: float = 0.0,
    antifloat_factor: float = 1.05,
) -> RectangularPoolInput:
    return RectangularPoolInput(
        geometry=RectangularPoolGeometry(
            inside_length_m=6.0,
            inside_width_m=4.0,
            wall_height_m=2.5,
            wall_thickness_mm=300.0,
            base_thickness_mm=400.0,
            base_projection_m=0.2,
            retained_soil_height_m=soil_height,
        ),
        materials=PoolMaterials(),
        reinforcement=PoolReinforcement(
            wall_vertical_as_mm2_per_m=1_600.0,
            wall_horizontal_as_mm2_per_m=2_400.0,
            base_x_as_mm2_per_m=1_800.0,
            base_y_as_mm2_per_m=1_800.0,
        ),
        water_levels=PoolWaterLevels(
            full_internal_depth_m=internal_depth,
            empty_external_head_m=external_empty,
            full_external_head_m=external_full,
        ),
        additional_ballast_kn=ballast,
        antifloat_factor=antifloat_factor,
    )


def combination(result, combination_id: str):
    return next(item for item in result.combinations if item.combination_id == combination_id)


def check(result, name: str):
    return next(item for item in result.checks if item.name == name)


def test_no_water_no_soil_has_zero_lateral_pressure() -> None:
    result = calculate_rectangular_pool(pool_input(internal_depth=0.0))
    for state in ("empty", "full"):
        service = combination(result, f"{state}-sls-service")
        assert service.pressures.net_resultant_kn_per_m == 0.0
        assert service.pressures.net_base_moment_kn_m_per_m == 0.0
        assert service.wall.vertical_moment_kn_m_per_m == 0.0
    assert result.verification_status == "unverified"


def test_full_pool_produces_internal_outward_pressure_closed_form() -> None:
    depth = 2.0
    result = calculate_rectangular_pool(pool_input(internal_depth=depth))
    service = combination(result, "full-sls-service")
    expected_resultant = -0.5 * 10.0 * depth**2
    expected_moment = expected_resultant * depth / 3.0
    assert service.pressures.net_resultant_kn_per_m == pytest.approx(expected_resultant)
    assert service.pressures.net_base_moment_kn_m_per_m == pytest.approx(expected_moment)
    assert service.wall.pressure_direction == "internal_outward"
    assert service.pressures.net_base_pressure_kpa == pytest.approx(-20.0)


def test_empty_pool_high_groundwater_has_external_pressure_and_uplift() -> None:
    result = calculate_rectangular_pool(pool_input(external_empty=2.4))
    service = combination(result, "empty-sls-service")
    wall_water_depth = 2.4 - 0.4
    assert service.pressures.external_water_resultant_kn_per_m == pytest.approx(
        0.5 * 10.0 * wall_water_depth**2
    )
    assert service.wall.pressure_direction == "external_inward"
    uplift = combination(result, "empty-uls-uplift")
    assert uplift.base.uplift_kn > 0
    assert uplift.base.tension_face == "top"


def test_active_soil_pressure_matches_rankine_closed_form() -> None:
    height = 2.0
    result = calculate_rectangular_pool(pool_input(internal_depth=0.0, soil_height=height))
    service = combination(result, "empty-sls-service")
    ka = tan(radians(45.0 - 30.0 / 2.0)) ** 2
    expected = 0.5 * ka * 18.0 * height**2
    assert service.pressures.active_coefficient == pytest.approx(ka)
    assert service.pressures.external_soil_resultant_kn_per_m == pytest.approx(expected)
    assert service.pressures.net_base_moment_kn_m_per_m == pytest.approx(expected * height / 3.0)


def test_full_and_empty_cases_preserve_opposite_pressure_directions() -> None:
    result = calculate_rectangular_pool(
        pool_input(internal_depth=2.2, external_empty=1.0, external_full=0.5)
    )
    assert combination(result, "empty-sls-service").wall.pressure_direction == "external_inward"
    assert combination(result, "full-sls-service").wall.pressure_direction == "internal_outward"


def test_unstable_empty_pool_reports_uplift_failure() -> None:
    result = calculate_rectangular_pool(pool_input(external_empty=2.5))
    antifloat = check(result, "抗浮稳定")
    assert antifloat.utilization > 1.0
    assert not antifloat.passed
    uplift_case = combination(result, antifloat.controlling_combination_id)
    assert uplift_case.base.unbalanced_uplift_kn > 0
    assert uplift_case.vertical_balance_error_kn < 0


@pytest.mark.parametrize(("target", "passed"), [(0.99, True), (1.01, False)])
def test_antifloat_utilization_flips_at_099_and_101(target: float, passed: bool) -> None:
    base = pool_input(external_empty=2.5, antifloat_factor=1.0)
    baseline = calculate_rectangular_pool(base)
    uplift_case = combination(baseline, "empty-uls-uplift")
    required_downward = uplift_case.base.uplift_kn / target
    ballast = required_downward - uplift_case.base.downward_kn
    tuned = pool_input(
        external_empty=2.5,
        ballast=ballast,
        antifloat_factor=1.0,
    )
    result = calculate_rectangular_pool(tuned)
    antifloat = check(result, "抗浮稳定")
    assert antifloat.utilization == pytest.approx(target, rel=1e-10)
    assert antifloat.passed is passed


def test_every_combination_is_force_and_moment_consistent_when_in_contact() -> None:
    result = calculate_rectangular_pool(
        pool_input(internal_depth=2.0, external_empty=1.0, external_full=0.5, soil_height=1.5, ballast=500.0)
    )
    assert len(result.combinations) == 10
    for item in result.combinations:
        assert item.wall_force_balance_error_kn_per_m == pytest.approx(0.0, abs=1e-12)
        assert item.wall_moment_balance_error_kn_m_per_m == pytest.approx(0.0, abs=1e-12)
        if item.base.unbalanced_uplift_kn == 0.0:
            assert item.vertical_balance_error_kn == pytest.approx(0.0, abs=1e-9)


def test_rectangular_base_distributes_moment_in_both_directions() -> None:
    result = calculate_rectangular_pool(pool_input(internal_depth=2.0))
    gravity = combination(result, "full-uls-gravity")
    assert gravity.base.x_moment_kn_m_per_m > 0
    assert gravity.base.y_moment_kn_m_per_m > 0
    assert gravity.base.x_moment_kn_m_per_m > gravity.base.y_moment_kn_m_per_m


@pytest.mark.parametrize(
    ("input_value", "code"),
    [
        (
            RectangularPoolInput(
                geometry=RectangularPoolGeometry(6, 4, 2.5, 300, 400, retained_soil_height_m=3.0),
                materials=PoolMaterials(),
                reinforcement=PoolReinforcement(),
                water_levels=PoolWaterLevels(2.0),
            ),
            "soil_height_out_of_scope",
        ),
        (
            RectangularPoolInput(
                geometry=RectangularPoolGeometry(6, 4, 2.5, 300, 400),
                materials=PoolMaterials(soil_friction_angle_deg=0.0),
                reinforcement=PoolReinforcement(),
                water_levels=PoolWaterLevels(2.0),
            ),
            "invalid_soil_friction_angle",
        ),
        (
            RectangularPoolInput(
                geometry=RectangularPoolGeometry(6, 4, 2.5, 30, 400),
                materials=PoolMaterials(),
                reinforcement=PoolReinforcement(wall_cover_mm=35),
                water_levels=PoolWaterLevels(2.0),
            ),
            "invalid_effective_depth",
        ),
    ],
)
def test_out_of_scope_inputs_are_structured(
    input_value: RectangularPoolInput, code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        calculate_rectangular_pool(input_value)
    assert caught.value.code == code
    assert caught.value.as_dict()["code"] == code
