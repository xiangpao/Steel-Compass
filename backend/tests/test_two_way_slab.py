from __future__ import annotations

import pytest

from app.core.two_way_slab import TwoWaySlabInput, calculate_two_way_slab


def test_four_side_fixed_two_way_slab():
    """测试四边固定矩形双向板内力与配筋计算。"""
    inp = TwoWaySlabInput(
        lx_m=4.0,
        ly_m=5.0,
        thickness_mm=120.0,
        dead_load_kpa=5.0,
        live_load_kpa=2.0,
        left_edge="fixed",
        right_edge="fixed",
        bottom_edge="fixed",
        top_edge="fixed",
    )

    out = calculate_two_way_slab(inp)

    # 1. 长短边跨度比 ly / lx = 5 / 4 = 1.25 <= 2.0 -> 双向板
    assert out.ratio_ly_lx == 1.25
    assert out.is_two_way is True
    assert out.passed is True

    # 2. 设计荷载 1.3*5.0 + 1.5*2.0 = 9.5 kPa
    assert pytest.approx(out.design_load_kpa, rel=1e-3) == 9.5

    # 3. 短边 (X向) 弯矩大于长边 (Y向) 弯矩
    assert out.mx_mid_knm > out.my_mid_knm
    assert out.mx_support_knm > out.my_support_knm

    # 4. 配筋大于等于最小配筋率要求 (rho_min * b * h)
    min_as = out.min_reinforcement_ratio * 1000.0 * 120.0
    assert out.as_x_mid_mm2 >= min_as
    assert out.as_y_mid_mm2 >= min_as


def test_one_way_slab_detection():
    """测试长宽比大于 2.0 时识别为非双向板。"""
    inp = TwoWaySlabInput(
        lx_m=3.0,
        ly_m=7.0,
        thickness_mm=100.0,
    )

    out = calculate_two_way_slab(inp)
    assert out.ratio_ly_lx > 2.0
    assert out.is_two_way is False
    assert out.passed is False
