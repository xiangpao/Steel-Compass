from __future__ import annotations

import pytest

from app.core.hydrostatics import (
    buoyancy_force,
    hydrostatic_lateral_action,
    rankine_active_earth_action,
)


def test_hydrostatic_triangular_action() -> None:
    action = hydrostatic_lateral_action(depth_m=2.0)
    assert action.maximum_pressure_kpa == pytest.approx(20.0)
    assert action.resultant_kn_per_m == pytest.approx(20.0)
    assert action.resultant_height_from_base_m == pytest.approx(2 / 3)


def test_rankine_active_action_for_phi_30_degrees() -> None:
    action = rankine_active_earth_action(
        height_m=3.0,
        friction_angle_deg=30.0,
        soil_unit_weight_kn_m3=18.0,
        surcharge_kpa=10.0,
    )
    assert action.coefficient == pytest.approx(1 / 3)
    assert action.soil_resultant_kn_per_m == pytest.approx(27.0)
    assert action.surcharge_resultant_kn_per_m == pytest.approx(10.0)
    assert action.overturning_moment_kn_m_per_m == pytest.approx(42.0)


def test_buoyancy_force_uses_displaced_volume() -> None:
    assert buoyancy_force(plan_area_m2=12.0, submerged_depth_m=1.5) == pytest.approx(
        180.0
    )
