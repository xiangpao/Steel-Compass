from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from .errors import CalculationInputError

BoundaryType = Literal["fixed", "hinged", "free"]


def _number(value: float, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_number", f"{field_name} 必须是有限数值。", field=field_name
        ) from exc
    if not isfinite(numeric):
        raise CalculationInputError(
            "invalid_number", f"{field_name} 必须是有限数值。", field=field_name
        )
    return numeric


def _positive(value: float, field_name: str) -> float:
    numeric = _number(value, field_name)
    if numeric <= 0:
        raise CalculationInputError(
            "non_positive_value", f"{field_name} 必须大于零。", field=field_name
        )
    return numeric


@dataclass(frozen=True)
class TwoWaySlabInput:
    lx_m: float                           # 短边净跨 lx (m)
    ly_m: float                           # 长边净跨 ly (m)
    thickness_mm: float                   # 板厚度 h (mm)
    concrete_fc_mpa: float = 14.3         # C30 轴心抗压强度设计值
    concrete_ft_mpa: float = 1.43         # C30 轴心抗拉强度设计值
    rebar_fy_mpa: float = 360.0           # HRB400 抗拉强度设计值
    cover_mm: float = 20.0                # 保护层厚度 (mm)
    dead_load_kpa: float = 5.0            # 恒载标准值 g_k (kPa)
    live_load_kpa: float = 2.5            # 活载标准值 q_k (kPa)
    left_edge: BoundaryType = "fixed"     # 左边 (x=0) 约束
    right_edge: BoundaryType = "fixed"    # 右边 (x=lx) 约束
    bottom_edge: BoundaryType = "fixed"   # 下边 (y=0) 约束
    top_edge: BoundaryType = "fixed"      # 上边 (y=ly) 约束
    calculation_method: Literal["elastic_table", "yield_line"] = "elastic_table"


@dataclass(frozen=True)
class TwoWaySlabOutput:
    ratio_ly_lx: float                   # 长短边跨度比 ly / lx
    is_two_way: bool                     # 是否为双向板 (ly / lx <= 2.0)
    design_load_kpa: float               # 设计荷载设计值 p_d (kPa)
    mx_mid_knm: float                    # X 向跨中设计弯矩 (kN·m/m)
    my_mid_knm: float                    # Y 向跨中设计弯矩 (kN·m/m)
    mx_support_knm: float                # X 向支座设计弯矩 (kN·m/m)
    my_support_knm: float                # Y 向支座设计弯矩 (kN·m/m)
    as_x_mid_mm2: float                  # X 向跨中所需钢筋面积 (mm²/m)
    as_y_mid_mm2: float                  # Y 向跨中所需钢筋面积 (mm²/m)
    as_x_support_mm2: float              # X 向支座所需钢筋面积 (mm²/m)
    as_y_support_mm2: float              # Y 向支座所需钢筋面积 (mm²/m)
    min_reinforcement_ratio: float       # 最小配筋率 rho_min
    passed: bool
    summary: str


