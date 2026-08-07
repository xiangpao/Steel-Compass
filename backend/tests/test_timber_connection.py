from __future__ import annotations

import pytest

from app.core.timber_connection import TimberConnectionInput, calculate_timber_connection


def test_dowel_connection_johansen_modes():
    """测试木结构销轴连接 Johansen 六种屈服模式与最小承载力控制。"""
    inp = TimberConnectionInput(
        fastener_type="dowel",
        fastener_diameter_mm=12.0,
        fastener_fy_mpa=400.0,
        main_thickness_mm=80.0,
        side_thickness_mm=40.0,
        timber_fh_mpa=25.0,
        num_fasteners=4,
        shear_force_kn=15.0,
    )

    out = calculate_timber_connection(inp)

    # 1. 验证 6 种模式均得到有效计算
    assert len(out.mode_capacities_kn) == 6
    assert out.single_fastener_capacity_kn > 0

    # 2. 验证控制模式为 6 种模式中的最小值
    min_val = min(out.mode_capacities_kn.values())
    assert pytest.approx(out.single_fastener_capacity_kn, rel=1e-3) == min_val

    # 3. 验证节点总承载力与利用率
    assert out.total_capacity_kn == out.single_fastener_capacity_kn * 4
    assert out.passed is True


def test_steel_plate_side_member():
    """测试带有钢板侧板的销轴连接局部承压提高与承载力变化。"""
    inp_timber = TimberConnectionInput(side_member_type="timber")
    inp_steel = TimberConnectionInput(side_member_type="steel_thick")

    out_timber = calculate_timber_connection(inp_timber)
    out_steel = calculate_timber_connection(inp_steel)

    # 厚钢板侧板孔壁承压强度更高，单销力能力增加
    assert out_steel.single_fastener_capacity_kn >= out_timber.single_fastener_capacity_kn
