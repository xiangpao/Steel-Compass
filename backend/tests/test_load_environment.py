from __future__ import annotations

from math import sin, radians

import pytest

from app.core.errors import CalculationInputError
from app.core.load_environment import (
    LoadCase,
    SoilWaterInput,
    WindSnowGuideInput,
    calculate_soil_water_actions,
    calculate_wind_snow_actions,
    generate_action_combinations,
)


def _case(
    case_id: str,
    category: str,
    value: float,
    direction: str,
    *,
    group: str | None = None,
) -> LoadCase:
    return LoadCase(
        id=case_id,
        label=case_id,
        category=category,
        characteristic_value=value,
        unit="kN",
        direction=direction,
        target="frame-base",
        source_reference=f"source:{case_id}",
        exclusive_group=group,
    )


def test_action_combinations_generate_uls_and_all_sls_families() -> None:
    bundle = generate_action_combinations(
        [
            _case("G", "permanent", 10, "gravity"),
            _case("Q", "live", 5, "gravity"),
            _case("W+", "wind", 4, "x_positive", group="wind-direction"),
            _case("W-", "wind", 4, "x_negative", group="wind-direction"),
        ]
    )
    assert bundle.verification_status == "unverified"
    assert {item.limit_state for item in bundle.combinations} == {"ULS", "SLS"}
    assert {item.sls_type for item in bundle.combinations if item.limit_state == "SLS"} == {
        "standard",
        "frequent",
        "quasi_permanent",
    }
    assert {item.leading_action for item in bundle.combinations if item.limit_state == "ULS"} == {
        "Q",
        "W+",
        "W-",
    }
    for combination in bundle.combinations:
        ids = {item.case_id for item in combination.actions}
        assert not {"W+", "W-"} <= ids
        assert combination.target == "frame-base"
        assert combination.unit == "kN"
        assert combination.verification_status == "unverified"


def test_uplift_uses_favorable_permanent_and_preserves_signed_actions() -> None:
    bundle = generate_action_combinations(
        [
            _case("G", "permanent", 100, "gravity"),
            _case("W-UP", "wind", 80, "uplift"),
        ]
    )
    uplift = next(
        item
        for item in bundle.combinations
        if item.limit_state == "ULS" and item.leading_action == "W-UP"
    )
    factors = {item.case_id: item.factor for item in uplift.actions}
    signed = {item.case_id: item.factored_value for item in uplift.actions}
    assert factors == {"G": pytest.approx(0.9), "W-UP": pytest.approx(1.5)}
    assert signed["G"] == pytest.approx(90)
    assert signed["W-UP"] == pytest.approx(-120)
    assert uplift.resultants["vertical"] == pytest.approx(-30)


def test_positive_and_negative_wind_remain_separate_signed_combinations() -> None:
    bundle = generate_action_combinations(
        [
            _case("G", "permanent", 10, "gravity"),
            _case("W+", "wind", 6, "x_positive", group="wind"),
            _case("W-", "wind", 6, "x_negative", group="wind"),
        ]
    )
    positive = next(item for item in bundle.combinations if item.id.startswith("ULS-W+"))
    negative = next(item for item in bundle.combinations if item.id.startswith("ULS-W-"))
    assert positive.resultants["x"] == pytest.approx(9)
    assert negative.resultants["x"] == pytest.approx(-9)


def test_seismic_uses_dedicated_design_situation_and_never_factor_1_5() -> None:
    bundle = generate_action_combinations(
        [
            _case("G", "permanent", 100, "gravity"),
            _case("Q", "live", 20, "gravity"),
            _case("E+", "seismic", 8, "x_positive", group="seismic-x"),
            _case("E-", "seismic", 8, "x_negative", group="seismic-x"),
        ]
    )
    seismic = [item for item in bundle.combinations if item.design_situation == "seismic"]
    assert {item.leading_action for item in seismic} == {"E+", "E-"}
    for combination in seismic:
        factors = {item.case_id: item.factor for item in combination.actions}
        assert factors[combination.leading_action] == 1.0
        assert factors["G"] == 1.0
        assert factors["Q"] == pytest.approx(0.3)
    assert all(
        action.category != "seismic"
        for combination in bundle.combinations
        if combination.design_situation == "persistent"
        for action in combination.actions
    )


