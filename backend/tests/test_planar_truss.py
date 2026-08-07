from __future__ import annotations

import pytest

from app.core.errors import CalculationInputError
from app.core.planar_truss import (
    PlanarTrussInput,
    TrussMember,
    TrussNode,
    TrussNodalLoad,
    TrussSupport,
    solve_planar_truss,
)


def test_simple_triangle_truss():
    """测试简单三角形桁架静力平衡与受拉受压计算。"""
    n1 = TrussNode("N1", 0.0, 0.0)
    n2 = TrussNode("N2", 4.0, 0.0)
    n3 = TrussNode("N3", 2.0, 3.0)

    m1 = TrussMember("Bottom", "N1", "N2", area_cm2=10.0, radius_gyration_cm=2.5)
    m2 = TrussMember("Left_Diagonal", "N1", "N3", area_cm2=10.0, radius_gyration_cm=2.5)
    m3 = TrussMember("Right_Diagonal", "N2", "N3", area_cm2=10.0, radius_gyration_cm=2.5)

    s1 = TrussSupport("N1", fix_x=True, fix_y=True) # 铰支座
    s2 = TrussSupport("N2", fix_x=False, fix_y=True) # 滚轴支座

    l3 = TrussNodalLoad("N3", fx_kn=0.0, fy_kn=-60.0)

    inp = PlanarTrussInput(
        nodes=(n1, n2, n3),
        members=(m1, m2, m3),
        supports=(s1, s2),
        loads=(l3,),
    )

    out = solve_planar_truss(inp)

    # 1. 验证位移与总体通过标志
    assert len(out.member_results) == 3
    assert out.overall_passed is True

    # 2. 验证支座反力: Fy_1 + Fy_2 应为 60 kN (各 30 kN 对称)
    r1_y = out.support_reactions_kn["N1"][1]
    r2_y = out.support_reactions_kn["N2"][1]
    assert pytest.approx(r1_y, rel=1e-2) == 30.0
    assert pytest.approx(r2_y, rel=1e-2) == 30.0

    # 3. 验证杆件内力：斜杆受压，下弦杆受拉
    res_dict = {m.member_id: m for m in out.member_results}
    assert res_dict["Left_Diagonal"].force_type == "compression"
    assert res_dict["Right_Diagonal"].force_type == "compression"
    assert res_dict["Bottom"].force_type == "tension"

    # 4. 验证长细比与轴压稳定系数 phi
    assert res_dict["Left_Diagonal"].slenderness_ratio > 0
    assert 0.0 < res_dict["Left_Diagonal"].phi_stability <= 1.0


def test_truss_invalid_inputs():
    """测试几何可变/缺少约束等的异常拦截。"""
    n1 = TrussNode("N1", 0.0, 0.0)
    n2 = TrussNode("N2", 4.0, 0.0)
    m1 = TrussMember("M1", "N1", "N2")
    s1 = TrussSupport("N1", fix_x=True, fix_y=False) # 缺少 Y 向约束

    inp = PlanarTrussInput(
        nodes=(n1, n2),
        members=(m1,),
        supports=(s1,),
        loads=(),
    )

    with pytest.raises(CalculationInputError, match="桁架刚度矩阵奇异"):
        solve_planar_truss(inp)
