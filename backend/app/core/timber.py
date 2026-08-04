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
from .loads import axial_load_envelope, line_load_envelope, transferred_line_load_envelope
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


TIMBER = {
    "TC13": {"fm": 13.0, "fv": 1.4, "fc": 10.0, "e": 9_000.0, "density": 5.0},
    "TC15": {"fm": 15.0, "fv": 1.6, "fc": 12.0, "e": 10_000.0, "density": 5.5},
    "GL24": {"fm": 16.5, "fv": 1.8, "fc": 14.0, "e": 11_000.0, "density": 5.5},
}


def _material(request: CalculationRequest) -> tuple[str, dict[str, float]]:
    grade = mode_text(
        request, "timber_grade", quick_default="TC13", allowed=set(TIMBER)
    )
    return grade, TIMBER[grade]


def calculate_timber_beam(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    grade_name, material = _material(request)
    b = mode_number(request, "b_mm", quick_default=100, minimum=40)
    h = mode_number(request, "h_mm", quick_default=200, minimum=60)
    span_m = mode_number(request, "span_m", quick_default=3.0, minimum=0.3, maximum=12)
    support = mode_text(
        request, "support", quick_default="simple", allowed={"simple", "cantilever"}
    )
    tributary_width = mode_number(
        request, "tributary_width_m", quick_default=1.0, minimum=0.05
    )
    area = b * h
    inertia = b * h**3 / 12
    section_modulus = b * h**2 / 6
    self_weight = area * 1e-6 * material["density"]
    upstream_lines = request.inputs.get("upstream_reaction_envelopes")
    if isinstance(upstream_lines, list) and upstream_lines:
        if request.loads:
            from .errors import CalculationInputError

            raise CalculationInputError("duplicate_member_load_source", "接收上游组合线荷载后不得再次提交普通荷载。", field="loads")
        envelope = transferred_line_load_envelope(
            upstream_lines, automatic_self_weight_kn_m=self_weight
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
    length_mm = span_m * 1000
    if support == "simple":
        moment = q_uls * span_m**2 / 8
        shear = q_uls * span_m / 2
        deflection = 5 * q_sls * length_mm**4 / (384 * material["e"] * inertia)
        limit = length_mm / 250
        reactions = {
            "left_vertical": Quantity(value=q_sls_signed * span_m / 2, unit="kN"),
            "right_vertical": Quantity(value=q_sls_signed * span_m / 2, unit="kN"),
        }
    else:
        moment = q_uls * span_m**2 / 2
        shear = q_uls * span_m
        deflection = q_sls * length_mm**4 / (8 * material["e"] * inertia)
        limit = length_mm / 200
        reactions = {
            "base_vertical": Quantity(value=q_sls_signed * span_m, unit="kN"),
            "base_moment": Quantity(
                value=q_sls_signed * span_m**2 / 2, unit="kN·m"
            ),
        }
    moment_capacity = material["fm"] * section_modulus / 1e6
    shear_capacity = material["fv"] * (2 / 3 * area) / 1000
    checks = [
        CheckResult(
            name="抗弯承载力",
            demand=Quantity(value=moment, unit="kN·m"),
            capacity=Quantity(value=moment_capacity, unit="kN·m"),
            utilization=moment / max(moment_capacity, 1e-9),
            passed=moment <= moment_capacity,
            reference="GB 50005-2017 木构件受弯（Beta映射）",
        ),
        CheckResult(
            name="抗剪承载力",
            demand=Quantity(value=shear, unit="kN"),
            capacity=Quantity(value=shear_capacity, unit="kN"),
            utilization=shear / max(shear_capacity, 1e-9),
            passed=shear <= shear_capacity,
            reference="GB 50005-2017 木构件受剪（Beta映射）",
        ),
        CheckResult(
            name="挠度",
            demand=Quantity(value=deflection, unit="mm"),
            capacity=Quantity(value=limit, unit="mm"),
            utilization=deflection / limit,
            passed=deflection <= limit,
            reference="GB 55001-2021 正常使用极限状态",
        ),
    ]
    governing = max(checks, key=lambda item: item.utilization)
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status([item.utilization for item in checks]),  # type: ignore[arg-type]
        standards=STANDARDS["timber"],
        input_summary=quantity_summary(
            {
                "timber_grade": grade_name,
                "width": (b, "mm"),
                "depth": (h, "mm"),
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
                    )
                },
            )
            for combination in envelope.combinations
        ],
        steps=[
            CalculationStep(
                name="截面抵抗矩",
                equation="W = bh²/6",
                substitution=f"b={b:.1f} mm, h={h:.1f} mm",
                result=Quantity(value=section_modulus, unit="mm³"),
                reference="矩形截面几何性质",
            )
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="timber_basic_scope",
                message="首期不覆盖连接、缺口、耐火、湿度与长期效应精细修正。",
            )
        ],
        assumptions=["矩形实木/胶合木等截面构件。", "材料设计值为首期 Beta 数据表。"],
        applicability=["简支木梁", "悬挑木梁"],
        disclaimer=DISCLAIMER,
    )


