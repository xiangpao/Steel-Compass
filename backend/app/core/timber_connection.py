from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Literal

from .errors import CalculationInputError

SideMemberType = Literal["timber", "steel_thin", "steel_thick"]
FastenerType = Literal["bolt", "dowel", "screw"]


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
class TimberConnectionInput:
    fastener_type: FastenerType = "dowel"
    fastener_diameter_mm: float = 12.0     # 销轴/螺栓直径 d (mm)
    fastener_fy_mpa: float = 400.0         # 销轴屈服强度 f_yb (MPa)
    main_thickness_mm: float = 80.0        # 主木构件厚度 t1 (mm)
    side_thickness_mm: float = 40.0        # 侧木构件厚度 t2 (mm)
    side_member_type: SideMemberType = "timber"
    timber_fh_mpa: float = 25.0            # 木材孔壁承压强度 f_h (MPa)
    num_fasteners: int = 4                 # 销轴数量 n
    shear_force_kn: float = 15.0           # 节点设计剪力 V (kN)


@dataclass(frozen=True)
class TimberConnectionOutput:
    governing_mode: str                   # 控制破坏模式 (e.g., "Mode IV (Dual Plastic Hinges)")
    single_fastener_capacity_kn: float     # 单个销轴抗剪承载力设计值 Rd (kN)
    total_capacity_kn: float               # 节点总抗剪承载力设计值 VR (kN)
    utilization: float                     # 剪力利用率 V / VR
    passed: bool
    mode_capacities_kn: dict[str, float]  # 各 Johansen 破坏模式对应承载力
    summary: str


def calculate_timber_connection(inp: TimberConnectionInput) -> TimberConnectionOutput:
    """GB/T 50005-2017 木结构销轴类紧固件 Johansen 屈服理论抗剪承载力计算。"""
    d = _positive(inp.fastener_diameter_mm, "fastener_diameter_mm")
    fy = _positive(inp.fastener_fy_mpa, "fastener_fy_mpa")
    t1 = _positive(inp.main_thickness_mm, "main_thickness_mm")
    t2 = _positive(inp.side_thickness_mm, "side_thickness_mm")
    fh1 = _positive(inp.timber_fh_mpa, "timber_fh_mpa")
    n_fasteners = int(_positive(inp.num_fasteners, "num_fasteners"))
    v_design = _number(inp.shear_force_kn, "shear_force_kn")

    if inp.side_member_type == "steel_thick":
        fh2 = 2.0 * fh1
    elif inp.side_member_type == "steel_thin":
        fh2 = 1.2 * fh1
    else:
        fh2 = fh1

    # 1. 销轴屈服弯矩 My (N·mm)
    m_y = 0.3 * fy * (d ** 2.6)

    # 2. Johansen 屈服模式计算 (单剪双构件模型)
    beta = fh2 / fh1

    # Mode Im: 主构件压屈
    r_im = fh1 * t1 * d

    # Mode Is: 侧构件压屈
    r_is = fh2 * t2 * d

    # Mode II: 主侧构件压屈
    r_ii = (fh1 * t1 * d / (1.0 + beta)) * (sqrt(beta + 2.0 * (beta**2) * (1.0 + t2/t1 + (t2/t1)**2) + (beta**3)*(t2/t1)**2) - beta * (1.0 + t2/t1))

    # Mode IIIm: 主构件孔壁压屈 + 销轴在主构件形成 1 个塑性铰
    r_iiim = (fh1 * t1 * d / (1.0 + 2.0*beta)) * (sqrt(2.0*beta*(1.0 + beta) + (4.0*beta*(2.0 + beta)*m_y)/(fh1 * d * (t1**2))) - beta)

    # Mode IIIs: 侧构件孔壁压屈 + 销轴在侧构件形成 1 个塑性铰
    r_iiis = (fh1 * t2 * d / (2.0 + beta)) * (sqrt(2.0*beta**2 * (1.0 + beta) + (4.0*beta*(1.0 + 2.0*beta)*m_y)/(fh1 * d * (t2**2))) - beta)

    # Mode IV: 销轴在主侧构件缝两侧形成 2 个塑性铰
    r_iv = sqrt((4.0 * beta) / (1.0 + beta)) * sqrt(2.0 * m_y * fh1 * d)

    modes = {
        "Mode Im (Main Member Bearing)": r_im / 1000.0,
        "Mode Is (Side Member Bearing)": r_is / 1000.0,
        "Mode II (Combined Bearing)": r_ii / 1000.0,
        "Mode IIIm (Main Plastic Hinge)": r_iiim / 1000.0,
        "Mode IIIs (Side Plastic Hinge)": r_iiis / 1000.0,
        "Mode IV (Dual Plastic Hinges)": r_iv / 1000.0,
    }

    # 控制破坏模式与单销轴承载力 (kN)
    governing_mode, single_cap_kn = min(modes.items(), key=lambda item: item[1])

    # 3. 节点总承载力 VR (kN)
    total_cap_kn = single_cap_kn * n_fasteners
    utilization = v_design / max(total_cap_kn, 1e-6)
    passed = utilization <= 1.0

    summary = (
        f"木结构销轴节点 ({n_fasteners}x d{d:.0f}mm): "
        f"控制模式={governing_mode}, 单销轴承载力={single_cap_kn:.2f} kN, "
        f"节点总承载力={total_cap_kn:.2f} kN, 剪力利用率={utilization:.2%} ({'满足' if passed else '超限'})。"
    )

    return TimberConnectionOutput(
        governing_mode=governing_mode,
        single_fastener_capacity_kn=single_cap_kn,
        total_capacity_kn=total_cap_kn,
        utilization=utilization,
        passed=passed,
        mode_capacities_kn=modes,
        summary=summary,
    )
