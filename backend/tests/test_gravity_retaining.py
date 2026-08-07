from __future__ import annotations

from dataclasses import replace
from math import radians, tan

import pytest

from app.core.errors import CalculationInputError
from app.core.gravity_retaining import (
    GravityRetainingInput,
    calculate_gravity_retaining_wall,
)


def _input(**overrides: object) -> GravityRetainingInput:
    values: dict[str, object] = {
        "combination_id": "ULS-GRW-1",
        "combination_name": "ULS 土压力主导",
        "limit_state": "ULS",
        "retained_height_m": 2.0,
        "base_width_m": 2.4,
        "base_slab_thickness_m": 0.3,
        "wall_bottom_thickness_m": 1.2,
        "wall_top_thickness_m": 0.5,
        "toe_projection_m": 0.7,
        "wall_unit_weight_kn_m3": 24.0,
        "soil_unit_weight_kn_m3": 18.0,
        "soil_friction_angle_deg": 30.0,
        "surcharge_kpa": 5.0,
        "base_friction_coefficient": 0.6,
        "soil_bearing_capacity_kpa": 300.0,
        "material_compressive_design_kpa": 1000.0,
        "water_depth_behind_m": 0.8,
        "water_unit_weight_kn_m3": 10.0,
        "uplift_head_toe_m": 0.0,
        "uplift_head_heel_m": 0.5,
        "sliding_safety_factor": 1.0,
        "overturning_safety_factor": 1.0,
    }
    values.update(overrides)
    return GravityRetainingInput(**values)  # type: ignore[arg-type]


def _check(result, key: str):
    return next(item for item in result.checks if item.key == key)


def test_gravity_wall_matches_independent_soil_water_and_equilibrium_formula() -> None:
    data = _input()
    result = calculate_gravity_retaining_wall(data)

    # Independent closed-form reference: effective soil stress is integrated
    # as a dry wedge, saturated rectangular overburden and submerged wedge.
    ka = tan(radians(45 - 30 / 2)) ** 2
    dry_height = 2.0 - 0.8
    dry_wedge = 0.5 * ka * 18 * dry_height**2
    saturated_rectangle = ka * 18 * dry_height * 0.8
    submerged_wedge = 0.5 * ka * (18 - 10) * 0.8**2
    soil = dry_wedge + saturated_rectangle + submerged_wedge
    surcharge = ka * 5 * 2
    water = 0.5 * 10 * 0.8**2
    lateral_moment = (
        dry_wedge * (0.8 + dry_height / 3)
        + saturated_rectangle * 0.8 / 2
        + submerged_wedge * 0.8 / 3
        + surcharge * 2 / 2
        + water * 0.8 / 3
    )
    wall_area = (1.2 + 0.5) * 2 / 2
    wall_weight = wall_area * 24
    wall_local_centroid = (1.2**2 + 1.2 * 0.5 + 0.5**2) / (3 * (1.2 + 0.5))
    base_weight = 2.4 * 0.3 * 24
    uplift = (0 + 10 * 0.5) * 2.4 / 2
    uplift_centroid = 2.4 * (0 + 2 * 5) / (3 * 5)
    vertical = wall_weight + base_weight - uplift
    stabilizing = wall_weight * (0.7 + wall_local_centroid) + base_weight * 1.2
    location = (stabilizing - lateral_moment - uplift * uplift_centroid) / vertical
    eccentricity = 1.2 - location
    q_average = vertical / 2.4
    expected_qmax = q_average * (1 + 6 * abs(eccentricity) / 2.4)
    material_compression = wall_weight / 1.2 + 6 * lateral_moment / 1.2**2

    assert result.active_coefficient == pytest.approx(ka)
    assert result.soil_resultant_kn_per_m == pytest.approx(soil)
    assert result.surcharge_resultant_kn_per_m == pytest.approx(surcharge)
    assert result.water_resultant_kn_per_m == pytest.approx(water)
    assert result.lateral_moment_kn_m_per_m == pytest.approx(lateral_moment)
    assert result.wall_weight_kn_per_m == pytest.approx(wall_weight)
    assert result.base_weight_kn_per_m == pytest.approx(base_weight)
    assert result.uplift_kn_per_m == pytest.approx(uplift)
    assert result.effective_vertical_kn_per_m == pytest.approx(vertical)
    assert result.resultant_location_from_toe_m == pytest.approx(location)
    assert result.eccentricity_m == pytest.approx(eccentricity)
    assert result.q_max_kpa == pytest.approx(expected_qmax)
    assert result.material_max_compression_kpa == pytest.approx(material_compression)


def test_rectangular_and_trapezoidal_wall_self_weight_geometry() -> None:
    rectangular = calculate_gravity_retaining_wall(
        _input(
            wall_bottom_thickness_m=1.0,
            wall_top_thickness_m=1.0,
            toe_projection_m=0.7,
            water_depth_behind_m=0,
            uplift_head_heel_m=0,
        )
    )
    trapezoidal = calculate_gravity_retaining_wall(
        _input(water_depth_behind_m=0, uplift_head_heel_m=0)
    )
    assert rectangular.wall_weight_kn_per_m == pytest.approx(1.0 * 2.0 * 24)
    assert trapezoidal.wall_weight_kn_per_m == pytest.approx(
        (1.2 + 0.5) / 2 * 2.0 * 24
    )


