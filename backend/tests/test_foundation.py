from __future__ import annotations

import pytest

from app.core.engine import calculate
from app.core.schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    LoadItem,
    LoadKind,
)


def spread_request(**input_overrides) -> CalculationRequest:
    inputs = {
        "length_m": 2.0,
        "width_m": 2.0,
        "thickness_mm": 500,
        "column_x_mm": 300,
        "column_y_mm": 300,
        "embedment_m": 1.0,
        "soil_cover_m": 0.0,
        "concrete_grade": "C30",
        "rebar_grade": "HRB400",
        "cover_mm": 50,
        "bar_dia_x_mm": 14,
        "bar_dia_y_mm": 14,
        "bar_spacing_x_mm": 150,
        "bar_spacing_y_mm": 150,
        "soil_capacity_kpa": 120,
        "base_friction_coefficient": 0.3,
        "moment_x_kn_m": 0,
        "moment_y_kn_m": 0,
        "horizontal_x_kn": 0,
        "horizontal_y_kn": 0,
        "uplift_kn": 0,
        "groundwater_known": True,
        "groundwater_depth_m": 2.0,
        "soil_source": "勘察报告测试值",
    }
    inputs.update(input_overrides)
    return CalculationRequest(
        mode=CalculationMode.PROFESSIONAL,
        module=CalculationModule.SPREAD_FOOTING,
        project_name="独立基础基准",
        inputs=inputs,
        loads=[
            LoadItem(
                kind=LoadKind.DEAD,
                value=100,
                unit="kN",
                source="柱底反力",
            )
        ],
    )


def test_centered_spread_footing_pressure_matches_hand_calculation() -> None:
    result = calculate(spread_request())
    pressure = next(step for step in result.steps if step.name == "基底平均压力")
    # N = 100 kN superstructure + 2m*2m*0.5m*25kN/m3 footing = 150 kN.
    assert pressure.result.value == pytest.approx(37.5)
    assert result.status == "incomplete"
    assert any(
        item.code == "foundation_validation_pending" for item in result.warnings
    )
    assert result.result_class == "professional_check"
    assert result.catalog_versions["materials"]


def test_large_eccentricity_is_reported_as_partial_contact() -> None:
    result = calculate(spread_request(moment_y_kn_m=80))
    assert any(item.code == "partial_contact" for item in result.warnings)
    contact = next(item for item in result.checks if item.name == "基底全截面接触")
    assert not contact.passed
    assert result.status == "failed"


def test_professional_foundation_without_geotechnical_confirmation_is_incomplete() -> None:
    result = calculate(
        spread_request(
            groundwater_known=False,
            groundwater_depth_m=None,
            soil_source="",
        )
    )
    assert result.status == "incomplete"
    assert any(
        item.code == "geotechnical_input_incomplete" for item in result.warnings
    )


def test_strip_footing_returns_pressure_and_reinforcement_checks() -> None:
    request = CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.STRIP_FOOTING,
        project_name="条形基础基准",
        confirmed_assumptions=True,
        inputs={
            "width_m": 1.4,
            "thickness_mm": 450,
            "wall_width_mm": 240,
            "wall_eccentricity_mm": 0,
            "concrete_grade": "C30",
            "rebar_grade": "HRB400",
            "cover_mm": 50,
            "bar_dia_mm": 14,
            "bar_spacing_mm": 150,
            "soil_capacity_kpa": 150,
            "base_friction_coefficient": 0.3,
            "horizontal_load_kn_m": 0,
            "moment_kn_m_per_m": 0,
        },
        loads=[
            LoadItem(
                kind=LoadKind.DEAD,
                value=60,
                unit="kN/m",
                source="墙体线荷载",
            )
        ],
    )
    result = calculate(request)
    assert result.diagrams[0].name == "条形基础基底压力"
    assert any(item.name == "横向底筋" for item in result.checks)