def calculate_two_way_slab(inp: TwoWaySlabInput) -> TwoWaySlabOutput:
    """GB 50010-2010 矩形双向板内力计算与双向配筋。"""
    lx = _positive(inp.lx_m, "lx_m")
    ly = _positive(inp.ly_m, "ly_m")
    h = _positive(inp.thickness_mm, "thickness_mm")
    fc = _positive(inp.concrete_fc_mpa, "concrete_fc_mpa")
    ft = _positive(inp.concrete_ft_mpa, "concrete_ft_mpa")
    fy = _positive(inp.rebar_fy_mpa, "rebar_fy_mpa")
    cover = _positive(inp.cover_mm, "cover_mm")

    if lx > ly:
        # 始终确保 lx 为短边，ly 为长边
        lx, ly = ly, lx

    ratio = ly / lx
    is_two_way = ratio <= 2.0

    # 1. 荷载组合 (GB 50009): 1.3 * g_k + 1.5 * q_k
    p_d = 1.3 * _number(inp.dead_load_kpa, "dead_load_kpa") + 1.5 * _number(inp.live_load_kpa, "live_load_kpa")

    # 2. 弯矩系数计算 (按 Marcus 法或四边固定近似系数)
    # 固结边数量
    fixed_count = [
        inp.left_edge, inp.right_edge, inp.bottom_edge, inp.top_edge
    ].count("fixed")

    if fixed_count == 4:
        # 四边固定 (4-side fixed)
        alpha_x_mid = 0.018 + 0.010 * (ratio - 1.0)
        alpha_y_mid = 0.018 / (ratio ** 1.5)
        alpha_x_sup = 0.045 + 0.015 * (ratio - 1.0)
        alpha_y_sup = 0.045 / (ratio ** 1.5)
    elif fixed_count == 0:
        # 四边简支 (4-side hinged)
        alpha_x_mid = 0.036 + 0.020 * (ratio - 1.0)
        alpha_y_mid = 0.036 / (ratio ** 1.5)
        alpha_x_sup = 0.0
        alpha_y_sup = 0.0
    else:
        # 三边或两边固定 (近似中间过渡)
        alpha_x_mid = 0.027 + 0.015 * (ratio - 1.0)
        alpha_y_mid = 0.027 / (ratio ** 1.5)
        alpha_x_sup = 0.025 + 0.010 * (ratio - 1.0)
        alpha_y_sup = 0.025 / (ratio ** 1.5)

    if inp.calculation_method == "yield_line":
        # 塑性屈服线法下调系数
        alpha_x_mid *= 0.85
        alpha_y_mid *= 0.85

    # 弯矩 M = alpha * p_d * lx^2 (kN·m/m)
    mx_mid = alpha_x_mid * p_d * (lx ** 2)
    my_mid = alpha_y_mid * p_d * (lx ** 2)
    mx_sup = alpha_x_sup * p_d * (lx ** 2)
    my_sup = alpha_y_sup * p_d * (lx ** 2)

    # 3. 截面配筋计算 (1m 宽板条)
    h0_x = h - cover - 5.0     # X 向有效高度 (假设外层)
    h0_y = h - cover - 15.0    # Y 向有效高度 (假设内层)
    b = 1000.0                 # 板条宽度 (mm)

    def _calc_as(m_knm: float, h0_mm: float) -> float:
        if m_knm <= 0:
            return 0.0
        m_nmm = m_knm * 1e6
        # alpha_s = M / (alpha_1 * fc * b * h0^2)
        alpha_s = m_nmm / (1.0 * fc * b * (h0_mm ** 2))
        if alpha_s >= 0.386:
            # 截面受压区超限
            return (m_nmm / (0.85 * fy * h0_mm))
        gamma_s = 0.5 * (1.0 + (1.0 - 2.0 * alpha_s) ** 0.5)
        return m_nmm / (fy * gamma_s * h0_mm)

    as_x_mid = _calc_as(mx_mid, h0_x)
    as_y_mid = _calc_as(my_mid, h0_y)
    as_x_sup = _calc_as(mx_sup, h0_x)
    as_y_sup = _calc_as(my_sup, h0_x)

    # 最小配筋率规范强检: rho_min = max(0.2%, 0.45 * ft / fy)
    rho_min = max(0.002, 0.45 * ft / fy)
    as_min_x = rho_min * b * h
    as_min_y = rho_min * b * h

    as_x_mid = max(as_x_mid, as_min_x)
    as_y_mid = max(as_y_mid, as_min_y)
    if mx_sup > 0:
        as_x_sup = max(as_x_sup, as_min_x)
    if my_sup > 0:
        as_y_sup = max(as_y_sup, as_min_y)

    passed = (h >= 80.0) and is_two_way

    summary = (
        f"矩形双向板 ({lx:.2f}m x {ly:.2f}m, 厚{h:.0f}mm): "
        f"X向跨中弯矩={mx_mid:.2f} kN·m/m, 所需配筋={as_x_mid:.0f} mm²/m; "
        f"Y向跨中弯矩={my_mid:.2f} kN·m/m, 所需配筋={as_y_mid:.0f} mm²/m。"
    )

    return TwoWaySlabOutput(
        ratio_ly_lx=ratio,
        is_two_way=is_two_way,
        design_load_kpa=p_d,
        mx_mid_knm=mx_mid,
        my_mid_knm=my_mid,
        mx_support_knm=mx_sup,
        my_support_knm=my_sup,
        as_x_mid_mm2=as_x_mid,
        as_y_mid_mm2=as_y_mid,
        as_x_support_mm2=as_x_sup,
        as_y_support_mm2=as_y_sup,
        min_reinforcement_ratio=rho_min,
        passed=passed,
        summary=summary,
    )
