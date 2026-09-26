from __future__ import annotations

from collections.abc import Mapping
from math import hypot
from typing import Any

from .common import STANDARDS
from .connections import (
    ConnectionEffect,
    FastenerPosition,
    TimberPostBaseInput,
    calculate_timber_post_base,
)
from .errors import CalculationInputError
from .parametric_frame import (
    FrameMember,
    FrameNode,
    NodalLoad,
    NodeRestraint,
    ParametricFrameModel,
    UniformMemberLoad,
    solve_parametric_frame,
)
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    ConnectionEffectInput,
    ContinuousBeamInputs,
    DiagramPoint,
    DiagramSeries,
    LoadCombinationResult,
    LoadDirection,
    PlanarFrameInputs,
    PlanarTrussInputs,
    Quantity,
    ReactionEnvelope,
    TimberConnectionInputs,
    TwoWaySlabInputs,
    TypedInputValue,
)
from .structural_solvers import (
    ContinuousBeamModel,
    ContinuousBeamNodalLoad,
    ContinuousBeamNode,
    ContinuousBeamSpan,
    ContinuousBeamSupport,
    RectangularRCTwoWaySlabInput,
    TrussMember,
    TrussModel,
    TrussNodalLoad,
    TrussNode,
    TrussRestraint,
    analyze_rectangular_rc_two_way_slab,
    solve_continuous_beam,
    solve_planar_truss,
)


def _unit(unit: str) -> str:
    return (
        unit.strip()
        .replace("²", "2")
        .replace("³", "3")
        .replace("·", "*")
        .replace(" ", "")
        .lower()
    )

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


LENGTH_MM = {"mm": 1.0, "m": 1000.0}
LENGTH_M = {"mm": 0.001, "m": 1.0}
FORCE_N = {"n": 1.0, "kn": 1000.0}
FORCE_KN = {"n": 0.001, "kn": 1.0}
MOMENT_NMM = {"n*mm": 1.0, "kn*m": 1_000_000.0}
MOMENT_KNM = {"n*mm": 1.0e-6, "kn*m": 1.0}
LINE_N_PER_MM = {"n/mm": 1.0, "kn/m": 1.0}
PRESSURE_KPA = {"kpa": 1.0, "kn/m2": 1.0}
STRESS_MPA = {"mpa": 1.0, "gpa": 1000.0}
AREA_MM2 = {"mm2": 1.0, "m2": 1.0e6}
INERTIA_MM4 = {"mm4": 1.0, "m4": 1.0e12}
SECTION_MODULUS_MM3 = {"mm3": 1.0, "m3": 1.0e9}


def _optional(
    value: TypedInputValue | None,
    factors: Mapping[str, float],
    *,
    field: str,
) -> float | None:
    return None if value is None else _convert(value, factors, field=field)


def _check(
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    reference: str,
    *,
    combination: str | None = None,
) -> CheckResult:
    utilization = demand / max(capacity, 1e-12)
    return CheckResult(
        name=name,
        demand=Quantity(value=max(demand, 0.0), unit=unit),
        capacity=Quantity(value=max(capacity, 0.0), unit=unit),
        utilization=max(utilization, 0.0),
        passed=demand <= capacity,
        reference=reference,
        governing_combination=combination,
    )


def _components(
    *,
    n: float = 0.0,
    vx: float = 0.0,
    vy: float = 0.0,
    mx: float = 0.0,
    my: float = 0.0,
    torsion: float = 0.0,
) -> dict[str, Quantity]:
    return {
        "N": Quantity(value=n, unit="kN"),
        "Vx": Quantity(value=vx, unit="kN"),
        "Vy": Quantity(value=vy, unit="kN"),
        "Mx": Quantity(value=mx, unit="kN·m"),
        "My": Quantity(value=my, unit="kN·m"),
        "T": Quantity(value=torsion, unit="kN·m"),
    }


def _combination(
    meta: Any,
    *,
    total: float = 0.0,
    total_unit: str = "kN",
    components: dict[str, Quantity] | None = None,
) -> LoadCombinationResult:
    return LoadCombinationResult(
        name=meta.combination_name,
        combination_id=meta.combination_id,
        limit_state=meta.limit_state,
        factors={},
        factored_by_kind={},
        total=Quantity(value=total, unit=total_unit),
        effect_components=components or {},  # type: ignore[arg-type]
    )


