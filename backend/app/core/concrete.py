from __future__ import annotations

from math import pi, sqrt

from .common import (
    DISCLAIMER,
    STANDARDS,
    mode_number,
    mode_text,
    quantity_summary,
    result_status,
)
from .catalogs import MATERIAL_CATALOG_VERSION, REBAR_MATERIALS
from .loads import (
    axial_load_envelope,
    line_load_envelope,
    transferred_axial_load_envelope,
    transferred_line_load_envelope,
)
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    LoadDirection,
    Quantity,
    ReactionEnvelope,
)


CONCRETE = {
    "C25": {"fc": 11.9, "ft": 1.27, "ec": 28_000.0},
    "C30": {"fc": 14.3, "ft": 1.43, "ec": 30_000.0},
    "C35": {"fc": 16.7, "ft": 1.57, "ec": 31_500.0},
    "C40": {"fc": 19.1, "ft": 1.71, "ec": 32_500.0},
}
REBAR = {
    item["id"]: {
        "fy": float(item["fy_mpa"]),
        "fyv": float(item["fyv_mpa"]),
        "es": float(item["elastic_modulus_mpa"]),
        "xi_b": 0.518 if float(item["fy_mpa"]) <= 360 else 0.482,
    }
    for item in REBAR_MATERIALS
    if item["status"] in {"active", "restricted"} and item["fy_mpa"] is not None
}


def _materials(request: CalculationRequest) -> tuple[str, dict[str, float], str, dict[str, float]]:
    concrete_name = mode_text(
        request, "concrete_grade", quick_default="C30", allowed=set(CONCRETE)
    )
    rebar_name = mode_text(
        request, "rebar_grade", quick_default="HRB400", allowed=set(REBAR)
    )
    return concrete_name, CONCRETE[concrete_name], rebar_name, REBAR[rebar_name]


def _beam_geometry(request: CalculationRequest) -> tuple[float, float, float, float, float]:
    slab = request.module.value == "concrete_slab"
    b = 1000.0 if slab else mode_number(request, "b_mm", quick_default=250, minimum=100)
    h = mode_number(request, "h_mm", quick_default=150 if slab else 450, minimum=80)
    cover = mode_number(request, "cover_mm", quick_default=20 if slab else 30, minimum=10)
    bar_dia = mode_number(request, "bar_dia_mm", quick_default=12 if slab else 18, minimum=6)
    if slab:
        spacing = mode_number(request, "bar_spacing_mm", quick_default=150, minimum=50)
        as_mm2 = 1000 / spacing * pi * bar_dia**2 / 4
    else:
        bar_count = mode_number(request, "bar_count", quick_default=3, minimum=2)
        as_mm2 = bar_count * pi * bar_dia**2 / 4
    h0 = h - cover - bar_dia / 2
    if h0 <= 0:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_effective_depth", "保护层与钢筋尺寸导致有效高度不大于 0"
        )
    return b, h, cover, bar_dia, as_mm2


