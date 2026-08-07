from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.connections import (
    ConnectionEffect,
    FastenerPosition,
    TimberPostBaseInput,
    WallAnchorGroupInput,
    calculate_timber_post_base,
    calculate_wall_anchor_group,
)
from app.core.errors import CalculationInputError


POSITIONS = [
    FastenerPosition(x_mm=-75, y_mm=-75),
    FastenerPosition(x_mm=75, y_mm=-75),
    FastenerPosition(x_mm=75, y_mm=75),
    FastenerPosition(x_mm=-75, y_mm=75),
]


def _effect(**overrides: float | str) -> ConnectionEffect:
    values: dict[str, float | str] = {
        "combination_id": "ULS-1",
        "combination_name": "ULS 风主导",
        "limit_state": "ULS",
        "n_kn": 0.0,
        "vx_kn": 0.0,
        "vy_kn": 0.0,
        "mx_kn_m": 0.0,
        "my_kn_m": 0.0,
        "torsion_kn_m": 0.0,
    }
    values.update(overrides)
    return ConnectionEffect.model_validate(values)


def _timber(**overrides: object) -> TimberPostBaseInput:
    values: dict[str, object] = {
        "post_width_mm": 180,
        "post_depth_mm": 180,
        "plate_width_mm": 300,
        "plate_depth_mm": 300,
        "fastener_diameter_mm": 12,
        "fastener_positions": POSITIONS,
        "connector_standoff_mm": 40,
        "bearing_design_capacity_kn": 200,
        "fastener_tension_design_capacity_kn": 30,
        "fastener_shear_design_capacity_kn": 20,
        "connector_bending_design_capacity_kn_m": 1.0,
        "minimum_spacing_mm": 48,
        "minimum_edge_distance_mm": 48,
    }
    values.update(overrides)
    return TimberPostBaseInput.model_validate(values)


def _rc_anchor(**overrides: object) -> WallAnchorGroupInput:
    values: dict[str, object] = {
        "base_material": "reinforced_concrete",
        "plate_width_mm": 300,
        "plate_depth_mm": 300,
        "anchor_diameter_mm": 16,
        "anchor_positions": POSITIONS,
        "anchor_tension_design_capacity_kn": 40,
        "anchor_shear_design_capacity_kn": 30,
        "minimum_spacing_mm": 48,
        "minimum_edge_distance_mm": 24,
        "concrete_capacity_method": "provided",
        "concrete_cone_design_capacity_kn": 160,
        "concrete_pullout_design_capacity_kn": 140,
        "concrete_splitting_design_capacity_kn": 120,
    }
    values.update(overrides)
    return WallAnchorGroupInput.model_validate(values)


def _checks(result, key: str):
    return [item for item in result.checks if item.key == key]


def test_timber_post_base_central_compression_and_material_capacity_path() -> None:
    data = _timber(
        bearing_design_capacity_kn=None,
        fastener_tension_design_capacity_kn=None,
        fastener_shear_design_capacity_kn=None,
        connector_bending_design_capacity_kn_m=None,
        timber_compression_design_mpa=8,
        timber_withdrawal_design_mpa=0.8,
        timber_shear_design_mpa=2.0,
        embedment_length_mm=80,
        fastener_fu_mpa=400,
        connector_bending_strength_mpa=235,
        connector_section_modulus_mm3=5000,
    )
    result = calculate_timber_post_base(data, [_effect(n_kn=100)],)
    bearing = _checks(result, "timber_end_bearing")[0]
    assert bearing.demand.value == pytest.approx(100)
    assert bearing.capacity.value == pytest.approx(8 * 180 * 180 / 1000)
    assert result.capacity_sources["tension"] in {
        "连接件钢材拉力筛查",
        "木材拔出侧表面设计强度筛查",
    }
    assert result.verification_status == "unverified"


def test_timber_post_base_eccentric_moment_increases_fastener_tension() -> None:
    centered = calculate_timber_post_base(_timber(), [_effect(n_kn=-20)])
    eccentric = calculate_timber_post_base(
        _timber(), [_effect(n_kn=-20, mx_kn_m=4, my_kn_m=3)]
    )
    centered_tension = _checks(centered, "fastener_tension_withdrawal")[0]
    eccentric_tension = _checks(eccentric, "fastener_tension_withdrawal")[0]
    assert centered_tension.demand.value == pytest.approx(5)
    assert eccentric_tension.demand.value > centered_tension.demand.value
    assert eccentric_tension.governing_fastener is not None


@pytest.mark.parametrize(
    ("uplift", "expected_status"),
    [(-9.9, "passed"), (-10.1, "failed")],
)
def test_timber_tension_099_101_flip(uplift: float, expected_status: str) -> None:
    result = calculate_timber_post_base(
        _timber(
            fastener_tension_design_capacity_kn=2.5,
            fastener_shear_design_capacity_kn=100,
            connector_standoff_mm=0,
        ),
        [_effect(n_kn=uplift)],
    )
    check = _checks(result, "fastener_tension_withdrawal")[0]
    assert check.utilization == pytest.approx(abs(uplift) / 4 / 2.5)
    assert check.passed is (expected_status == "passed")
    assert result.status == expected_status


def test_timber_shear_torsion_and_connector_bending_are_checked() -> None:
    result = calculate_timber_post_base(
        _timber(), [_effect(vx_kn=12, vy_kn=5, torsion_kn_m=2)]
    )
    shear = _checks(result, "fastener_horizontal_shear")[0]
    bending = _checks(result, "connector_bending")[0]
    assert shear.demand.value > hypot_per_anchor(12, 5, 4)
    assert bending.demand.value == pytest.approx(shear.demand.value * 0.04)


