"""GB 50010-2010 Section 9.7 Concrete Embedded Plate & Anchor Rebar Design Solver.

Calculates resistance and required anchor steel area As, Asb under combined actions:
Tension N (or Compression N), Bending M, Shear V according to GB 50010-2010 Section 9.7.6~9.7.9.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import sqrt, ceil, pi, sin
from typing import Literal

from pydantic import BaseModel, Field

from .errors import CalculationInputError
from .schemas import CheckResult, Quantity, TypedInputValue, WallAnchorInputs


def _unit(unit: str) -> str:
    return (
        unit.strip()
        .replace("·", "*")
        .replace("⋅", "*")
        .replace("路", "*")
        .replace(" ", "")
        .lower()
    )


LENGTH_MM = {"mm": 1.0, "m": 1000.0}
FORCE_KN = {"kn": 1.0, "n": 0.001}
MOMENT_KNM = {"kn*m": 1.0, "n*mm": 1.0e-6}
STRESS_MPA = {"mpa": 1.0, "gpa": 1000.0}
SCALAR = {"1": 1.0}
ANGLE_DEG = {"deg": 1.0, "°": 1.0}


def _convert(
    value: TypedInputValue,
    factors: Mapping[str, float],
    *,
    field: str,
) -> float:
    canonical = _unit(value.unit)
    if canonical not in factors:
        raise CalculationInputError(
            "invalid_unit",
            f"{field} 的单位 {value.unit!r} 不受支持。",
            field=field,
            details={"unit": value.unit, "supported_units": sorted(factors)},
        )
    return value.value * factors[canonical]


def _integer(value: TypedInputValue, *, field: str) -> int:
    number = _convert(value, SCALAR, field=field)
    if not number.is_integer():
        raise CalculationInputError(
            "invalid_integer",
            f"{field} 必须是整数。",
            field=field,
        )
    return int(number)


class EmbeddedPlateInput(BaseModel):
    """Input parameters for GB 50010 embedded plate with anchor rebars."""

    plate_width_mm: float = Field(gt=0, description="预埋件锚板宽度 b (mm)")
    plate_height_mm: float = Field(gt=0, description="预埋件锚板高度 h (mm)")
    plate_thickness_mm: float = Field(gt=0, description="锚板厚度 t (mm)")
    
    # 直锚筋参数
    rebar_count: int = Field(ge=2, description="直锚筋总根数 (通常4根或更多)")
    rebar_rows: int = Field(ge=2, description="直锚筋排数 (最外层排距 y1)")
    rebar_diameter_mm: float = Field(gt=0, description="直锚筋直径 d (mm)")
    rebar_fy_mpa: float = Field(gt=0, default=360.0, description="直锚筋抗拉设计强度 fy (MPa)")
    rebar_length_mm: float = Field(gt=0, description="直锚筋锚固长度 la (mm)")
    
    # 弯折锚筋参数 (可选)
    bent_rebar_count: int = Field(ge=0, default=0, description="弯折锚筋根数 (用于分担剪力)")
    bent_rebar_diameter_mm: float = Field(ge=0, default=0.0, description="弯折锚筋直径 (mm)")
    bent_rebar_angle_deg: float = Field(ge=15.0, le=60.0, default=45.0, description="弯折锚筋倾角 (度)")
    
    # 混凝土及边距
    concrete_fc_mpa: float = Field(gt=0, default=14.3, description="混凝土轴心抗压强度设计值 fc (MPa, C30对应14.3)")
    concrete_ft_mpa: float = Field(gt=0, default=1.43, description="混凝土轴心抗拉强度设计值 ft (MPa)")
    edge_distance_x_mm: float = Field(gt=0, description="锚筋至锚板边缘距离 cx (mm)")
    edge_distance_y_mm: float = Field(gt=0, description="锚筋至锚板边缘距离 cy (mm)")
    
    # 作用效应组合 (ULS)
    n_design_kn: float = Field(default=0.0, description="轴向设计力 N (kN, >0为拉力, <0为压力)")
    m_design_kn_m: float = Field(default=0.0, description="设计弯矩 M (kN·m)")
    v_design_kn: float = Field(default=0.0, description="设计剪力 V (kN)")


class EmbeddedPlateResult(BaseModel):
    """Calculation and verification output for GB 50010 embedded plate."""

    status: Literal["passed", "failed"]
    as_provided_mm2: float
    as_required_mm2: float
    v_capacity_kn: float
    governing_utilization: float
    checks: list[CheckResult]
    warnings: list[str]


def calculate_gb50010_embedded_plate(input_data: EmbeddedPlateInput) -> EmbeddedPlateResult:
    """Calculate GB 50010-2010 Section 9.7 embedded plate rebar area and capacities."""

    b = input_data.plate_width_mm
    h = input_data.plate_height_mm
    t = input_data.plate_thickness_mm
    d = input_data.rebar_diameter_mm
    n_rebar = input_data.rebar_count
    rows = input_data.rebar_rows
    fy = input_data.rebar_fy_mpa
    la = input_data.rebar_length_mm
    fc = input_data.concrete_fc_mpa
    ft = input_data.concrete_ft_mpa
    cx = input_data.edge_distance_x_mm
    cy = input_data.edge_distance_y_mm
    
    N = input_data.n_design_kn
    M = abs(input_data.m_design_kn_m)
    V = abs(input_data.v_design_kn)

    # 1. 几何构造校验 (GB 50010 第 9.7.2, 9.7.3 条)
    # 最外层锚筋中心距离 y1
    y1 = h - 2 * cy
    if y1 <= 0:
        raise CalculationInputError(
            "invalid_embedded_plate_geometry",
            "锚筋边距 cy 过大，导致锚筋受力力臂 y1 <= 0。",
            field="edge_distance_y_mm",
        )
    
    # 锚筋间距 s
    cols = max(1, n_rebar // rows)
    x_spacing = (b - 2 * cx) / max(1, cols - 1) if cols > 1 else (b - 2 * cx)
    y_spacing = y1 / max(1, rows - 1) if rows > 1 else y1
    min_spacing = min(x_spacing, y_spacing)
    
    # 2. 剪力项锚筋受力系数 alpha_v (GB 50010 第 9.7.6 条)
    # alpha_v = (4.0 - 0.08 * d) * sqrt(fc / fy), 且当 alpha_v < 0.6 时取 0.6
    alpha_v_raw = (4.0 - 0.08 * d) * sqrt(fc / fy)
    alpha_v = max(0.6, alpha_v_raw)

    # 锚筋受力修正系数 alpha_b (直锚筋取 1.0)
    alpha_b = 1.0
    
    # 内力臂 z
    z = 0.8 * y1

    # 3. 弯折锚筋分担剪力 Vb (GB 50010 第 9.7.8 条)
    v_bent_capacity = 0.0
    if input_data.bent_rebar_count > 0 and input_data.bent_rebar_diameter_mm > 0:
        ab_area = input_data.bent_rebar_count * (pi * input_data.bent_rebar_diameter_mm**2 / 4)
        rad = input_data.bent_rebar_angle_deg * pi / 180.0
        # 弯折锚筋抗剪设计承载力 Vb = 0.8 * fy * ab_area * sin(rad)
        v_bent_capacity = 0.8 * fy * ab_area * sin(rad) / 1000.0

    v_rem_direct = max(0.0, V - v_bent_capacity)

    # 4. 所需直锚筋截面面积 As_required 计算 (GB 50010 第 9.7.6 与 9.7.7 条)
    as_provided = n_rebar * (pi * d**2 / 4)
    
    if N >= 0:
        # 受拉、弯、剪作用 (GB 50010 公式 9.7.6-1)
        # As >= N / (alpha_b * fy) + M / (alpha_b * fy * z) + V_rem / (alpha_b * alpha_v * fy)
        term_n = (N * 1000.0) / (alpha_b * fy)
        term_m = (M * 1e6) / (alpha_b * fy * z)
        term_v = (v_rem_direct * 1000.0) / (alpha_b * alpha_v * fy)
        as_required = term_n + term_m + term_v
    else:
        # 受压、弯、剪作用 (GB 50010 公式 9.7.7-1)
        # As >= (M - 0.4 * |N| * z) / (alpha_b * fy * z) + (V_rem - 0.3 * |N|) / (alpha_b * alpha_v * fy)
        abs_n = abs(N)
        term_m = max(0.0, (M * 1e6 - 0.4 * abs_n * 1000.0 * z)) / (alpha_b * fy * z)
        term_v = max(0.0, (v_rem_direct * 1000.0 - 0.3 * abs_n * 1000.0)) / (alpha_b * alpha_v * fy)
        as_required = term_m + term_v

    # 最小构造配筋要求 (锚筋直径 >= 10mm, 锚板厚度 t >= d / 8)
    min_thickness = max(6.0, d / 8.0)

    # 直锚筋最小锚固长度 lab (GB 50010 第 8.3.1 条)
    # lab = alpha * (fy / ft) * d, 常见带肋钢筋 alpha 取 0.14
    lab = 0.14 * (fy / ft) * d
    
    # 5. 校验列表构建
    checks: list[CheckResult] = []
    
    # 1) 直锚筋截面面积验算
    util_as = as_required / max(as_provided, 1e-9)
    checks.append(
        CheckResult(
            name="直锚筋截面面积验算",
            demand=Quantity(value=as_required, unit="mm²"),
            capacity=Quantity(value=as_provided, unit="mm²"),
            utilization=util_as,
            passed=as_provided >= as_required,
            reference="GB 50010-2010 公式 9.7.6-1 / 9.7.7-1",
            note="包含拉/压、弯、剪复合作用下的理论计算截面面积。",
        )
    )

    # 2) 锚板厚度强检
    util_t = min_thickness / max(t, 1e-9)
    checks.append(
        CheckResult(
            name="锚板最小厚度强检",
            demand=Quantity(value=min_thickness, unit="mm"),
            capacity=Quantity(value=t, unit="mm"),
            utilization=util_t,
            passed=t >= min_thickness,
            reference="GB 50010-2010 第 9.7.3 条（t >= d/8 且 t >= 6mm）",
        )
    )

    # 3) 锚筋最小间距强检
    req_spacing = 3.0 * d
    util_spacing = req_spacing / max(min_spacing, 1e-9)
    checks.append(
        CheckResult(
            name="锚筋最小间距强检",
            demand=Quantity(value=req_spacing, unit="mm"),
            capacity=Quantity(value=min_spacing, unit="mm"),
            utilization=util_spacing,
            passed=min_spacing >= req_spacing,
            reference="GB 50010-2010 第 9.7.3 条（间距 s >= 3d）",
        )
    )

    # 4) 锚筋最小边距强检
    req_edge = max(45.0, 3.0 * d)
    min_edge = min(cx, cy)
    util_edge = req_edge / max(min_edge, 1e-9)
    checks.append(
        CheckResult(
            name="锚筋最小边距强检",
            demand=Quantity(value=req_edge, unit="mm"),
            capacity=Quantity(value=min_edge, unit="mm"),
            utilization=util_edge,
            passed=min_edge >= req_edge,
            reference="GB 50010-2010 第 9.7.3 条（边距 c >= 3d 且 c >= 45mm）",
        )
    )

    # 5) 直锚筋锚固长度验算
    util_la = lab / max(la, 1e-9)
    checks.append(
        CheckResult(
            name="直锚筋基本锚固长度验算",
            demand=Quantity(value=lab, unit="mm"),
            capacity=Quantity(value=la, unit="mm"),
            utilization=util_la,
            passed=la >= lab,
            reference="GB 50010-2010 第 9.7.4 条 & 第 8.3.1 条",
            note="未加末端弯钩/贴角焊锚板时须满足基本锚固长度 lab。",
        )
    )

    governing_utilization = max(c.utilization for c in checks)
    status: Literal["passed", "failed"] = "passed" if all(c.passed for c in checks) else "failed"

    warnings: list[str] = []
    if d < 10.0:
        warnings.append("GB 50010 第 9.7.3 条规定预埋件直锚筋直径不宜小于 10mm。")

    return EmbeddedPlateResult(
        status=status,
        as_provided_mm2=as_provided,
        as_required_mm2=as_required,
        v_capacity_kn=V / max(util_as, 1e-9) if util_as > 0 else V,
        governing_utilization=governing_utilization,
        checks=checks,
        warnings=warnings,
    )


from .common import DISCLAIMER, STANDARDS, mode_number, quantity_summary
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
)


def calculate_wall_anchor(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    """Standard engine adapter for GB 50010 embedded plate & anchor rebar design."""

    typed = request.typed_inputs
    if isinstance(typed, WallAnchorInputs):
        plate_w = _convert(typed.plate_width, LENGTH_MM, field="plate_width")
        plate_h = _convert(typed.plate_height, LENGTH_MM, field="plate_height")
        plate_t = _convert(typed.plate_thickness, LENGTH_MM, field="plate_thickness")
        rebar_count = _integer(typed.rebar_count, field="rebar_count")
        rebar_rows = _integer(typed.rebar_rows, field="rebar_rows")
        rebar_d = _convert(typed.rebar_diameter, LENGTH_MM, field="rebar_diameter")
        rebar_fy = _convert(typed.rebar_fy, STRESS_MPA, field="rebar_fy")
        rebar_la = _convert(typed.rebar_length, LENGTH_MM, field="rebar_length")
        bent_count = (
            _integer(typed.bent_rebar_count, field="bent_rebar_count")
            if typed.bent_rebar_count is not None
            else 0
        )
        bent_d = (
            _convert(typed.bent_rebar_diameter, LENGTH_MM, field="bent_rebar_diameter")
            if typed.bent_rebar_diameter is not None
            else 0.0
        )
        bent_angle = (
            _convert(typed.bent_rebar_angle, ANGLE_DEG, field="bent_rebar_angle")
            if typed.bent_rebar_angle is not None
            else 45.0
        )
        fc = _convert(typed.concrete_fc, STRESS_MPA, field="concrete_fc")
        ft = _convert(typed.concrete_ft, STRESS_MPA, field="concrete_ft")
        cx = _convert(typed.edge_distance_x, LENGTH_MM, field="edge_distance_x")
        cy = _convert(typed.edge_distance_y, LENGTH_MM, field="edge_distance_y")
        n_kn = _convert(typed.n_design, FORCE_KN, field="n_design")
        m_kn_m = _convert(typed.m_design, MOMENT_KNM, field="m_design")
        v_kn = _convert(typed.v_design, FORCE_KN, field="v_design")
    else:
        # Read compatibility for pre-Schema-3.2 saved requests.
        plate_w = mode_number(request, "plate_width_mm", quick_default=250.0, minimum=80.0, maximum=1500.0)
        plate_h = mode_number(request, "plate_height_mm", quick_default=250.0, minimum=80.0, maximum=1500.0)
        plate_t = mode_number(request, "plate_thickness_mm", quick_default=12.0, minimum=6.0, maximum=50.0)
        rebar_count = int(mode_number(request, "rebar_count", quick_default=4.0, minimum=2.0, maximum=32.0))
        rebar_rows = int(mode_number(request, "rebar_rows", quick_default=2.0, minimum=2.0, maximum=8.0))
        rebar_d = mode_number(request, "rebar_diameter_mm", quick_default=16.0, minimum=8.0, maximum=40.0)
        rebar_fy = mode_number(request, "rebar_fy_mpa", quick_default=360.0, minimum=200.0, maximum=500.0)
        rebar_la = mode_number(request, "rebar_length_mm", quick_default=400.0, minimum=100.0, maximum=1500.0)
        bent_count = int(mode_number(request, "bent_rebar_count", quick_default=0.0, minimum=0.0, maximum=16.0))
        bent_d = mode_number(request, "bent_rebar_diameter_mm", quick_default=0.0, minimum=0.0, maximum=40.0)
        bent_angle = mode_number(request, "bent_rebar_angle_deg", quick_default=45.0, minimum=15.0, maximum=60.0)
        fc = mode_number(request, "concrete_fc_mpa", quick_default=14.3, minimum=7.2, maximum=30.0)
        ft = mode_number(request, "concrete_ft_mpa", quick_default=1.43, minimum=0.9, maximum=3.0)
        cx = mode_number(request, "edge_distance_x_mm", quick_default=50.0, minimum=20.0, maximum=300.0)
        cy = mode_number(request, "edge_distance_y_mm", quick_default=50.0, minimum=20.0, maximum=300.0)
        n_kn = mode_number(request, "n_design_kn", quick_default=0.0, minimum=-1000.0, maximum=1000.0)
        m_kn_m = mode_number(request, "m_design_kn_m", quick_default=0.0, minimum=0.0, maximum=500.0)
        v_kn = mode_number(request, "v_design_kn", quick_default=20.0, minimum=0.0, maximum=500.0)

    input_data = EmbeddedPlateInput(
        plate_width_mm=plate_w,
        plate_height_mm=plate_h,
        plate_thickness_mm=plate_t,
        rebar_count=rebar_count,
        rebar_rows=rebar_rows,
        rebar_diameter_mm=rebar_d,
        rebar_fy_mpa=rebar_fy,
        rebar_length_mm=rebar_la,
        bent_rebar_count=bent_count,
        bent_rebar_diameter_mm=bent_d,
        bent_rebar_angle_deg=bent_angle,
        concrete_fc_mpa=fc,
        concrete_ft_mpa=ft,
        edge_distance_x_mm=cx,
        edge_distance_y_mm=cy,
        n_design_kn=n_kn,
        m_design_kn_m=m_kn_m,
        v_design_kn=v_kn,
    )

    res = calculate_gb50010_embedded_plate(input_data)
    governing = max(res.checks, key=lambda c: c.utilization)

    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=res.status,
        result_class="professional_check",
        standards=[*STANDARDS["concrete"], "GB 50010-2010 第 9.7 节 预埋件"],
        input_summary=quantity_summary(
            {
                "plate_dimensions": f"{plate_w:.0f}x{plate_h:.0f}x{plate_t:.0f} mm",
                "rebar_config": f"{rebar_count}d{rebar_d:.0f} (la={rebar_la:.0f}mm)",
                "concrete_fc": (fc, "MPa"),
                "n_design": (n_kn, "kN"),
                "m_design": (m_kn_m, "kN·m"),
                "v_design": (v_kn, "kN"),
            }
        ),
        combinations=[],
        reactions={},
        steps=[
            CalculationStep(
                name="直锚筋实际面积",
                equation="As_provided = n * pi * d^2 / 4",
                substitution=f"n={rebar_count}, d={rebar_d} mm",
                result=Quantity(value=res.as_provided_mm2, unit="mm²"),
                reference="GB 50010-2010 第 9.7.3 条",
            ),
            CalculationStep(
                name="直锚筋理论计算面积",
                equation="As_required",
                substitution=f"N={n_kn} kN, M={m_kn_m} kN·m, V={v_kn} kN",
                result=Quantity(value=res.as_required_mm2, unit="mm²"),
                reference="GB 50010-2010 公式 9.7.6-1",
            ),
        ],
        checks=res.checks,
        governing_check=governing.name,
        warnings=[CalculationWarning(severity="info", code="wall_anchor_checked", message=w) for w in res.warnings],
        assumptions=[
            "直锚筋对称布置，锚板为刚性受力板。",
            "剪拉/剪压复合作用遵循 GB 50010-2010 第 9.7 节推导模型。",
        ],
        applicability=[
            "混凝土结构预埋件直锚筋与弯折锚筋验算",
            "剪受拉、剪受压、弯矩复合作用节点强检",
        ],
        disclaimer=DISCLAIMER,
    )