def calculate_timber_column(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    grade_name, material = _material(request)
    b = mode_number(request, "b_mm", quick_default=120, minimum=40)
    h = mode_number(request, "h_mm", quick_default=120, minimum=40)
    height_m = mode_number(request, "height_m", quick_default=2.8, minimum=0.3, maximum=12)
    k = mode_number(request, "effective_length_factor", quick_default=1.0, minimum=0.2, maximum=3)
    envelope = axial_load_envelope(request.loads)
    axial = abs(envelope.governing_uls.total.value)
    area = b * h
    i_min = min(b, h) / sqrt(12)
    slenderness = height_m * 1000 * k / i_min
    euler = pi**2 * material["e"] * min(h * b**3, b * h**3) / 12 / (height_m * 1000 * k) ** 2 / 1000
    material_capacity = material["fc"] * area / 1000
    capacity = min(euler / 1.8, material_capacity)
    checks = [
        CheckResult(
            name="轴压稳定承载力",
            demand=Quantity(value=axial, unit="kN"),
            capacity=Quantity(value=capacity, unit="kN"),
            utilization=axial / max(capacity, 1e-9),
            passed=axial <= capacity,
            reference="GB 50005-2017 轴心受压木构件（Beta筛查）",
        ),
        CheckResult(
            name="长细比",
            demand=Quantity(value=slenderness, unit="1"),
            capacity=Quantity(value=120, unit="1"),
            utilization=slenderness / 120,
            passed=slenderness <= 120,
            reference="GB 50005-2017 长细比（项目复核）",
        ),
    ]
    governing = max(checks, key=lambda item: item.utilization)
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status([item.utilization for item in checks]),  # type: ignore[arg-type]
        standards=STANDARDS["timber"],
        input_summary=quantity_summary(
            {
                "timber_grade": grade_name,
                "width": (b, "mm"),
                "depth": (h, "mm"),
                "height": (height_m, "m"),
                "effective_length_factor": (k, "1"),
            }
        ),
        combinations=envelope.combinations,
        reactions={
            "base_vertical": Quantity(
                value=envelope.governing_sls.total.value, unit="kN"
            )
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
                    "N": Quantity(value=combination.total.value, unit="kN")
                },
            )
            for combination in envelope.combinations
        ],
        steps=[
            CalculationStep(
                name="欧拉临界力",
                equation="Ncr = π²EI/(μL)²",
                substitution=f"E={material['e']:.1f} MPa, μ={k:.2f}, L={height_m:.2f} m",
                result=Quantity(value=euler, unit="kN"),
                reference="稳定理论；GB 50005-2017 Beta筛查",
            )
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="timber_stability_beta",
                message="木柱稳定采用材料强度与欧拉临界力的保守包络。",
            )
        ],
        assumptions=["矩形等截面轴压木柱。", "不覆盖连接偏心和双向弯矩。"],
        applicability=["轴心受压木柱"],
        disclaimer=DISCLAIMER,
    )