def calculate_concrete_member(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    concrete_name, concrete, rebar_name, rebar = _materials(request)
    b, h, cover, bar_dia, as_mm2 = _beam_geometry(request)
    h0 = h - cover - bar_dia / 2
    span_m = mode_number(request, "span_m", quick_default=3.0, minimum=0.3, maximum=20)
    support = mode_text(
        request, "support", quick_default="simple", allowed={"simple", "cantilever"}
    )
    slab = request.module.value == "concrete_slab"
    stirrup_name: str | None = None
    stirrup_rebar: dict[str, float] | None = None
    if not slab:
        stirrup_name = mode_text(
            request,
            "stirrup_grade",
            quick_default="HPB300",
            allowed=set(REBAR),
        )
        stirrup_rebar = REBAR[stirrup_name]
    tributary_width = 1.0 if slab else mode_number(
        request, "tributary_width_m", quick_default=1.0, minimum=0.05
    )
    density = 25.0
    self_weight = density * b / 1000 * h / 1000
    upstream_lines = request.inputs.get("upstream_reaction_envelopes")
    if isinstance(upstream_lines, list) and upstream_lines:
        if request.loads:
            from .errors import CalculationInputError

            raise CalculationInputError(
                "duplicate_member_load_source",
                "接收上游组合线荷载后不得再次提交普通荷载。",
                field="loads",
            )
        envelope = transferred_line_load_envelope(
            upstream_lines,
            automatic_self_weight_kn_m=self_weight,
        )
    else:
        envelope = line_load_envelope(
            request.loads,
            tributary_width_m=tributary_width,
            automatic_self_weight_kn_m=self_weight,
        )
    q_uls_signed = envelope.governing_uls.total.value
    q_sls_signed = envelope.governing_sls.total.value
    q_uls = abs(q_uls_signed)
    q_sls = abs(q_sls_signed)
    if support == "simple":
        moment_demand = q_uls * span_m**2 / 8
        shear_demand = q_uls * span_m / 2
        deflection_factor = 5 / 384
        deflection_limit = span_m * 1000 / (250 if slab else 300)
        reactions = {
            "left_vertical": Quantity(value=q_sls_signed * span_m / 2, unit="kN"),
            "right_vertical": Quantity(value=q_sls_signed * span_m / 2, unit="kN"),
        }
    else:
        moment_demand = q_uls * span_m**2 / 2
        shear_demand = q_uls * span_m
        deflection_factor = 1 / 8
        deflection_limit = span_m * 1000 / 200
        reactions = {
            "base_vertical": Quantity(value=q_sls_signed * span_m, unit="kN"),
            "base_moment": Quantity(
                value=q_sls_signed * span_m**2 / 2, unit="kN·m"
            ),
        }

    x = rebar["fy"] * as_mm2 / (concrete["fc"] * b)
    xb = rebar["xi_b"] * h0
    effective_x = min(x, xb)
    moment_capacity = rebar["fy"] * as_mm2 * (h0 - effective_x / 2) / 1e6
    rho = as_mm2 / (b * h0)
    rho_min = max(0.002, 0.45 * concrete["ft"] / rebar["fy"])
    rho_max = concrete["fc"] * rebar["xi_b"] / rebar["fy"]

    if slab:
        shear_capacity = 0.7 * concrete["ft"] * b * h0 / 1000
    else:
        stirrup_dia = mode_number(
            request, "stirrup_dia_mm", quick_default=8, minimum=6
        )
        stirrup_legs = mode_number(
            request, "stirrup_legs", quick_default=2, minimum=2
        )
        stirrup_spacing = mode_number(
            request, "stirrup_spacing_mm", quick_default=200, minimum=50
        )
        asv = stirrup_legs * pi * stirrup_dia**2 / 4
        assert stirrup_rebar is not None
        shear_capacity = (
            0.7 * concrete["ft"] * b * h0
            + stirrup_rebar["fyv"] * asv * h0 / stirrup_spacing
        ) / 1000

    length_mm = span_m * 1000
    ig = b * h**3 / 12
    m_sls = q_sls * span_m**2 / (8 if support == "simple" else 2)
    mcr = concrete["ft"] * ig / (h / 2) / 1e6
    ratio = min(1.0, mcr / max(m_sls, 1e-9))
    ie = max(0.35 * ig, ratio**3 * ig + (1 - ratio**3) * 0.35 * ig)
    deflection = deflection_factor * q_sls * length_mm**4 / (concrete["ec"] * ie)
    steel_stress = m_sls * 1e6 / max(0.87 * h0 * as_mm2, 1e-9)
    effective_rho = max(rho, 0.002)
    crack_width = (
        1.7
        * steel_stress
        / rebar["es"]
        * (1.9 * cover + 0.08 * bar_dia / effective_rho)
    )

    checks = [
        CheckResult(
            name="受弯承载力",
            demand=Quantity(value=moment_demand, unit="kN·m"),
            capacity=Quantity(value=moment_capacity, unit="kN·m"),
            utilization=moment_demand / max(moment_capacity, 1e-9),
            passed=moment_demand <= moment_capacity and x <= xb,
            reference="GB/T 50010-2010（2024局部修订）受弯构件（Beta映射）",
            note="超筋时即使名义承载力足够也判为不通过。",
        ),
        CheckResult(
            name="受剪承载力",
            demand=Quantity(value=shear_demand, unit="kN"),
            capacity=Quantity(value=shear_capacity, unit="kN"),
            utilization=shear_demand / max(shear_capacity, 1e-9),
            passed=shear_demand <= shear_capacity,
            reference=(
                "GB/T 50010-2010 板不配置箍筋时的受剪筛查（Beta映射）"
                if slab
                else "GB/T 50010-2010 受剪构件（Beta映射）"
            ),
        ),
        CheckResult(
            name="最小配筋",
            demand=Quantity(value=rho_min, unit="1"),
            capacity=Quantity(value=rho, unit="1"),
            utilization=rho_min / max(rho, 1e-9),
            passed=rho >= rho_min,
            reference="GB/T 50010-2010 最小配筋率",
        ),
        CheckResult(
            name="最大配筋",
            demand=Quantity(value=rho, unit="1"),
            capacity=Quantity(value=rho_max, unit="1"),
            utilization=rho / max(rho_max, 1e-9),
            passed=rho <= rho_max,
            reference="GB/T 50010-2010 界限受压区高度（Beta映射）",
        ),
        CheckResult(
            name="挠度",
            demand=Quantity(value=deflection, unit="mm"),
            capacity=Quantity(value=deflection_limit, unit="mm"),
            utilization=deflection / deflection_limit,
            passed=deflection <= deflection_limit,
            reference="GB 55001-2021 正常使用极限状态（有效刚度筛查）",
        ),
        CheckResult(
            name="裂缝宽度筛查",
            demand=Quantity(value=crack_width, unit="mm"),
            capacity=Quantity(value=0.3, unit="mm"),
            utilization=crack_width / 0.3,
            passed=crack_width <= 0.3,
            reference="GB/T 50010-2010 裂缝控制（Beta估算）",
            note="环境类别、长期作用和受力特征须由专业人员复核。",
        ),
    ]
    governing = max(checks, key=lambda item: item.utilization)
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status([item.utilization for item in checks]),  # type: ignore[arg-type]
        standards=STANDARDS["concrete"],
        input_summary=quantity_summary(
            {
                "concrete_grade": concrete_name,
                "rebar_grade": rebar_name,
                **({"stirrup_grade": stirrup_name} if stirrup_name else {}),
                "width": (b, "mm"),
                "depth": (h, "mm"),
                "effective_depth": (h0, "mm"),
                "reinforcement_area": (as_mm2, "mm²"),
                "span": (span_m, "m"),
                "support": support,
            }
        ),
        combinations=envelope.combinations,
        reactions=reactions,
        reaction_envelopes=[
            ReactionEnvelope(
                name="member_support",
                limit_state=combination.limit_state,
                combination_name=combination.name,
                direction=(
                    LoadDirection.UPLIFT
                    if combination.total.value < 0
                    else LoadDirection.GRAVITY
                ),
                components={
                    "Vy": Quantity(
                        value=(
                            combination.total.value * span_m / 2
                            if support == "simple"
                            else combination.total.value * span_m
                        ),
                        unit="kN",
                    ),
                    **(
                        {
                            "Mx": Quantity(
                                value=combination.total.value * span_m**2 / 2,
                                unit="kN·m",
                            )
                        }
                        if support == "cantilever"
                        else {}
                    ),
                },
            )
            for combination in envelope.combinations
        ],
        steps=[
            CalculationStep(
                name="受压区高度",
                equation="x = f_y A_s / (α₁ f_c b)",
                substitution=f"f_y={rebar['fy']:.1f} MPa, A_s={as_mm2:.1f} mm², f_c={concrete['fc']:.1f} MPa, b={b:.1f} mm",
                result=Quantity(value=x, unit="mm"),
                reference="GB/T 50010-2010（Beta映射）",
            ),
            CalculationStep(
                name="受弯承载力",
                equation="M_u = f_y A_s (h₀ - x/2)",
                substitution=f"h₀={h0:.1f} mm, x_eff={effective_x:.1f} mm",
                result=Quantity(value=moment_capacity, unit="kN·m"),
                reference="GB/T 50010-2010（Beta映射）",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="concrete_beta",
                message="裂缝、挠度及复杂受力为 Beta 筛查，不能替代完整专业复核。",
            )
        ],
        assumptions=[
            "矩形截面、单筋受弯；板按 1 m 宽条带。",
            "挠度采用有效刚度近似，裂缝宽度采用首期 Beta 估算。",
        ],
        applicability=["矩形梁", "单向板", "静力均布荷载"],
        catalog_versions={"materials": MATERIAL_CATALOG_VERSION},
        disclaimer=DISCLAIMER,
    )