def test_reaction_envelope_preserves_one_combination_and_six_components() -> None:
    result = calculate_gravity_retaining_wall(_input())
    envelope = result.reaction_envelopes[0]
    assert envelope.combination_id == "ULS-GRW-1"
    assert envelope.combination_name == "ULS 土压力主导"
    assert envelope.limit_state == "ULS"
    assert set(envelope.components) == {"N", "Vx", "Vy", "Mx", "My", "T"}
    assert envelope.components["N"].value == pytest.approx(
        result.effective_vertical_kn_per_m
    )
    assert envelope.components["Vx"].value == pytest.approx(
        result.total_horizontal_kn_per_m
    )
    assert envelope.components["My"].value == pytest.approx(
        result.effective_vertical_kn_per_m * result.eccentricity_m
    )
    assert result.verification_status == "unverified"


def test_partial_contact_is_reported_without_using_passive_pressure() -> None:
    result = calculate_gravity_retaining_wall(
        _input(
            base_width_m=1.8,
            toe_projection_m=0.2,
            base_slab_thickness_m=0.2,
            base_friction_coefficient=1.0,
            soil_bearing_capacity_kpa=1000,
        )
    )
    assert result.contact_length_m < 1.8
    assert result.q_min_kpa == pytest.approx(0)
    assert not _check(result, "eccentricity").passed
    assert any("局部脱开" in warning for warning in result.warnings)
    assert any("不采用被动土压力" in item for item in result.assumptions)


@pytest.mark.parametrize(
    ("capacity_ratio", "expected_passed"), [(1.01, True), (0.99, False)]
)
def test_material_compression_099_101_flip(
    capacity_ratio: float, expected_passed: bool
) -> None:
    reference = calculate_gravity_retaining_wall(_input())
    capacity = reference.material_max_compression_kpa * capacity_ratio
    result = calculate_gravity_retaining_wall(
        _input(material_compressive_design_kpa=capacity)
    )
    check = _check(result, "material_compression")
    assert check.utilization == pytest.approx(1 / capacity_ratio)
    assert check.passed is expected_passed


@pytest.mark.parametrize(
    ("capacity_ratio", "expected_passed"), [(1.01, True), (0.99, False)]
)
def test_sliding_099_101_flip(
    capacity_ratio: float, expected_passed: bool
) -> None:
    reference = calculate_gravity_retaining_wall(_input())
    friction = (
        reference.total_horizontal_kn_per_m
        * capacity_ratio
        / reference.effective_vertical_kn_per_m
    )
    result = calculate_gravity_retaining_wall(
        _input(base_friction_coefficient=friction)
    )
    check = _check(result, "sliding")
    assert check.utilization == pytest.approx(1 / capacity_ratio)
    assert check.passed is expected_passed


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("retained_height_m", 0, "non_positive_value"),
        ("wall_top_thickness_m", 1.3, "invalid_wall_taper"),
        ("toe_projection_m", 1.3, "wall_outside_base"),
        ("water_depth_behind_m", 2.1, "water_depth_exceeds_wall"),
        ("soil_friction_angle_deg", 45, "invalid_friction_angle"),
        ("surcharge_kpa", -1, "negative_value"),
        ("soil_unit_weight_kn_m3", 10, "invalid_submerged_unit_weight"),
    ],
)
def test_invalid_boundary_inputs_are_structured(
    field: str, value: float, code: str
) -> None:
    with pytest.raises(CalculationInputError) as exc:
        calculate_gravity_retaining_wall(_input(**{field: value}))
    assert exc.value.code == code
    assert exc.value.field == field


def test_excessive_uplift_is_rejected_before_pressure_conclusion() -> None:
    with pytest.raises(CalculationInputError) as exc:
        calculate_gravity_retaining_wall(
            replace(
                _input(),
                uplift_head_toe_m=10,
                uplift_head_heel_m=10,
            )
        )
    assert exc.value.code == "non_positive_effective_vertical"


def test_resultant_outside_base_returns_failed_result_not_infinite_output() -> None:
    result = calculate_gravity_retaining_wall(
        _input(surcharge_kpa=500, soil_bearing_capacity_kpa=1000)
    )
    assert result.status == "failed"
    assert result.contact_length_m == 0
    assert result.q_max_kpa > result.effective_vertical_kn_per_m
    assert result.q_max_kpa < float("inf")
    assert any("倾覆失稳" in warning for warning in result.warnings)


def test_result_scope_excludes_unimplemented_engineering_checks() -> None:
    result = calculate_gravity_retaining_wall(_input())
    scope = " ".join(result.applicability)
    assert "地震" in scope
    assert "整体稳定" in scope
    assert "沉降" in scope
    assert result.status in {"passed", "failed"}