def hypot_per_anchor(vx: float, vy: float, count: int) -> float:
    return ((vx / count) ** 2 + (vy / count) ** 2) ** 0.5


def test_timber_layout_edge_failure_and_invalid_duplicate_position() -> None:
    edge_failed = calculate_timber_post_base(
        _timber(minimum_edge_distance_mm=80), [_effect(n_kn=20)]
    )
    assert not _checks(edge_failed, "fastener_edge_distance")[0].passed
    assert edge_failed.status == "failed"

    duplicate = [POSITIONS[0], POSITIONS[0], POSITIONS[2], POSITIONS[3]]
    with pytest.raises(CalculationInputError) as exc:
        calculate_timber_post_base(
            _timber(fastener_positions=duplicate), [_effect(n_kn=20)]
        )
    assert exc.value.code == "duplicate_fastener_position"


def test_timber_rejects_missing_capacity_and_nonfinite_effect() -> None:
    with pytest.raises(CalculationInputError) as exc:
        calculate_timber_post_base(
            _timber(fastener_tension_design_capacity_kn=None), [_effect(n_kn=-20)]
        )
    assert exc.value.code == "missing_connection_capacity"
    with pytest.raises(ValidationError):
        _effect(n_kn=float("nan"))


def test_rc_anchor_group_centered_and_eccentric_effects() -> None:
    centered = calculate_wall_anchor_group(_rc_anchor(), [_effect(n_kn=-40)])
    eccentric = calculate_wall_anchor_group(
        _rc_anchor(), [_effect(n_kn=-40, mx_kn_m=6, my_kn_m=-3)]
    )
    centered_steel = _checks(centered, "anchor_steel_tension")[0]
    eccentric_steel = _checks(eccentric, "anchor_steel_tension")[0]
    assert centered_steel.demand.value == pytest.approx(10)
    assert eccentric_steel.demand.value > centered_steel.demand.value
    assert _checks(eccentric, "concrete_cone")[0].combination_id == "ULS-1"


def test_rc_anchor_keeps_tension_and_shear_in_their_own_combinations() -> None:
    effects = [
        _effect(
            combination_id="ULS-T",
            combination_name="ULS uplift",
            n_kn=-80,
        ),
        _effect(
            combination_id="ULS-V",
            combination_name="ULS shear",
            vx_kn=80,
        ),
    ]
    result = calculate_wall_anchor_group(_rc_anchor(), effects)
    interactions = {
        item.combination_id: item.utilization
        for item in _checks(result, "anchor_steel_interaction")
    }
    assert interactions["ULS-T"] == pytest.approx(0.5)
    assert interactions["ULS-V"] == pytest.approx((20 / 30))
    assert len(result.effects) == 2


@pytest.mark.parametrize(
    ("uplift", "expected"),
    [(-39.6, True), (-40.4, False)],
)
def test_rc_anchor_steel_099_101_flip(uplift: float, expected: bool) -> None:
    result = calculate_wall_anchor_group(
        _rc_anchor(
            anchor_tension_design_capacity_kn=10,
            anchor_shear_design_capacity_kn=100,
            concrete_cone_design_capacity_kn=1000,
            concrete_pullout_design_capacity_kn=1000,
            concrete_splitting_design_capacity_kn=1000,
        ),
        [_effect(n_kn=uplift)],
    )
    check = _checks(result, "anchor_steel_tension")[0]
    assert check.utilization == pytest.approx(abs(uplift) / 4 / 10)
    assert check.passed is expected


def test_rc_anchor_simplified_concrete_capacity_is_explicitly_unverified() -> None:
    result = calculate_wall_anchor_group(
        _rc_anchor(
            concrete_capacity_method="simplified",
            concrete_cone_design_capacity_kn=None,
            concrete_pullout_design_capacity_kn=None,
            concrete_splitting_design_capacity_kn=None,
            concrete_fc_mpa=30,
            effective_embedment_mm=120,
        ),
        [_effect(n_kn=-20)],
    )
    assert result.capacity_sources["concrete_cone"].startswith("未验证")
    assert any("简化式" in warning for warning in result.warnings)
    assert result.verification_status == "unverified"


def test_masonry_requires_evaluated_capacity_and_uses_its_source() -> None:
    with pytest.raises(CalculationInputError) as exc:
        calculate_wall_anchor_group(
            _rc_anchor(base_material="solid_masonry"), [_effect(n_kn=-20)]
        )
    assert exc.value.code == "missing_evaluated_masonry_capacity"

    data = _rc_anchor(
        base_material="solid_masonry",
        masonry_evaluated_tension_capacity_kn=60,
        masonry_evaluated_shear_capacity_kn=40,
        masonry_capacity_source="现场拉拔试验报告 A-01",
    )
    result = calculate_wall_anchor_group(data, [_effect(n_kn=-20, vx_kn=8)])
    assert _checks(result, "masonry_tension")[0].reference == "现场拉拔试验报告 A-01"
    assert _checks(result, "concrete_cone") == []


def test_unknown_wall_substrate_returns_capability_unavailable() -> None:
    result = calculate_wall_anchor_group(
        _rc_anchor(base_material="unknown"), [_effect(n_kn=-20)]
    )
    assert result.status == "capability_unavailable"
    assert result.checks == []
    assert "未知" in result.warnings[0]


def test_anchor_layout_rejects_unresolvable_moment_axis() -> None:
    line = [
        FastenerPosition(x_mm=0, y_mm=-60),
        FastenerPosition(x_mm=0, y_mm=60),
    ]
    with pytest.raises(CalculationInputError) as exc:
        calculate_wall_anchor_group(
            _rc_anchor(anchor_positions=line), [_effect(my_kn_m=5)]
        )
    assert exc.value.code == "anchor_layout_has_no_x_lever_arm"
