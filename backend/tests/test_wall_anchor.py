import pytest
from app.core.schemas import CalculationMode, CalculationModule, CalculationRequest
from app.core.wall_anchor import (
    EmbeddedPlateInput,
    calculate_gb50010_embedded_plate,
    calculate_wall_anchor,
)


def test_embedded_plate_tension_shear_combination():
    """Verify GB 50010 Section 9.7 rebar design under tension, bending & shear."""
    inp = EmbeddedPlateInput(
        plate_width_mm=300.0,
        plate_height_mm=300.0,
        plate_thickness_mm=14.0,
        rebar_count=4,
        rebar_rows=2,
        rebar_diameter_mm=16.0,
        rebar_fy_mpa=360.0,
        rebar_length_mm=600.0,
        concrete_fc_mpa=14.3,
        concrete_ft_mpa=1.43,
        edge_distance_x_mm=60.0,
        edge_distance_y_mm=60.0,
        n_design_kn=20.0,
        m_design_kn_m=10.0,
        v_design_kn=30.0,
    )

    res = calculate_gb50010_embedded_plate(inp)
    assert res.status == "passed"
    assert res.as_provided_mm2 > res.as_required_mm2
    assert res.governing_utilization < 1.0
    assert len(res.checks) >= 5


def test_embedded_plate_compression_shear_combination():
    """Verify GB 50010 Section 9.7 under compression, bending & shear."""
    inp = EmbeddedPlateInput(
        plate_width_mm=300.0,
        plate_height_mm=300.0,
        plate_thickness_mm=14.0,
        rebar_count=4,
        rebar_rows=2,
        rebar_diameter_mm=14.0,
        rebar_fy_mpa=360.0,
        rebar_length_mm=500.0,
        concrete_fc_mpa=14.3,
        concrete_ft_mpa=1.43,
        edge_distance_x_mm=60.0,
        edge_distance_y_mm=60.0,
        n_design_kn=-50.0,  # 压力
        m_design_kn_m=5.0,
        v_design_kn=20.0,
    )

    res = calculate_gb50010_embedded_plate(inp)
    assert res.status == "passed"
    assert res.governing_utilization < 1.0


def test_wall_anchor_calculation_request():
    """Verify engine API wrapper for wall_anchor."""
    req = CalculationRequest(
        project_name="Wall Anchor Test",
        module=CalculationModule.WALL_ANCHOR,
        mode=CalculationMode.QUICK,
        inputs={
            "plate_width_mm": 300,
            "plate_height_mm": 300,
            "plate_thickness_mm": 16,
            "rebar_count": 4,
            "rebar_rows": 2,
            "rebar_diameter_mm": 18,
            "rebar_fy_mpa": 360,
            "rebar_length_mm": 650,
            "edge_distance_x_mm": 60,
            "edge_distance_y_mm": 60,
            "v_design_kn": 40,
            "m_design_kn_m": 15,
        },
    )

    res = calculate_wall_anchor(req, trace_id="test-trace-wall-anchor")
    assert res.status == "passed"
    assert res.module == CalculationModule.WALL_ANCHOR
    assert len(res.checks) >= 5
