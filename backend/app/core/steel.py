from __future__ import annotations

from math import pi, sqrt

from .common import (
    DISCLAIMER,
    STANDARDS,
    mode_bool,
    mode_number,
    mode_text,
    quantity_summary,
    result_status,
)
from .errors import CalculationInputError
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
    DiagramPoint,
    DiagramSeries,
    LoadDirection,
    Quantity,
    ReactionEnvelope,
)
from .sections import SectionProperties, steel_section


STEEL = {
    "Q235B": {"fd": 215.0, "fy": 235.0, "fv": 125.0},
    "Q355B": {"fd": 305.0, "fy": 355.0, "fv": 175.0},
}
E_STEEL = 206_000.0

STEEL_DESIGN_STRENGTH = {
    "Q235B": (
        (16.0, 215.0, 125.0),
        (40.0, 205.0, 120.0),
        (100.0, 200.0, 115.0),
        (150.0, 190.0, 110.0),
    ),
    "Q355B": (
        (16.0, 305.0, 175.0),
        (40.0, 295.0, 170.0),
        (63.0, 290.0, 165.0),
        (80.0, 280.0, 160.0),
        (100.0, 270.0, 155.0),
        (150.0, 260.0, 150.0),
    ),
}


def steel_design_strength(grade_name: str, thickness_mm: float) -> dict[str, float]:
    if thickness_mm <= 0 or thickness_mm > 150:
        raise CalculationInputError(
            "unsupported_steel_thickness",
            "钢材设计强度分档仅覆盖厚度大于 0 且不超过 150 mm",
            field="t_mm",
            details={"thickness_mm": thickness_mm},
        )
    nominal = STEEL[grade_name]
    for upper, fd, fv in STEEL_DESIGN_STRENGTH[grade_name]:
        if thickness_mm <= upper:
            return {"fd": fd, "fy": nominal["fy"], "fv": fv}
    raise AssertionError("unreachable steel thickness band")


def _grade(
    request: CalculationRequest, section: SectionProperties
) -> tuple[str, dict[str, float], float]:
    name = mode_text(
        request,
        "steel_grade",
        quick_default="Q355B",
        allowed=set(STEEL),
    )
    if section.section_type == "H":
        thickness = max(
            float(request.inputs.get("tw_mm", 6)),
            float(request.inputs.get("tf_mm", 10)),
        )
    else:
        thickness = float(request.inputs.get("t_mm", 6))
    return name, steel_design_strength(name, thickness), thickness


def _combination_direction(total: float) -> LoadDirection:
    return LoadDirection.UPLIFT if total < 0 else LoadDirection.GRAVITY


def _beam_reaction_envelopes(
    combinations, support: str, span_m: float
) -> list[ReactionEnvelope]:
    envelopes: list[ReactionEnvelope] = []
    for combination in combinations:
        q = combination.total.value
        direction = _combination_direction(q)
        if support == "simple":
            reaction = q * span_m / 2
            for support_name in ("left", "right"):
                envelopes.append(
                    ReactionEnvelope(
                        name=f"{support_name}_support",
                        limit_state=combination.limit_state,
                        combination_name=combination.name,
                        direction=direction,
                        components={"Vy": Quantity(value=reaction, unit="kN")},
                    )
                )
        else:
            envelopes.append(
                ReactionEnvelope(
                    name="fixed_support",
                    limit_state=combination.limit_state,
                    combination_name=combination.name,
                    direction=direction,
                    components={
                        "Vy": Quantity(value=q * span_m, unit="kN"),
                        "Mx": Quantity(value=q * span_m**2 / 2, unit="kN·m"),
                    },
                )
            )
    return envelopes


def _section_with_mode(request: CalculationRequest) -> SectionProperties:
    inputs = dict(request.inputs)
    if request.mode.value == "quick":
        inputs.setdefault("section_type", "RHS")
        inputs.setdefault("h_mm", 200)
        inputs.setdefault("b_mm", 100)
        inputs.setdefault("t_mm", 6)
    return steel_section(inputs)