def calculate_concrete_column(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    concrete_name, concrete, rebar_name, rebar = _materials(request)
    shape = mode_text(
        request, "shape", quick_default="rectangular", allowed={"rectangular", "circular"}
    )
    if shape == "rectangular":
        b = mode_number(request, "b_mm", quick_default=300, minimum=150)
        h = mode_number(request, "h_mm", quick_default=300, minimum=150)
        gross_area = b * h
        radius = min(b, h) / sqrt(12)
        lever_arm = 0.4 * h
        section_desc = f"{b:g}×{h:g} mm"
    else:
        diameter = mode_number(request, "diameter_mm", quick_default=350, minimum=150)
        gross_area = pi * diameter**2 / 4
        radius = diameter / 4
        lever_arm = 0.35 * diameter
        section_desc = f"Φ{diameter:g} mm"
    as_mm2 = mode_number(request, "reinforcement_area_mm2", quick_default=1608, minimum=100)
    length_m = mode_number(request, "height_m", quick_default=3.0, minimum=0.3)
    k = mode_number(request, "effective_length_factor", quick_default=1.0, minimum=0.2, maximum=3)
    moment_kn_m = mode_number(request, "design_moment_kn_m", quick_default=0.0, minimum=0)
    upstream_axial = request.inputs.get("upstream_reaction_envelopes")
    if isinstance(upstream_axial, list) and upstream_axial:
        if request.loads:
            from .errors import CalculationInputError

            raise CalculationInputError(
                "duplicate_member_load_source",
                "接收上游组合反力后不得再次提交普通荷载。",
                field="loads",
            )
        envelope = transferred_axial_load_envelope(upstream_axial)
    else:
        envelope = axial_load_envelope(request.loads)
    axial_kn = abs(envelope.governing_uls.total.value)
    slenderness = length_m * 1000 * k / radius
    phi = max(0.65, min(1.0, 1.0 - max(slenderness - 20, 0) / 300))
    concrete_area = max(gross_area - as_mm2, 0)
    axial_capacity = 0.9 * phi * (
        concrete["fc"] * concrete_area + rebar["fy"] * as_mm2
    ) / 1000
    moment_capacity = 0.8 * rebar["fy"] * as_mm2 * lever_arm / 1e6
    interaction = axial_kn / max(axial_capacity, 1e-9) + moment_kn_m / max(moment_capacity, 1e-9)
    reinforcement_ratio = as_mm2 / gross_area
    checks = [
        CheckResult(
            name="轴压承载力",
            demand=Quantity(value=axial_kn, unit="kN"),
            capacity=Quantity(value=axial_capacity, unit="kN"),
            utilization=axial_kn / max(axial_capacity, 1e-9),
            passed=axial_kn <= axial_capacity,
            reference="GB/T 50010-2010 轴心受压构件（Beta映射）",
        ),
        CheckResult(
            name="偏压相互作用筛查",
            demand=Quantity(value=interaction, unit="1"),
            capacity=Quantity(value=1, unit="1"),
            utilization=interaction,
            passed=interaction <= 1,
            reference="GB/T 50010-2010 偏心受压构件（简化Beta筛查）",
        ),
        CheckResult(
            name="纵筋配筋率",
            demand=Quantity(value=0.005, unit="1"),
            capacity=Quantity(value=reinforcement_ratio, unit="1"),
            utilization=0.005 / max(reinforcement_ratio, 1e-9),
            passed=0.005 <= reinforcement_ratio <= 0.05,
            reference="GB/T 50010-2010 柱纵向钢筋构造（项目复核）",
            note="同时要求配筋率不大于 5%。",
        ),
    ]
    governing = max(checks, key=lambda item: item.utilization)
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status([item.utilization for item in checks]),  # type: ignore[arg-type]
        standards=STANDARDS["concrete"],
        input_summary=quantity_summary(
            {
                "shape": shape,
                "section": section_desc,
                "height": (length_m, "m"),
                "effective_length_factor": (k, "1"),
                "reinforcement_area": (as_mm2, "mm²"),
                "design_moment": (moment_kn_m, "kN·m"),
            }
        ),
        combinations=envelope.combinations,
        reactions={
            "base_vertical": Quantity(
                value=envelope.governing_sls.total.value, unit="kN"
            ),
            "base_moment": Quantity(value=moment_kn_m, unit="kN·m"),
        },
        reaction_envelopes=[
            ReactionEnvelope(
                name="column_base",
                limit_state=combination.limit_state,
                combination_name=combination.name,
                direction=(
                    LoadDirection.UPLIFT
                    if combination.total.value < 0
                    else LoadDirection.GRAVITY
                ),
                components={
                    "N": Quantity(value=combination.total.value, unit="kN"),
                    "My": Quantity(value=moment_kn_m, unit="kN·m"),
                },
            )
            for combination in envelope.combinations
        ],
        steps=[
            CalculationStep(
                name="计算长细比",
                equation="λ = μL / i",
                substitution=f"μ={k:.2f}, L={length_m*1000:.1f} mm, i={radius:.1f} mm",
                result=Quantity(value=slenderness, unit="1"),
                reference="结构稳定基本关系",
            ),
            CalculationStep(
                name="轴压承载力",
                equation="N_u = 0.9φ(f_c A_c + f_y A_s)",
                substitution=f"φ={phi:.3f}",
                result=Quantity(value=axial_capacity, unit="kN"),
                reference="GB/T 50010-2010（Beta映射）",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=[
            CalculationWarning(
                severity="critical",
                code="column_interaction_beta",
                message="偏压采用简化相互作用筛查，不覆盖双向偏压、抗震和二阶精细分析。",
            )
        ],
        assumptions=["普通钢筋混凝土短柱/中长柱筛查。", "偏压承载力采用保守简化相互作用。"],
        applicability=["矩形柱", "圆柱", "单向偏压筛查"],
        catalog_versions={"materials": MATERIAL_CATALOG_VERSION},
        disclaimer=DISCLAIMER,
    )