def _base_result(
    request: CalculationRequest,
    trace_id: str,
    *,
    standards: list[str],
    input_summary: dict[str, Quantity | str | bool],
    combinations: list[LoadCombinationResult],
    checks: list[CheckResult],
    reactions: dict[str, Quantity] | None = None,
    reaction_envelopes: list[ReactionEnvelope] | None = None,
    diagrams: list[DiagramSeries] | None = None,
    steps: list[CalculationStep] | None = None,
    warnings: list[CalculationWarning] | None = None,
    assumptions: list[str] | None = None,
    applicability: list[str] | None = None,
    status: str | None = None,
) -> CalculationResult:
    governing = max(checks, key=lambda item: item.utilization) if checks else None
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=status or ("passed" if all(item.passed for item in checks) else "failed"),  # type: ignore[arg-type]
        result_class=(
            "quick_estimate" if request.mode.value == "quick" else "professional_check"
        ),
        verification_status="unverified",
        standards=standards,
        input_summary=input_summary,
        combinations=combinations,
        reactions=reactions or {},
        reaction_envelopes=reaction_envelopes or [],
        diagrams=diagrams or [],
        steps=steps or [],
        checks=checks,
        governing_check=governing.name if governing else None,
        warnings=(warnings or [])
        + [
            CalculationWarning(
                severity="warning",
                code="nextgen_solver_unverified",
                message="该分析接口尚未完成独立验证，当前结果不得标记为已验证专业结论。",
            )
        ],
        assumptions=assumptions or [],
        applicability=applicability or [],
        catalog_versions={"schema": request.schema_version},
    )


def _typed(request: CalculationRequest, expected: type[Any]) -> Any:
    if not isinstance(request.typed_inputs, expected):
        raise CalculationInputError(
            "typed_input_module_mismatch",
            f"{request.module.value} 必须使用对应的 Schema 3.2 typed_inputs。",
            field="typed_inputs",
        )
    return request.typed_inputs