def _beam_diagrams(
    support: str, span_m: float, q_kn_m: float
) -> tuple[list[DiagramSeries], dict[str, Quantity]]:
    points_m = [span_m * index / 10 for index in range(11)]
    shear_points: list[DiagramPoint] = []
    moment_points: list[DiagramPoint] = []
    if support == "simple":
        reaction = q_kn_m * span_m / 2
        for x in points_m:
            shear = reaction - q_kn_m * x
            moment = reaction * x - q_kn_m * x**2 / 2
            shear_points.append(
                DiagramPoint(x=Quantity(value=x, unit="m"), value=Quantity(value=shear, unit="kN"))
            )
            moment_points.append(
                DiagramPoint(x=Quantity(value=x, unit="m"), value=Quantity(value=moment, unit="kN·m"))
            )
        reactions = {
            "left_vertical": Quantity(value=reaction, unit="kN"),
            "right_vertical": Quantity(value=reaction, unit="kN"),
        }
    else:
        for x in points_m:
            shear = q_kn_m * (span_m - x)
            moment = q_kn_m * (span_m - x) ** 2 / 2
            shear_points.append(
                DiagramPoint(x=Quantity(value=x, unit="m"), value=Quantity(value=shear, unit="kN"))
            )
            moment_points.append(
                DiagramPoint(x=Quantity(value=x, unit="m"), value=Quantity(value=moment, unit="kN·m"))
            )
        reactions = {
            "fixed_vertical": Quantity(value=q_kn_m * span_m, unit="kN"),
            "fixed_moment": Quantity(value=q_kn_m * span_m**2 / 2, unit="kN·m"),
        }
    return (
        [
            DiagramSeries(name="剪力图", points=shear_points),
            DiagramSeries(name="弯矩图", points=moment_points),
        ],
        reactions,
    )