@pytest.mark.parametrize(
    ("cases", "code"),
    [
        ([], "missing_load_cases"),
        (
            [
                _case("A", "live", 1, "gravity"),
                _case("B", "live", 1, "gravity").model_copy(update={"unit": "mm"}),
            ],
            "unsupported_load_unit",
        ),
        (
            [
                _case("A", "live", 1, "gravity"),
                _case("B", "live", 1, "gravity").model_copy(update={"target": "other"}),
            ],
            "incompatible_combination_scope",
        ),
    ],
)
def test_combination_contract_returns_structured_errors(
    cases: list[LoadCase], code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        generate_action_combinations(cases)
    assert caught.value.code == code


def _wind_snow(**updates: object) -> WindSnowGuideInput:
    values: dict[str, object] = {
        "basic_wind_pressure_kpa": 0.45,
        "wind_source_reference": "reviewed GB 50009 city table",
        "recurrence_period_years": 50,
        "recurrence_factor": 1.0,
        "terrain_roughness": "B",
        "terrain_height_factor": 1.2,
        "shape_coefficient_positive": 0.8,
        "shape_coefficient_negative": -0.6,
        "wind_area_m2": 10.0,
        "snow_applicability": "applicable",
        "basic_snow_pressure_kpa": 0.30,
        "snow_source_reference": "reviewed GB 50009 snow table",
        "roof_snow_coefficient": 0.8,
        "snow_area_m2": 12.0,
        "target": "roof",
    }
    values.update(updates)
    return WindSnowGuideInput.model_validate(values)


def test_wind_snow_guide_converts_basic_values_to_member_actions() -> None:
    result = calculate_wind_snow_actions(_wind_snow())
    actions = {item.id: item for item in result.actions}
    expected_positive_pressure = 0.45 * 1.0 * 1.2 * 0.8
    expected_negative_pressure = 0.45 * 1.0 * 1.2 * 0.6
    assert actions["wind-positive"].pressure_kpa == pytest.approx(
        expected_positive_pressure
    )
    assert actions["wind-positive"].characteristic_value == pytest.approx(
        expected_positive_pressure * 10
    )
    assert actions["wind-negative"].direction == "x_negative"
    assert actions["wind-negative"].characteristic_value == pytest.approx(
        expected_negative_pressure * 10
    )
    assert actions["roof-snow"].pressure_kpa == pytest.approx(0.30 * 0.8)
    assert actions["roof-snow"].characteristic_value == pytest.approx(0.30 * 0.8 * 12)
    assert all(item.characteristic_value != 0.45 for item in result.actions[:2])
    assert result.verification_status == "unverified"


def test_zero_snow_is_valid_and_no_snow_is_explicitly_not_applicable() -> None:
    zero = calculate_wind_snow_actions(
        _wind_snow(basic_snow_pressure_kpa=0.0)
    )
    assert next(item for item in zero.actions if item.id == "roof-snow").characteristic_value == 0

    no_snow = calculate_wind_snow_actions(
        _wind_snow(
            snow_applicability="not_applicable",
            basic_snow_pressure_kpa=None,
            snow_source_reference=None,
            roof_snow_coefficient=None,
            snow_area_m2=None,
            no_snow_basis="reviewed project climate record: no snow action",
        )
    )
    assert no_snow.snow_status == "not_applicable"
    assert {item.category for item in no_snow.actions} == {"wind"}


def test_no_snow_without_basis_is_rejected() -> None:
    with pytest.raises(CalculationInputError) as caught:
        calculate_wind_snow_actions(
            _wind_snow(snow_applicability="not_applicable", no_snow_basis=None)
        )
    assert caught.value.code == "missing_no_snow_basis"


def _soil_water(**updates: object) -> SoilWaterInput:
    values: dict[str, object] = {
        "wall_height_m": 3.0,
        "earth_pressure_state": "active",
        "soil_unit_weight_dry_kn_m3": 18.0,
        "soil_unit_weight_saturated_kn_m3": 20.0,
        "soil_friction_angle_deg": 30.0,
        "surcharge_kpa": 0.0,
        "groundwater_depth_below_top_m": 3.0,
        "water_unit_weight_kn_m3": 10.0,
        "internal_water_depth_m": 0.0,
        "external_water_depth_m": 0.0,
        "base_area_m2": 6.0,
        "source_reference": "investigation report and operating levels",
        "target": "pool-wall-base",
    }
    values.update(updates)
    return SoilWaterInput.model_validate(values)


def test_active_dry_soil_matches_independent_triangular_closed_form() -> None:
    data = _soil_water()
    result = calculate_soil_water_actions(data)
    coefficient = (1 - sin(radians(30))) / (1 + sin(radians(30)))
    expected_base = coefficient * 18 * 3
    expected_force = expected_base * 3 / 2
    soil = result.actions[0]
    assert result.earth_pressure_coefficient == pytest.approx(coefficient)
    assert soil.base_pressure_kpa == pytest.approx(expected_base)
    assert soil.resultant_kn_per_m == pytest.approx(expected_force)
    assert soil.moment_about_base_kn_m_per_m == pytest.approx(expected_force * 3 / 3)
    assert soil.centroid_above_base_m == pytest.approx(1.0)
    assert result.verification_status == "unverified"


def test_groundwater_uses_effective_soil_weight_and_outputs_water_and_buoyancy() -> None:
    result = calculate_soil_water_actions(
        _soil_water(
            groundwater_depth_below_top_m=1.0,
            external_water_depth_m=2.0,
            internal_water_depth_m=1.0,
        )
    )
    actions = {item.id: item for item in result.actions}
    coefficient = 1 / 3
    pressure_at_water = coefficient * 18 * 1
    pressure_at_base = coefficient * (18 * 1 + (20 - 10) * 2)
    expected_soil_force = pressure_at_water * 1 / 2 + (
        pressure_at_water + pressure_at_base
    ) * 2 / 2
    assert actions["soil-active"].base_pressure_kpa == pytest.approx(pressure_at_base)
    assert actions["soil-active"].resultant_kn_per_m == pytest.approx(
        expected_soil_force
    )
    assert actions["external-water"].resultant_kn_per_m == pytest.approx(20)
    assert actions["external-water"].moment_about_base_kn_m_per_m == pytest.approx(
        20 * 2 / 3
    )
    assert actions["internal-water"].resultant_kn_per_m == pytest.approx(5)
    assert actions["internal-water"].direction == "x_negative"
    assert actions["base-uplift"].base_pressure_kpa == pytest.approx(20)
    assert actions["base-uplift"].force_kn == pytest.approx(120)
    assert actions["base-uplift"].direction == "uplift"


def test_at_rest_option_and_invalid_submerged_weight_boundary() -> None:
    at_rest = calculate_soil_water_actions(
        _soil_water(earth_pressure_state="at_rest", at_rest_coefficient=0.55)
    )
    assert at_rest.earth_pressure_coefficient == pytest.approx(0.55)

    with pytest.raises(CalculationInputError) as caught:
        calculate_soil_water_actions(
            _soil_water(
                groundwater_depth_below_top_m=1.0,
                soil_unit_weight_saturated_kn_m3=9.0,
            )
        )
    assert caught.value.code == "invalid_submerged_unit_weight"
