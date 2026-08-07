from __future__ import annotations

import pytest

from app.core.parametric_frame import (
    PortalFrameGeneratorInput,
    calculate_gb51022_member_check,
    generate_portal_frame_model,
    solve_parametric_frame,
)


def test_generate_single_span_portal_frame():
    """测试单跨门式刚架模型生成与矩阵求解。"""
    inp = PortalFrameGeneratorInput(
        span_m=18.0,
        height_m=6.0,
        roof_slope=0.1,
        num_spans=1,
    )
    model = generate_portal_frame_model(inp)
    assert len(model.nodes) == 5  # Left base, left top, apex, right top, right base
    assert len(model.members) == 4 # 2 Columns + 2 Beams
    assert len(model.restraints) == 2

    # 求解刚架
    res = solve_parametric_frame(model)
    assert len(res.displacements) == 5
    assert len(res.members) == 4


def test_generate_multi_span_portal_frame_with_rocking_column():
    """测试带摇晃柱的双跨门式刚架生成。"""
    inp = PortalFrameGeneratorInput(
        span_m=15.0,
        height_m=5.5,
        roof_slope=0.1,
        num_spans=2,
        has_rocking_column=True,
    )
    model = generate_portal_frame_model(inp)
    assert len(model.members) == 7  # 3 columns + 4 beams


def test_gb51022_tapered_member_stability_check():
    """按 GB 51022-2015 验算门式刚架变截面柱稳定性。"""
    res = calculate_gb51022_member_check(
        member_id="Col_1",
        axial_n_kn=120.0,
        moment_m_knm=180.0,
        shear_v_kn=35.0,
        b_f_mm=220.0,
        t_f_mm=12.0,
        h_web_max_mm=600.0,
        h_web_min_mm=350.0,
        t_w_mm=8.0,
        l_0x_m=6.0,
        l_0y_m=3.0,
        f_y_mpa=235.0,
    )

    assert res.lambda_x > 0
    assert res.lambda_y > 0
    assert 0.0 < res.phi_x <= 1.0
    assert 0.0 < res.phi_y <= 1.0
    assert res.strength_utilization > 0
    assert res.in_plane_stability_utilization > 0
    assert res.out_of_plane_stability_utilization > 0