def calculate_steel_beam(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    section = _section_with_mode(request)
    grade_name, grade, governing_thickness = _grade(request, section)
    support = mode_text(
        request,
        "support",
        quick_default="simple",
        allowed={"simple", "cantilever"},
    )
    span_m = mode_number(request, "span_m", quick_default=3.0, minimum=0.2, maximum=30)
    tributary_width = mode_number(
        request, "tributary_width_m", quick_default=1.0, minimum=0.05, maximum=20
    )
    include_self_weight = mode_bool(
        request, "include_self_weight", quick_default=True
    )
    lateral_restrained = mode_bool(
        request, "lateral_restrained", quick_default=True
    )
    if section.section_type == "H" and not lateral_restrained:
        raise CalculationInputError(
            "unsupported_unrestrained_open_section",
            "首期专业计算不覆盖无侧向约束 H 型钢梁的整体稳定设计",
            field="lateral_restrained",
        )

    upstream_lines = request.inputs.get("upstream_reaction_envelopes")
    if isinstance(upstream_lines, list) and upstream_lines:
        if request.loads:
            raise CalculationInputError("duplicate_member_load_source", "接收上游组合线荷载后不得再次提交普通荷载。", field="loads")
        envelope = transferred_line_load_envelope(
            upstream_lines,
            automatic_self_weight_kn_m=section.self_weight_kn_m if include_self_weight else 0,
        )
    else:
        envelope = line_load_envelope(
            request.loads,
            tributary_width_m=tributary_width,
            automatic_self_weight_kn_m=section.self_weight_kn_m if include_self_weight else 0,
        )
    q_uls_signed = envelope.governing_uls.total.value
    q_sls_signed = envelope.governing_sls.total.value
    q_uls = abs(q_uls_signed)
    q_sls = abs(q_sls_signed)
    length_mm = span_m * 1000
    if support == "simple":
        moment_kn_m = q_uls * span_m**2 / 8
        shear_kn = q_uls * span_m / 2
        deflection_mm = 5 * q_sls * length_mm**4 / (384 * E_STEEL * section.ix_mm4)
        deflection_limit = length_mm / 400
    else:
        moment_kn_m = q_uls * span_m**2 / 2
        shear_kn = q_uls * span_m
        deflection_mm = q_sls * length_mm**4 / (8 * E_STEEL * section.ix_mm4)
        deflection_limit = length_mm / 250

    bending_capacity = grade["fd"] * section.wx_mm3 / 1e6
    shear_capacity = grade["fv"] * section.shear_area_mm2 / 1000
    local_limit = (
        100 * 235 / grade["fy"]
        if section.section_type == "CHS"
        else (72 if section.section_type == "H" else 40) * sqrt(235 / grade["fy"])
    )
    checks = [
        CheckResult(
            name="抗弯承载力",
            demand=Quantity(value=moment_kn_m, unit="kN·m"),
            capacity=Quantity(value=bending_capacity, unit="kN·m"),
            utilization=moment_kn_m / bending_capacity,
            passed=moment_kn_m <= bending_capacity,
            reference="GB 50017-2017 钢构件受弯验算（Beta映射）",
        ),
        CheckResult(
            name="抗剪承载力",
            demand=Quantity(value=shear_kn, unit="kN"),
            capacity=Quantity(value=shear_capacity, unit="kN"),
            utilization=shear_kn / shear_capacity,
            passed=shear_kn <= shear_capacity,
            reference="GB 50017-2017 钢构件受剪验算（Beta映射）",
        ),
        CheckResult(
            name="挠度",
            demand=Quantity(value=deflection_mm, unit="mm"),
            capacity=Quantity(value=deflection_limit, unit="mm"),
            utilization=deflection_mm / deflection_limit,
            passed=deflection_mm <= deflection_limit,
            reference="GB 55001-2021 正常使用极限状态",
        ),
        CheckResult(
            name="局部稳定筛查",
            demand=Quantity(value=section.local_slenderness, unit="1"),
            capacity=Quantity(value=local_limit, unit="1"),
            utilization=section.local_slenderness / local_limit,
            passed=section.local_slenderness <= local_limit,
            reference="GB 50017-2017 板件宽厚比（简化筛查）",
            note="该项用于首期筛查，复杂截面仍需专业复核。",
        ),
    ]
    diagrams, _ = _beam_diagrams(support, span_m, q_uls_signed)
    _, reactions = _beam_diagrams(support, span_m, q_sls_signed)
    warnings: list[CalculationWarning] = []
    if q_uls == 0:
        warnings.append(
            CalculationWarning(
                severity="warning",
                code="zero_load",
                message="总设计荷载为 0，请确认是否遗漏荷载。",
            )
        )
    if request.mode.value == "quick":
        warnings.append(
            CalculationWarning(
                severity="info",
                code="quick_mode",
                message="快算结果包含已确认的场景默认假定。",
            )
        )
    utilizations = [item.utilization for item in checks]
    governing = max(checks, key=lambda item: item.utilization)
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status(utilizations),  # type: ignore[arg-type]
        standards=STANDARDS["steel"],
        input_summary=quantity_summary(
            {
                "steel_grade": grade_name,
                "governing_thickness": (governing_thickness, "mm"),
                "design_strength": (grade["fd"], "MPa"),
                "section": section.description,
                "support": support,
                "span": (span_m, "m"),
                "tributary_width": (tributary_width, "m"),
                "include_self_weight": include_self_weight,
                "lateral_restrained": lateral_restrained,
            }
        ),
        combinations=envelope.combinations,
        reactions=reactions,
        reaction_envelopes=_beam_reaction_envelopes(
            envelope.combinations, support, span_m
        ),
        diagrams=diagrams,
        steps=[
            CalculationStep(
                name="最大弯矩",
                equation="M = qL²/8" if support == "simple" else "M = qL²/2",
                substitution=f"q={q_uls:.3f} kN/m, L={span_m:.3f} m",
                result=Quantity(value=moment_kn_m, unit="kN·m"),
                reference="结构力学均布荷载基本公式",
            ),
            CalculationStep(
                name="抗弯承载力",
                equation="M_Rd = f_d × W",
                substitution=f"f_d={grade['fd']:.1f} MPa, W={section.wx_mm3:.1f} mm³",
                result=Quantity(value=bending_capacity, unit="kN·m"),
                reference="GB 50017-2017（Beta映射）",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=warnings,
        assumptions=[
            "构件按等截面、线弹性、平面受力计算。",
            "均布面荷载通过从属宽度换算为线荷载。",
            "H 型钢梁仅在有可靠侧向约束时纳入首期适用范围。",
        ],
        applicability=[
            "简支梁或悬挑梁",
            "静力均布荷载",
            "Q235B/Q355B，首期设计值映射",
        ],
        disclaimer=DISCLAIMER,
    )


def _column_phi(slenderness: float, yield_strength: float) -> float:
    lambda_bar = slenderness / pi * sqrt(yield_strength / E_STEEL)
    if lambda_bar <= 0.215:
        return max(0.0, 1.0 - 0.65 * lambda_bar**2)
    alpha2, alpha3 = 0.965, 0.300
    root = (alpha2 + alpha3 * lambda_bar + lambda_bar**2) ** 2 - 4 * lambda_bar**2
    return max(
        0.0,
        (
            alpha2
            + alpha3 * lambda_bar
            + lambda_bar**2
            - sqrt(max(root, 0.0))
        )
        / (2 * lambda_bar**2),
    )


def calculate_steel_column(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    section = _section_with_mode(request)
    grade_name, grade, governing_thickness = _grade(request, section)
    height_m = mode_number(request, "height_m", quick_default=3.0, minimum=0.2, maximum=30)
    effective_length_factor = mode_number(
        request, "effective_length_factor", quick_default=1.0, minimum=0.2, maximum=3
    )
    raw_upstream = request.inputs.get("upstream_reaction_envelopes")
    if isinstance(raw_upstream, list) and raw_upstream:
        if request.loads:
            raise CalculationInputError("duplicate_member_load_source", "接收上游组合反力后不得再次提交普通轴力荷载。", field="loads")
        envelope = transferred_axial_load_envelope(raw_upstream)
        upstream_moment = max(
            [
                abs(float(((item.get("components") or {}).get("My") or (item.get("components") or {}).get("Mx") or {}).get("value", 0.0)))
                for item in raw_upstream
            ],
            default=0.0,
        )
    else:
        envelope = axial_load_envelope(request.loads)
        upstream_moment = 0.0
    moment_kn_m = max(
        mode_number(request, "design_moment_kn_m", quick_default=0.0, minimum=0),
        upstream_moment,
    )
    axial_kn = abs(envelope.governing_uls.total.value)
    slenderness = height_m * 1000 * effective_length_factor / min(section.rx_mm, section.ry_mm)
    phi = _column_phi(slenderness, grade["fy"])
    axial_capacity = phi * section.area_mm2 * grade["fd"] / 1000
    moment_capacity = grade["fd"] * section.wx_mm3 / 1e6
    interaction = axial_kn / axial_capacity + moment_kn_m / moment_capacity
    checks = [
        CheckResult(
            name="轴压稳定承载力",
            demand=Quantity(value=axial_kn, unit="kN"),
            capacity=Quantity(value=axial_capacity, unit="kN"),
            utilization=axial_kn / axial_capacity,
            passed=axial_kn <= axial_capacity,
            reference="GB 50017-2017 轴心受压构件稳定（Beta映射）",
        ),
        CheckResult(
            name="长细比",
            demand=Quantity(value=slenderness, unit="1"),
            capacity=Quantity(value=150, unit="1"),
            utilization=slenderness / 150,
            passed=slenderness <= 150,
            reference="GB 50017-2017 构件长细比限值（项目复核）",
        ),
        CheckResult(
            name="压弯组合",
            demand=Quantity(value=interaction, unit="1"),
            capacity=Quantity(value=1, unit="1"),
            utilization=interaction,
            passed=interaction <= 1,
            reference="GB 50017-2017 压弯构件线性相互作用筛查",
            note="首期采用保守线性相互作用，专业模式须复核二阶效应。",
        ),
    ]
    governing = max(checks, key=lambda item: item.utilization)
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status([item.utilization for item in checks]),  # type: ignore[arg-type]
        standards=STANDARDS["steel"],
        input_summary=quantity_summary(
            {
                "steel_grade": grade_name,
                "governing_thickness": (governing_thickness, "mm"),
                "design_strength": (grade["fd"], "MPa"),
                "section": section.description,
                "height": (height_m, "m"),
                "effective_length_factor": (effective_length_factor, "1"),
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
                direction=_combination_direction(combination.total.value),
                components={
                    "N": Quantity(value=combination.total.value, unit="kN"),
                    "My": Quantity(value=moment_kn_m, unit="kN·m"),
                },
            )
            for combination in envelope.combinations
        ],
        steps=[
            CalculationStep(
                name="构件长细比",
                equation="λ = μL / i_min",
                substitution=f"μ={effective_length_factor:.3f}, L={height_m*1000:.1f} mm, i={min(section.rx_mm, section.ry_mm):.1f} mm",
                result=Quantity(value=slenderness, unit="1"),
                reference="GB 50017-2017",
            ),
            CalculationStep(
                name="稳定承载力",
                equation="N_Rd = φAf_d",
                substitution=f"φ={phi:.3f}, A={section.area_mm2:.1f} mm², f_d={grade['fd']:.1f} MPa",
                result=Quantity(value=axial_capacity, unit="kN"),
                reference="GB 50017-2017（Beta映射）",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="second_order_review",
                message="压弯构件尚未自动计入结构整体二阶效应，专业模式必须复核。",
            )
        ],
        assumptions=["等截面轴压/单向压弯构件。", "稳定系数采用首期 Beta 映射曲线。"],
        applicability=["轴心受压柱", "单向小偏心压弯筛查"],
        disclaimer=DISCLAIMER,
    )
