from __future__ import annotations

import pytest

from app.core.continuous_beam import (
    ContinuousBeamInput,
    ContinuousBeamSpanInput,
    calculate_continuous_beam_engine,
)
from app.core.errors import CalculationInputError


def test_three_span_continuous_beam_basic():
    """测试三跨混凝土连续梁：多工况活载包络 + GB 50010 20% 塑性调幅。"""
    span1 = ContinuousBeamSpanInput(
        span_id="Span1",
        length_m=6.0,
        b_mm=250.0,
        h_mm=500.0,
        dead_load_kn_m=12.0,
        live_load_kn_m=10.0,
        elastic_modulus_gpa=30.0,
        as_mm2=1400.0,
        asv_s_mm2_mm=1.2,
    )
    span2 = ContinuousBeamSpanInput(
        span_id="Span2",
        length_m=6.0,
        b_mm=250.0,
        h_mm=500.0,
        dead_load_kn_m=12.0,
        live_load_kn_m=10.0,
        elastic_modulus_gpa=30.0,
        as_mm2=1400.0,
        asv_s_mm2_mm=1.2,
    )
    span3 = ContinuousBeamSpanInput(
        span_id="Span3",
        length_m=6.0,
        b_mm=250.0,
        h_mm=500.0,
        dead_load_kn_m=12.0,
        live_load_kn_m=10.0,
        elastic_modulus_gpa=30.0,
        as_mm2=1400.0,
        asv_s_mm2_mm=1.2,
    )

    inp = ContinuousBeamInput(
        spans=(span1, span2, span3),
        gamma_g=1.3,
        gamma_q=1.5,
        enable_plastic_redistribution=True,
        redistribution_ratio=0.20,
        material_type="concrete",
    )

    res = calculate_continuous_beam_engine(inp)

    # 1. 验证结果基本属性
    assert len(res.spans_results) == 3
    assert res.redistribution_applied is True
    assert res.redistribution_ratio_used == 0.20
    assert len(res.reactions_max_kn) == 4
    assert len(res.envelope_points) > 0

    # 2. 验证塑性调幅逻辑：支座负弯矩被调低 20%，设计弯矩应小于弹性最小弯矩绝对值
    sp1_res = res.spans_results[0]
    assert sp1_res.m_hogging_max_knm > 0
    # 调幅后的支座负弯矩 m_design_hogging_knm = m_hogging_max_knm * 0.8
    assert pytest.approx(sp1_res.m_design_hogging_knm, rel=1e-2) == sp1_res.m_hogging_max_knm * 0.8
    # 调幅后跨中正弯矩 m_design_sagging_knm 应大于原始弹性正弯矩
    assert sp1_res.m_design_sagging_knm > sp1_res.m_sagging_max_knm

    # 3. 验证受弯与受剪承载力计算 (GB 50010)
    assert sp1_res.moment_capacity_knm > 0
    assert sp1_res.shear_capacity_kn > 0
    assert sp1_res.flexure_utilization > 0
    assert sp1_res.shear_utilization > 0


def test_two_span_steel_continuous_beam():
    """测试两跨钢结构连续梁。"""
    span1 = ContinuousBeamSpanInput(
        span_id="Span1",
        length_m=5.0,
        b_mm=200.0,
        h_mm=400.0,
        dead_load_kn_m=5.0,
        live_load_kn_m=8.0,
        elastic_modulus_gpa=206.0,
        f_y_mpa=235.0,
    )
    span2 = ContinuousBeamSpanInput(
        span_id="Span2",
        length_m=5.0,
        b_mm=200.0,
        h_mm=400.0,
        dead_load_kn_m=5.0,
        live_load_kn_m=8.0,
        elastic_modulus_gpa=206.0,
        f_y_mpa=235.0,
    )

    inp = ContinuousBeamInput(
        spans=(span1, span2),
        gamma_g=1.2,
        gamma_q=1.4,
        enable_plastic_redistribution=False,
        material_type="steel",
    )

    res = calculate_continuous_beam_engine(inp)

    assert len(res.spans_results) == 2
    assert res.redistribution_applied is False
    assert res.redistribution_ratio_used == 0.0
    assert res.spans_results[0].flexure_passed is True


def test_continuous_beam_input_validations():
    """测试输入参数异常拦截。"""
    # 缺少跨
    with pytest.raises(CalculationInputError, match="连续梁至少需要一个跨"):
        calculate_continuous_beam_engine(ContinuousBeamInput(spans=()))

    # 跨长非正数
    span_invalid = ContinuousBeamSpanInput(
        span_id="Span1",
        length_m=-3.0,
    )
    with pytest.raises(CalculationInputError, match="spans\\[0\\].length_m 必须大于零"):
        calculate_continuous_beam_engine(ContinuousBeamInput(spans=(span_invalid,)))
