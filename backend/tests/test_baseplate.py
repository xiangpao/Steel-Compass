from __future__ import annotations

import pytest

from app.core.baseplate import calculate_steel_baseplate_anchor
from app.core.schemas import CalculationMode, CalculationModule, CalculationRequest


def _request(**overrides) -> CalculationRequest:
    inputs = {
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
        "upstream_reaction_envelopes": [
            {
                "name": "left_base",
                "limit_state": "SLS",
                "combination_name": "SLS-standard",
                "direction": "gravity",
                "components": {
                    "N": {"value": 80, "unit": "kN"},
                    "Vx": {"value": 5, "unit": "kN"},
                    "My": {"value": 8, "unit": "kN·m"},
                },
            },
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
            },
        ],
    }
    inputs.update(overrides)
    return CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.STEEL_BASEPLATE_ANCHOR,
        project_name="steel pergola base",
        confirmed_assumptions=True,
        inputs=inputs,
        loads=[],
    )


def test_baseplate_preserves_combination_effects_for_foundation() -> None:
    result = calculate_steel_baseplate_anchor(_request(), "trace-baseplate")
    assert len(result.reaction_envelopes) == 2
    uls = next(item for item in result.reaction_envelopes if item.limit_state == "ULS")
    assert uls.combination_name == "ULS-wind-leading"
    assert uls.components["N"].value == pytest.approx(105)
    assert uls.components["Vx"].value == pytest.approx(8)
    assert uls.components["My"].value == pytest.approx(14)
    assert set(uls.components) == {"N", "Vx", "Vy", "Mx", "My", "T"}
    assert any(
        warning.code == "anchor_concrete_failure_modes_checked"
        for warning in result.warnings
    )


def test_baseplate_rejects_odd_anchor_layout() -> None:
    with pytest.raises(Exception):
        calculate_steel_baseplate_anchor(_request(anchor_count=5), "trace-invalid")