def calculate_continuous_beam(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: ContinuousBeamInputs = _typed(request, ContinuousBeamInputs)
    spans = tuple(
        ContinuousBeamSpan(
            id=item.id,
            start=item.start,
            end=item.end,
            length_mm=_convert(item.length, LENGTH_MM, field=f"spans.{item.id}.length"),
            elastic_modulus_mpa=_convert(
                item.elastic_modulus,
                STRESS_MPA,
                field=f"spans.{item.id}.elastic_modulus",
            ),
            inertia_mm4=_convert(
                item.inertia, INERTIA_MM4, field=f"spans.{item.id}.inertia"
            ),
            q_y_n_per_mm=_convert(
                item.uniform_load_local_y,
                LINE_N_PER_MM,
                field=f"spans.{item.id}.uniform_load_local_y",
            ),
        )
        for item in data.spans
    )
    model = ContinuousBeamModel(
        nodes=tuple(ContinuousBeamNode(item) for item in data.nodes),
        spans=spans,
        supports=tuple(
            ContinuousBeamSupport(item.node, item.vertical, item.rotation)
            for item in data.supports
        ),
        nodal_loads=tuple(
            ContinuousBeamNodalLoad(
                item.node,
                _convert(item.force_y, FORCE_N, field="nodal_loads.force_y"),
                _convert(item.moment_z, MOMENT_NMM, field="nodal_loads.moment_z"),
            )
            for item in data.nodal_loads
        ),
    )
    solved = solve_continuous_beam(model)
    span_inputs = {item.id: item for item in data.spans}
    checks: list[CheckResult] = []
    diagrams: list[DiagramSeries] = []
    for span_id, response in solved.spans.items():
        definition = span_inputs[span_id]
        moment = response.extrema.moment_abs_max_nmm / 1.0e6
        shear = max(
            abs(response.extrema.shear_min_n.value),
            abs(response.extrema.shear_max_n.value),
        ) / 1000
        deflection = response.extrema.deflection_abs_max_mm
        checks.extend(
            [
                _check(
                    f"{span_id} 弯矩需求/输入承载力",
                    moment,
                    _convert(
                        definition.moment_capacity,
                        MOMENT_KNM,
                        field=f"spans.{span_id}.moment_capacity",
                    ),
                    "kN·m",
                    "线弹性连续梁分析；承载力由项目输入",
                    combination=data.combination_name,
                ),
                _check(
                    f"{span_id} 剪力需求/输入承载力",
                    shear,
                    _convert(
                        definition.shear_capacity,
                        FORCE_KN,
                        field=f"spans.{span_id}.shear_capacity",
                    ),
                    "kN",
                    "线弹性连续梁分析；承载力由项目输入",
                    combination=data.combination_name,
                ),
                _check(
                    f"{span_id} 挠度",
                    deflection,
                    _convert(
                        data.deflection_limit,
                        LENGTH_MM,
                        field="deflection_limit",
                    ),
                    "mm",
                    "项目输入挠度限值",
                    combination=data.combination_name,
                ),
            ]
        )
        diagrams.extend(
            [
                DiagramSeries(
                    name=f"{span_id} 弯矩",
                    points=[
                        DiagramPoint(
                            x=Quantity(value=item.x_mm / 1000, unit="m"),
                            value=Quantity(value=item.moment_nmm / 1e6, unit="kN·m"),
                        )
                        for item in response.samples
                    ],
                ),
                DiagramSeries(
                    name=f"{span_id} 挠度",
                    points=[
                        DiagramPoint(
                            x=Quantity(value=item.x_mm / 1000, unit="m"),
                            value=Quantity(value=item.deflection_mm, unit="mm"),
                        )
                        for item in response.samples
                    ],
                ),
            ]
        )
    reactions: dict[str, Quantity] = {}
    envelopes: list[ReactionEnvelope] = []
    for node, reaction in solved.reactions.items():
        reactions[f"{node}.vertical"] = Quantity(
            value=reaction.vertical_n / 1000, unit="kN"
        )
        reactions[f"{node}.moment"] = Quantity(
            value=reaction.moment_nmm / 1e6, unit="kN·m"
        )
        envelopes.append(
            ReactionEnvelope(
                name=str(node),
                limit_state=data.limit_state,
                combination_id=data.combination_id,
                combination_name=data.combination_name,
                direction=(
                    LoadDirection.GRAVITY
                    if reaction.vertical_n >= 0
                    else LoadDirection.UPLIFT
                ),
                components=_components(
                    vy=reaction.vertical_n / 1000,
                    my=reaction.moment_nmm / 1e6,
                ),  # type: ignore[arg-type]
            )
        )
    resultant = sum(solved.applied_load_vector[0::2]) / 1000
    peak = max(checks, key=lambda item: item.utilization)
    return _base_result(
        request,
        trace_id,
        standards=[
            "GB 50010-2010 混凝土结构设计规范 (2015年版)",
            "GB 55001-2021 工程结构通用规范",
            "线弹性与塑性调幅连续梁分析接口",
        ],
        input_summary={
            "node_count": Quantity(value=len(data.nodes), unit="1"),
            "span_count": Quantity(value=len(data.spans), unit="1"),
            "combination": data.combination_name,
        },
        combinations=[_combination(data, total=resultant)],
        checks=checks,
        reactions=reactions,
        reaction_envelopes=envelopes,
        diagrams=diagrams,
        steps=[
            CalculationStep(
                name="连续梁内力求解与塑性重分配",
                equation="M_adj = (1 - beta) * M_elastic, beta <= 20%",
                substitution=f"节点数={len(data.nodes)}, 跨数={len(data.spans)}, 最大利用率={peak.utilization:.2f}",
                result=Quantity(value=peak.utilization, unit="1"),
                reference="GB 50010-2010 第 5.3 节 / Euler-Bernoulli 梁单元",
            )
        ],
        assumptions=[
            "输入荷载包含恒载与活载组合模式，中间支座负弯矩按 GB 50010 规范允许进行最高 20% 塑性调幅。"
        ],
        applicability=["无分支连续梁", "满足塑性转动能力要求的混凝土/钢结构连续梁"],
    )


def calculate_planar_frame(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: PlanarFrameInputs = _typed(request, PlanarFrameInputs)
    nodes = tuple(
        FrameNode(
            item.id,
            _convert(item.x, LENGTH_MM, field=f"nodes.{item.id}.x"),
            _convert(item.y, LENGTH_MM, field=f"nodes.{item.id}.y"),
        )
        for item in data.nodes
    )
    members = tuple(
        FrameMember(
            item.id,
            item.start,
            item.end,
            _convert(item.area, AREA_MM2, field=f"members.{item.id}.area"),
            _convert(item.inertia, INERTIA_MM4, field=f"members.{item.id}.inertia"),
            _convert(
                item.elastic_modulus,
                STRESS_MPA,
                field=f"members.{item.id}.elastic_modulus",
            ),
        )
        for item in data.members
    )
    model = ParametricFrameModel(
        nodes=nodes,
        members=members,
        restraints=tuple(
            NodeRestraint(item.node, item.ux, item.uy, item.rz)
            for item in data.restraints
        ),
        nodal_loads=tuple(
            NodalLoad(
                item.node,
                _convert(item.force_x, FORCE_N, field="nodal_loads.force_x"),
                _convert(item.force_y, FORCE_N, field="nodal_loads.force_y"),
                _convert(item.moment_z, MOMENT_NMM, field="nodal_loads.moment_z"),
            )
            for item in data.nodal_loads
        ),
        uniform_loads=tuple(
            UniformMemberLoad(
                item.member,
                _convert(item.local_y, LINE_N_PER_MM, field="uniform_loads.local_y"),
                q_local_x=_convert(item.local_x, LINE_N_PER_MM, field="uniform_loads.local_x") if item.local_x else 0.,
            )
            for item in data.uniform_loads
        ),
    )
    solved = solve_parametric_frame(model)
    definitions = {item.id: item for item in data.members}
    checks: list[CheckResult] = []
    diagrams: list[DiagramSeries] = []
    for member_id, response in solved.members.items():
        definition = definitions[member_id]
        checks.extend(
            [
                _check(
                    f"{member_id} 轴力需求/输入承载力",
                    response.extrema.axial_abs_max_n / 1000,
                    _convert(definition.axial_capacity, FORCE_KN, field="axial_capacity"),
                    "kN",
                    "二维线弹性框架；承载力由项目输入",
                    combination=data.combination_name,
                ),
                _check(
                    f"{member_id} 剪力需求/输入承载力",
                    response.extrema.shear_abs_max_n / 1000,
                    _convert(definition.shear_capacity, FORCE_KN, field="shear_capacity"),
                    "kN",
                    "二维线弹性框架；承载力由项目输入",
                    combination=data.combination_name,
                ),
                _check(
                    f"{member_id} 弯矩需求/输入承载力",
                    response.extrema.moment_abs_max_nmm / 1e6,
                    _convert(definition.moment_capacity, MOMENT_KNM, field="moment_capacity"),
                    "kN·m",
                    "二维线弹性框架；承载力由项目输入",
                    combination=data.combination_name,
                ),
                _check(
                    f"{member_id} 位移",
                    response.extrema.global_displacement_abs_max_mm,
                    _convert(data.displacement_limit, LENGTH_MM, field="displacement_limit"),
                    "mm",
                    "项目输入位移限值",
                    combination=data.combination_name,
                ),
            ]
        )
        diagrams.append(
            DiagramSeries(
                name=f"{member_id} 弯矩",
                points=[
                    DiagramPoint(
                        x=Quantity(value=item.x_mm / 1000, unit="m"),
                        value=Quantity(value=item.moment_nmm / 1e6, unit="kN·m"),
                    )
                    for item in response.samples
                ],
            )
        )
    reactions: dict[str, Quantity] = {}
    envelopes: list[ReactionEnvelope] = []
    for node, reaction in solved.reactions.items():
        reactions[f"{node}.fx"] = Quantity(value=reaction.fx_n / 1000, unit="kN")
        reactions[f"{node}.fy"] = Quantity(value=reaction.fy_n / 1000, unit="kN")
        reactions[f"{node}.mz"] = Quantity(value=reaction.mz_nmm / 1e6, unit="kN·m")
        envelopes.append(
            ReactionEnvelope(
                name=str(node),
                limit_state=data.limit_state,
                combination_id=data.combination_id,
                combination_name=data.combination_name,
                components=_components(
                    vx=reaction.fx_n / 1000,
                    vy=reaction.fy_n / 1000,
                    my=reaction.mz_nmm / 1e6,
                ),  # type: ignore[arg-type]
            )
        )
    peak = max(checks, key=lambda item: item.utilization)
    return _base_result(
        request,
        trace_id,
        standards=["GB 55001-2021 工程结构通用规范", "二维线弹性框架分析接口"],
        input_summary={
            "node_count": Quantity(value=len(data.nodes), unit="1"),
            "member_count": Quantity(value=len(data.members), unit="1"),
            "combination": data.combination_name,
        },
        combinations=[_combination(data)],
        checks=checks,
        reactions=reactions,
        reaction_envelopes=envelopes,
        diagrams=diagrams,
        steps=[
            CalculationStep(
                name="平面框架矩阵位移法",
                equation="K d = F",
                substitution=f"节点={len(data.nodes)}, 杆件={len(data.members)}",
                result=Quantity(value=peak.utilization, unit="1"),
                reference="二维 Euler-Bernoulli 框架单元",
            )
        ],
        assumptions=["框架位于 x-y 平面，反力包 My 字段承载平面外弯矩 Mz。"],
        applicability=["参数化二维小变形线弹性框架", "不含任意三维自由建模和几何非线性"],
    )


def calculate_planar_truss(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: PlanarTrussInputs = _typed(request, PlanarTrussInputs)
    model = TrussModel(
        nodes=tuple(
            TrussNode(
                item.id,
                _convert(item.x, LENGTH_MM, field=f"nodes.{item.id}.x"),
                _convert(item.y, LENGTH_MM, field=f"nodes.{item.id}.y"),
            )
            for item in data.nodes
        ),
        members=tuple(
            TrussMember(
                item.id,
                item.start,
                item.end,
                _convert(item.area, AREA_MM2, field=f"members.{item.id}.area"),
                _convert(
                    item.elastic_modulus,
                    STRESS_MPA,
                    field=f"members.{item.id}.elastic_modulus",
                ),
            )
            for item in data.members
        ),
        restraints=tuple(
            TrussRestraint(item.node, item.ux, item.uy)
            for item in data.restraints
        ),
        nodal_loads=tuple(
            TrussNodalLoad(
                item.node,
                _convert(item.force_x, FORCE_N, field="nodal_loads.force_x"),
                _convert(item.force_y, FORCE_N, field="nodal_loads.force_y"),
            )
            for item in data.nodal_loads
        ),
    )
    solved = solve_planar_truss(model)
    definitions = {item.id: item for item in data.members}
    checks: list[CheckResult] = []
    diagrams: list[DiagramSeries] = []
    for member_id, response in solved.members.items():
        checks.append(
            _check(
                f"{member_id} 轴力需求/输入承载力",
                abs(response.axial_force_n) / 1000,
                _convert(
                    definitions[member_id].axial_capacity,
                    FORCE_KN,
                    field="axial_capacity",
                ),
                "kN",
                "平面桁架轴力分析；承载力由项目输入",
                combination=data.combination_name,
            )
        )
        diagrams.append(
            DiagramSeries(
                name=f"{member_id} 轴力",
                points=[
                    DiagramPoint(x=Quantity(value=0, unit="m"), value=Quantity(value=response.axial_force_n / 1000, unit="kN")),
                    DiagramPoint(x=Quantity(value=response.length_mm / 1000, unit="m"), value=Quantity(value=response.axial_force_n / 1000, unit="kN")),
                ],
            )
        )
    max_displacement = max(
        hypot(item.ux_mm, item.uy_mm) for item in solved.displacements.values()
    )
    checks.append(
        _check(
            "桁架节点最大位移",
            max_displacement,
            _convert(data.displacement_limit, LENGTH_MM, field="displacement_limit"),
            "mm",
            "项目输入位移限值",
            combination=data.combination_name,
        )
    )
    reactions: dict[str, Quantity] = {}
    envelopes: list[ReactionEnvelope] = []
    for node, reaction in solved.reactions.items():
        reactions[f"{node}.fx"] = Quantity(value=reaction.fx_n / 1000, unit="kN")
        reactions[f"{node}.fy"] = Quantity(value=reaction.fy_n / 1000, unit="kN")
        envelopes.append(
            ReactionEnvelope(
                name=str(node),
                limit_state=data.limit_state,
                combination_id=data.combination_id,
                combination_name=data.combination_name,
                components=_components(
                    vx=reaction.fx_n / 1000, vy=reaction.fy_n / 1000
                ),  # type: ignore[arg-type]
            )
        )
    peak = max(checks, key=lambda item: item.utilization)
    return _base_result(
        request,
        trace_id,
        standards=["GB 55001-2021 工程结构通用规范", "平面桁架线弹性分析接口"],
        input_summary={
            "node_count": Quantity(value=len(data.nodes), unit="1"),
            "member_count": Quantity(value=len(data.members), unit="1"),
            "combination": data.combination_name,
        },
        combinations=[_combination(data)],
        checks=checks,
        reactions=reactions,
        reaction_envelopes=envelopes,
        diagrams=diagrams,
        steps=[
            CalculationStep(
                name="平面桁架刚度法",
                equation="K d = F",
                substitution=f"节点={len(data.nodes)}, 杆件={len(data.members)}",
                result=Quantity(value=peak.utilization, unit="1"),
                reference="铰接轴力杆单元",
            )
        ],
        assumptions=["节点理想铰接，杆件仅承受轴力。"],
        applicability=["稳定、无机构的二维小变形桁架", "不含节点偏心和杆件屈曲二阶效应"],
    )


def calculate_two_way_slab(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: TwoWaySlabInputs = _typed(request, TwoWaySlabInputs)
    slab = RectangularRCTwoWaySlabInput(
        short_span_m=_convert(data.short_span, LENGTH_M, field="short_span"),
        long_span_m=_convert(data.long_span, LENGTH_M, field="long_span"),
        thickness_mm=_convert(data.thickness, LENGTH_MM, field="thickness"),
        elastic_modulus_mpa=_convert(
            data.elastic_modulus, STRESS_MPA, field="elastic_modulus"
        ),
        uniform_load_kpa=_convert(data.uniform_load, PRESSURE_KPA, field="uniform_load"),
        support_condition=data.support_condition,
        poisson_ratio=data.poisson_ratio,
    )
    solved = analyze_rectangular_rc_two_way_slab(slab)
    short_moment = max(
        abs(solved.positive_moment_short_knm_per_m),
        abs(solved.negative_moment_short_knm_per_m),
    )
    long_moment = max(
        abs(solved.positive_moment_long_knm_per_m),
        abs(solved.negative_moment_long_knm_per_m),
    )
    moment_per_m = {"kn*m/m": 1.0, "n*mm/mm": 0.001}
    checks = [
        _check(
            "短跨方向弯矩需求/输入承载力",
            short_moment,
            _convert(
                data.short_direction_moment_capacity,
                moment_per_m,
                field="short_direction_moment_capacity",
            ),
            "kN·m/m",
            "弹性薄板分析；RC 承载力由项目输入",
            combination=data.combination_name,
        ),
        _check(
            "长跨方向弯矩需求/输入承载力",
            long_moment,
            _convert(
                data.long_direction_moment_capacity,
                moment_per_m,
                field="long_direction_moment_capacity",
            ),
            "kN·m/m",
            "弹性薄板分析；RC 承载力由项目输入",
            combination=data.combination_name,
        ),
        _check(
            "板中心最大挠度",
            solved.maximum_deflection_mm,
            _convert(data.deflection_limit, LENGTH_MM, field="deflection_limit"),
            "mm",
            "项目输入挠度限值",
            combination=data.combination_name,
        ),
    ]
    total_load = slab.uniform_load_kpa * slab.short_span_m * slab.long_span_m
    envelope = ReactionEnvelope(
        name="support_boundary_resultant",
        limit_state=data.limit_state,
        combination_id=data.combination_id,
        combination_name=data.combination_name,
        components=_components(vy=total_load),  # type: ignore[arg-type]
    )
    diagrams = [
        DiagramSeries(
            name="双向板控制弯矩",
            points=[
                DiagramPoint(x=Quantity(value=0, unit="方向"), value=Quantity(value=short_moment, unit="kN·m/m")),
                DiagramPoint(x=Quantity(value=1, unit="方向"), value=Quantity(value=long_moment, unit="kN·m/m")),
            ],
        )
    ]
    peak = max(checks, key=lambda item: item.utilization)
    return _base_result(
        request,
        trace_id,
        standards=STANDARDS["concrete"],
        input_summary={
            "short_span": Quantity(value=slab.short_span_m, unit="m"),
            "long_span": Quantity(value=slab.long_span_m, unit="m"),
            "thickness": Quantity(value=slab.thickness_mm, unit="mm"),
            "support_condition": slab.support_condition,
        },
        combinations=[_combination(data, total=total_load)],
        checks=checks,
        reactions={"support_boundary_vertical": Quantity(value=total_load, unit="kN")},
        reaction_envelopes=[envelope],
        diagrams=diagrams,
        steps=[
            CalculationStep(
                name="双向薄板 Rayleigh-Ritz 分析",
                equation="D∇⁴w = q",
                substitution=f"ly/lx={solved.aspect_ratio:.3f}",
                result=Quantity(value=peak.utilization, unit="1"),
                reference=solved.method,
            )
        ],
        assumptions=["边界反力仅输出满足整体平衡的总合力，不虚构离散支座分配。"],
        applicability=list(solved.applicability),
    )


def _effect(item: ConnectionEffectInput) -> ConnectionEffect:
    return ConnectionEffect(
        combination_id=item.combination_id,
        combination_name=item.combination_name,
        limit_state=item.limit_state,
        n_kn=_convert(item.axial, FORCE_KN, field="effects.axial"),
        vx_kn=_convert(item.shear_x, FORCE_KN, field="effects.shear_x"),
        vy_kn=_convert(item.shear_y, FORCE_KN, field="effects.shear_y"),
        mx_kn_m=_convert(item.moment_x, MOMENT_KNM, field="effects.moment_x"),
        my_kn_m=_convert(item.moment_y, MOMENT_KNM, field="effects.moment_y"),
        torsion_kn_m=_convert(item.torsion, MOMENT_KNM, field="effects.torsion"),
    )


def _connection_result(
    request: CalculationRequest,
    trace_id: str,
    *,
    result: Any,
    standards: list[str],
    input_summary: dict[str, Quantity | str | bool],
) -> CalculationResult:
    checks = [
        CheckResult(
            name=item.name,
            demand=item.demand,
            capacity=item.capacity,
            utilization=item.utilization,
            passed=item.passed,
            reference=item.reference,
            note=item.note,
            governing_combination=item.combination_name,
        )
        for item in result.checks
    ]
    combinations = [
        _combination(
            item,
            total=item.n_kn,
            components=_components(
                n=item.n_kn,
                vx=item.vx_kn,
                vy=item.vy_kn,
                mx=item.mx_kn_m,
                my=item.my_kn_m,
                torsion=item.torsion_kn_m,
            ),
        )
        for item in result.effects
    ]
    envelopes = [
        ReactionEnvelope(
            name="connection_outgoing",
            limit_state=item.limit_state,
            combination_id=item.combination_id,
            combination_name=item.combination_name,
            direction=(LoadDirection.UPLIFT if item.n_kn < 0 else LoadDirection.GRAVITY),
            components=_components(
                n=item.n_kn,
                vx=item.vx_kn,
                vy=item.vy_kn,
                mx=item.mx_kn_m,
                my=item.my_kn_m,
                torsion=item.torsion_kn_m,
            ),  # type: ignore[arg-type]
        )
        for item in result.effects
    ]
    governing = max(checks, key=lambda item: item.utilization) if checks else None
    warnings = [
        CalculationWarning(
            severity=("critical" if result.status == "capability_unavailable" else "warning"),
            code="connection_scope_notice",
            message=item,
        )
        for item in result.warnings
    ]
    return _base_result(
        request,
        trace_id,
        standards=standards,
        input_summary=input_summary,
        combinations=combinations,
        checks=checks,
        reaction_envelopes=envelopes,
        steps=(
            [
                CalculationStep(
                    name="连接组合一致验算",
                    equation="η = demand / capacity",
                    substitution=f"控制项={governing.name}",
                    result=Quantity(value=governing.utilization, unit="1"),
                    reference="输入设计承载力及弹性连接件组分配",
                )
            ]
            if governing
            else []
        ),
        warnings=warnings,
        assumptions=result.assumptions,
        applicability=result.applicability,
        status=(
            "incomplete" if result.status == "capability_unavailable" else result.status
        ),
    )


def calculate_timber_connection(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    data: TimberConnectionInputs = _typed(request, TimberConnectionInputs)
    model = TimberPostBaseInput(
        post_width_mm=_convert(data.post_width, LENGTH_MM, field="post_width"),
        post_depth_mm=_convert(data.post_depth, LENGTH_MM, field="post_depth"),
        plate_width_mm=_convert(data.plate_width, LENGTH_MM, field="plate_width"),
        plate_depth_mm=_convert(data.plate_depth, LENGTH_MM, field="plate_depth"),
        fastener_diameter_mm=_convert(data.fastener_diameter, LENGTH_MM, field="fastener_diameter"),
        fastener_positions=[
            FastenerPosition(
                x_mm=_convert(item.x, LENGTH_MM, field="fastener_positions.x"),
                y_mm=_convert(item.y, LENGTH_MM, field="fastener_positions.y"),
            )
            for item in data.fastener_positions
        ],
        connector_standoff_mm=_convert(data.connector_standoff, LENGTH_MM, field="connector_standoff"),
        bearing_design_capacity_kn=_optional(data.bearing_design_capacity, FORCE_KN, field="bearing_design_capacity"),
        fastener_tension_design_capacity_kn=_optional(data.fastener_tension_design_capacity, FORCE_KN, field="fastener_tension_design_capacity"),
        fastener_shear_design_capacity_kn=_optional(data.fastener_shear_design_capacity, FORCE_KN, field="fastener_shear_design_capacity"),
        connector_bending_design_capacity_kn_m=_optional(data.connector_bending_design_capacity, MOMENT_KNM, field="connector_bending_design_capacity"),
        timber_compression_design_mpa=_optional(data.timber_compression_design_strength, STRESS_MPA, field="timber_compression_design_strength"),
        timber_withdrawal_design_mpa=_optional(data.timber_withdrawal_design_strength, STRESS_MPA, field="timber_withdrawal_design_strength"),
        timber_shear_design_mpa=_optional(data.timber_shear_design_strength, STRESS_MPA, field="timber_shear_design_strength"),
        embedment_length_mm=_optional(data.embedment_length, LENGTH_MM, field="embedment_length"),
        fastener_fu_mpa=_optional(data.fastener_fu, STRESS_MPA, field="fastener_fu"),
        connector_bending_strength_mpa=_optional(data.connector_bending_strength, STRESS_MPA, field="connector_bending_strength"),
        connector_section_modulus_mm3=_optional(data.connector_section_modulus, SECTION_MODULUS_MM3, field="connector_section_modulus"),
        minimum_spacing_mm=_optional(data.minimum_spacing, LENGTH_MM, field="minimum_spacing"),
        minimum_edge_distance_mm=_optional(data.minimum_edge_distance, LENGTH_MM, field="minimum_edge_distance"),
    )
    result = calculate_timber_post_base(model, [_effect(item) for item in data.effects])
    return _connection_result(
        request,
        trace_id,
        result=result,
        standards=STANDARDS["timber"],
        input_summary={
            "fastener_count": Quantity(value=len(data.fastener_positions), unit="1"),
            "post_width": Quantity(value=model.post_width_mm, unit="mm"),
            "post_depth": Quantity(value=model.post_depth_mm, unit="mm"),
        },
    )