def test_spread_footing_uses_correct_critical_punching_perimeter() -> None:
    """Use the same column side + effective depth geometry verified by ASDIP.

    Only the critical-perimeter geometry is cross-checked; the Chinese-code
    punching resistance remains an independent implementation.
    Source: https://www.asdipsoft.com/documentation/ASDIP%20Foundation%20-%20Spread%20Footing%20Verification%20Example.pdf
    """
    result = calculate(spread_request())
    step = next(item for item in result.steps if item.name == "冲切承载力")
    # h0=min(500-50-7, 500-50-7)=443 mm;
    # u_m=2[(300+443)+(300+443)]=2972 mm.
    assert "u_m=2972.0 mm" in step.substitution


def test_groundwater_reduces_effective_foundation_weight() -> None:
    dry = calculate(spread_request(groundwater_depth_m=2.0))
    submerged = calculate(spread_request(groundwater_depth_m=0.0))
    dry_pressure = next(
        item for item in dry.steps if item.name == "基底平均压力"
    ).result.value
    submerged_pressure = next(
        item for item in submerged.steps if item.name == "基底平均压力"
    ).result.value
    assert dry_pressure == pytest.approx(37.5)
    # 2m*2m*0.5m displaces 20 kN of water.
    assert submerged_pressure == pytest.approx(32.5)
    assert submerged.input_summary["displaced_water_weight"].value == pytest.approx(20)


def test_uplift_failure_is_an_explicit_hard_failure() -> None:
    result = calculate(spread_request(uplift_kn=200))
    uplift = next(item for item in result.checks if item.name == "抗浮稳定")
    assert not uplift.passed
    assert result.status == "failed"


def test_strip_footing_preserves_eccentricity_sign_and_cancellation() -> None:
    request = CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.STRIP_FOOTING,
        project_name="条基偏心符号",
        confirmed_assumptions=True,
        inputs={
            "width_m": 1.4,
            "thickness_mm": 450,
            "wall_width_mm": 240,
            "wall_eccentricity_mm": 100,
            "concrete_grade": "C30",
            "rebar_grade": "HRB400",
            "cover_mm": 50,
            "bar_dia_mm": 14,
            "bar_spacing_mm": 150,
            "soil_capacity_kpa": 150,
            "base_friction_coefficient": 0.3,
            "horizontal_load_kn_m": 0,
            # N_service=60+1.4*0.45*25=75.75 kN/m; cancel N*0.1.
            "moment_kn_m_per_m": -7.575,
        },
        loads=[LoadItem(kind=LoadKind.DEAD, value=60, unit="kN/m", source="墙体")],
    )
    result = calculate(request)
    pressure = result.diagrams[0].points
    assert pressure[0].value.value == pytest.approx(pressure[-1].value.value)
    assert result.reactions["My"].value == pytest.approx(0, abs=1e-9)


def test_upstream_uls_reaction_is_not_factored_a_second_time() -> None:
    result = calculate(
        spread_request(
            upstream_reaction_envelopes=[
                {
                    "name": "left_support",
                    "limit_state": "SLS",
                    "combination_name": "SLS-标准组合",
                    "direction": "gravity",
                    "components": {"N": {"value": 100, "unit": "kN"}},
                },
                {
                    "name": "left_support",
                    "limit_state": "ULS",
                    "combination_name": "ULS-活荷载控制",
                    "direction": "gravity",
                    "components": {"N": {"value": 145, "unit": "kN"}},
                },
            ]
        )
    )
    # 基础自重 50 kN：SLS=100+50，ULS=145+1.3*50。
    # 若把上游 ULS 反力重新标成恒载，设计轴力会错误变成 195 kN。
    assert result.reactions["N_service"].value == pytest.approx(150)
    assert result.reactions["N_design"].value == pytest.approx(210)
    assert any(
        item.name == "ULS-活荷载控制" and item.total.value == pytest.approx(210)
        for item in result.combinations
    )
