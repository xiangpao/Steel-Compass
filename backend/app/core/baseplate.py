from __future__ import annotations

from math import hypot, isfinite, pi, sqrt

from .contact import (ContactError, solve_rectangular_contact,
                      anchor_shear_distribution, rectangular_weld_peak_line_force)
from .common import DISCLAIMER, STANDARDS, mode_number, mode_text, quantity_summary
from .errors import CalculationInputError
from .loads import axial_load_envelope
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    LoadCombinationResult,
    LoadDirection,
    Quantity,
    ReactionEnvelope,
)
from .steel import steel_design_strength


ANCHOR_STEEL = {
    "4.8": {"fu_mpa": 400.0},
    "5.8": {"fu_mpa": 500.0},
    "8.8": {"fu_mpa": 800.0},
}


def _check(
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    reference: str,
    note: str | None = None,
) -> CheckResult:
    utilization = demand / max(capacity, 1e-9)
    return CheckResult(
        name=name,
        demand=Quantity(value=max(demand, 0.0), unit=unit),
        capacity=Quantity(value=max(capacity, 0.0), unit=unit),
        utilization=max(utilization, 0.0),
        passed=demand <= capacity,
        reference=reference,
        note=note,
    )


def _incoming_envelopes(request: CalculationRequest) -> list[ReactionEnvelope]:
    raw = request.inputs.get("upstream_reaction_envelopes")
    if not isinstance(raw, list):
        return []
    try:
        return [ReactionEnvelope.model_validate(item) for item in raw]
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_upstream_reaction_envelope",
            "上游反力包格式无效，柱脚无法继续验算。",
            field="upstream_reaction_envelopes",
        ) from exc


def _component(envelope: ReactionEnvelope, name: str) -> float:
    quantity = envelope.components.get(name)  # type: ignore[arg-type]
    return quantity.value if quantity is not None else 0.0


def _complete_components(envelope: ReactionEnvelope) -> dict[str, Quantity]:
    units = {
        "N": "kN",
        "Vx": "kN",
        "Vy": "kN",
        "Mx": "kN·m",
        "My": "kN·m",
        "T": "kN·m",
    }
    return {
        name: Quantity(value=_component(envelope, name), unit=unit)
        for name, unit in units.items()
    }


def calculate_steel_baseplate_anchor(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    plate_length = mode_number(
        request, "plate_length_mm", quick_default=360, minimum=160, maximum=2000
    )
    plate_width = mode_number(
        request, "plate_width_mm", quick_default=360, minimum=160, maximum=2000
    )
    plate_thickness = mode_number(
        request, "plate_thickness_mm", quick_default=20, minimum=8, maximum=100
    )
    column_depth = mode_number(
        request, "column_depth_mm", quick_default=200, minimum=50, maximum=1500
    )
    column_width = mode_number(
        request, "column_width_mm", quick_default=200, minimum=50, maximum=1500
    )
    steel_grade = mode_text(
        request, "steel_grade", quick_default="Q355B", allowed={"Q235B", "Q355B"}
    )
    concrete_bearing = mode_number(
        request,
        "concrete_bearing_capacity_mpa",
        quick_default=10.0,
        minimum=1.0,
        maximum=60.0,
    )
    anchor_count = int(
        mode_number(request, "anchor_count", quick_default=4, minimum=4, maximum=24)
    )
    anchor_diameter = mode_number(
        request, "anchor_diameter_mm", quick_default=20, minimum=12, maximum=64
    )
    anchor_grade = mode_text(
        request, "anchor_grade", quick_default="5.8", allowed=set(ANCHOR_STEEL)
    )
    anchor_spacing = mode_number(
        request, "anchor_spacing_mm", quick_default=260, minimum=60, maximum=1800
    )
    anchor_edge = mode_number(
        request, "anchor_edge_mm", quick_default=50, minimum=20, maximum=500
    )
    anchor_head_diameter = mode_number(
        request,
        "anchor_head_diameter_mm",
        quick_default=max(2.5 * anchor_diameter, anchor_diameter + 20),
        minimum=anchor_diameter + 4,
        maximum=300,
    )
    weld_throat = mode_number(
        request, "weld_throat_mm", quick_default=6, minimum=3, maximum=40
    )

    if plate_length <= column_depth or plate_width <= column_width:
        raise CalculationInputError(
            "invalid_baseplate_geometry",
            "底板平面尺寸必须大于柱截面尺寸。",
            field="plate_length_mm",
        )
    if anchor_count % 2:
        raise CalculationInputError(
            "invalid_anchor_layout",
            "首期柱脚模型要求锚栓数量为偶数，并按两侧对称布置。",
            field="anchor_count",
        )

    incoming = _incoming_envelopes(request)
    if not incoming:
        envelope = axial_load_envelope(request.loads)
        incoming = [
            ReactionEnvelope(
                name="column_base",
                limit_state=item.limit_state,
                combination_name=item.name,
                direction=(
                    LoadDirection.UPLIFT
                    if item.total.value < 0
                    else LoadDirection.GRAVITY
                ),
                components={
                    "N": Quantity(value=item.total.value, unit="kN"),
                    "Vx": Quantity(
                        value=float(request.inputs.get("horizontal_x_kn", 0.0)),
                        unit="kN",
                    ),
                    "Vy": Quantity(
                        value=float(request.inputs.get("horizontal_y_kn", 0.0)),
                        unit="kN",
                    ),
                    "Mx": Quantity(
                        value=float(request.inputs.get("moment_x_kn_m", 0.0)),
                        unit="kN·m",
                    ),
                    "My": Quantity(
                        value=float(request.inputs.get("moment_y_kn_m", 0.0)),
                        unit="kN·m",
                    ),
                    "T": Quantity(value=0.0, unit="kN·m"),
                },
            )
            for item in envelope.combinations
        ]

    design = [item for item in incoming if item.limit_state == "ULS"] or incoming
    steel = steel_design_strength(steel_grade, plate_thickness)
    anchor_area = pi * anchor_diameter**2 / 4
    anchor_fu = ANCHOR_STEEL[anchor_grade]["fu_mpa"]
    tension_capacity_each = 0.65 * anchor_fu * anchor_area / 1000
    shear_capacity_each = 0.40 * anchor_fu * anchor_area / 1000
    projection = max(
        (plate_length - column_depth) / 2,
        (plate_width - column_width) / 2,
    )
    plate_area = plate_length * plate_width

    # Explicit positions are the actual group geometry, also for detailing and
    # concrete splitting. A legacy default must not override smaller distances.
    raw_springs = request.inputs.get("anchor_springs")
    if isinstance(raw_springs, list) and raw_springs:
        try:
            points = [(float(a["x_m"]) * 1000, float(a["y_m"]) * 1000) for a in raw_springs]
            if len(points) != anchor_count or not all(isfinite(v) for p in points for v in p):
                raise ValueError("invalid positions")
            actual_spacing = min(hypot(x-u, y-v) for i, (x,y) in enumerate(points) for u,v in points[i+1:])
            plate_edge = min(min(plate_length/2-abs(x), plate_width/2-abs(y)) for x,y in points)
            if min(actual_spacing, plate_edge) <= 0:
                raise ValueError("duplicate or out of plate positions")
        except (TypeError, ValueError, KeyError) as exc:
            raise CalculationInputError("invalid_anchor_layout", "锚栓坐标须有限、互不重复且位于底板内。") from exc
        anchor_spacing = actual_spacing
        # Explicit concrete edge distance may be smaller than the plate edge.
        # Until foundation edge coordinates are supplied, use the smaller bound.
        anchor_edge = min(anchor_edge, plate_edge)

    governing_values: dict[str, float] | None = None
    governing_utilization = -1.0
    embedment_depth = float(request.inputs.get("embedment_depth_mm", 15 * anchor_diameter))
    concrete_fcu = float(request.inputs.get("concrete_fcu_mpa", 30.0))
    concrete_member_thickness = float(request.inputs.get("anchor_member_thickness_mm", embedment_depth + 100))
    supplementary_area = float(request.inputs.get("anchor_supplementary_reinforcement_area_mm2", 0.0))
    cracked_concrete = bool(request.inputs.get("anchor_cracked_concrete", True))
    # GB 50010 / JGJ 145 混凝土受拉锥体破坏特征设计承载力 (kN)
    # N_rd_c = 11.0 * sqrt(fcu) * hef^1.5 / 1.5 / 1000
    anchor_concrete_tension_capacity = (
        11.0 * sqrt(concrete_fcu) * (embedment_depth**1.5) / 1.5 / 1000.0
    )
    # 锚栓边缘受剪破坏设计承载力 V_rd_c (kN)
    anchor_edge_mm = max(anchor_edge, 10.0)
    anchor_concrete_shear_capacity = (
        0.6 * sqrt(anchor_diameter) * ((anchor_edge_mm / anchor_diameter) ** 1.5) * sqrt(concrete_fcu) / 1.5
    )
    head_bearing_area = pi * (anchor_head_diameter**2 - anchor_diameter**2) / 4
    anchor_pullout_capacity = 8.0 * head_bearing_area * concrete_fcu / 1.5 / 1000
    edge_factor = min(1.0, anchor_edge / max(1.5 * embedment_depth, 1e-9))
    spacing_factor = min(1.0, anchor_spacing / max(3.0 * embedment_depth, 1e-9))
    thickness_factor = min(1.0, concrete_member_thickness / max(1.5 * embedment_depth, 1e-9))
    cracked_factor = 0.7 if cracked_concrete else 1.0
    supplementary_capacity_each = 0.8 * 360.0 * supplementary_area / max(anchor_count, 1) / 1000
    anchor_splitting_capacity = (
        anchor_concrete_tension_capacity
        * max(min(edge_factor, spacing_factor, thickness_factor), 0.15)
        * cracked_factor
        + supplementary_capacity_each
    )

    partial_contact = False
    contact_unresolved = False
    plate_tension_pending = False
    torsion_pending = False
    continuous_weld = request.inputs.get("continuous_perimeter_weld") is True
    contact_solutions = []
    contact_stiffness = request.inputs.get("contact_stiffness_kn_m3")
    anchor_springs = request.inputs.get("anchor_springs")
    contact_source = request.inputs.get("contact_model_source")
    explicit_contact = any(value is not None for value in (contact_stiffness, anchor_springs, contact_source))
    if explicit_contact:
        if (not isinstance(contact_source, str) or not contact_source.strip()
                or not isinstance(anchor_springs, list) or len(anchor_springs) != anchor_count
                or contact_stiffness is None):
            raise CalculationInputError("missing_contact_model_inputs",
                "接触耦合须明确支承刚度、每根锚栓坐标/轴向刚度及模型来源；锚栓数量须一致。")
        try:
            contact_stiffness = float(contact_stiffness)
            anchor_springs = [{key:float(a[key]) for key in ("x_m", "y_m", "stiffness_kn_m")} for a in anchor_springs]
        except (ValueError, TypeError, KeyError) as exc:
            raise CalculationInputError("invalid_contact_model_inputs", "接触或锚栓弹簧输入格式无效。") from exc
    demands_by_check: dict[str, tuple[float, str | None]] = {}
    for item in design:
        axial = _component(item, "N")
        if item.direction is LoadDirection.UPLIFT:
            axial = -abs(axial)
        shear = hypot(_component(item, "Vx"), _component(item, "Vy"))
        moment = hypot(_component(item, "Mx"), _component(item, "My"))
        compression = max(axial, 0.0)
        requires_partial = axial < 0 or (compression <= 0 and moment > 0) or (
            compression > 0 and 6 * abs(_component(item, "Mx")) / (compression * plate_width / 1000)
            + 6 * abs(_component(item, "My")) / (compression * plate_length / 1000) > 1
        )
        solution = None
        if not requires_partial or explicit_contact:
            try:
                # Zero actions have no unique displacement but zero demand.
                if explicit_contact or axial != 0 or moment != 0:
                    solution = solve_rectangular_contact(
                        plate_length/1000, plate_width/1000, axial,
                        _component(item, "Mx"), _component(item, "My"),
                        contact_stiffness_kn_m3=contact_stiffness,
                        anchor_springs=anchor_springs if explicit_contact else None)
            except ContactError as exc:
                if explicit_contact:
                    raise CalculationInputError("contact_equilibrium_unavailable", str(exc)) from exc
                contact_unresolved = True
        else:
            contact_unresolved = True
        if solution is not None:
            contact_solutions.append({"combination_name":item.combination_name,
                "limit_state":item.limit_state, "status":"solved",
                "contact_stiffness_kn_m3":contact_stiffness,
                "contact_model_source":contact_source or "full-contact rigid rectangle equilibrium",
                **solution.as_dict()})
            pressure = solution.qmax_kpa / 1000
            tension_each = max(solution.anchor_tensions_kn, default=0.0)
            plate_tension_pending = plate_tension_pending or tension_each > 1e-8
        else:
            pressure = tension_each = 0.0
            if requires_partial:
                contact_solutions.append({"combination_name":item.combination_name,
                    "limit_state":item.limit_state,"status":"missing_inputs",
                    "missing_inputs":["contact_stiffness_kn_m3","anchor_springs","contact_model_source"],
                    "verification_status":"unverified"})
        # Axial anchor tensions come directly from compatible rigid-plane uplift;
        # no arbitrary prying multiplier is hidden in the equilibrium solution.
        partial_contact = contact_unresolved or plate_tension_pending
        if explicit_contact:
            shear_vectors = anchor_shear_distribution(anchor_springs,
                _component(item, "Vx"), _component(item, "Vy"), _component(item, "T"))
            shear_each = max(hypot(*v) for v in shear_vectors)
            tensions = solution.anchor_tensions_kn if solution else [0.0]*anchor_count
            interaction = max(sqrt((t/tension_capacity_each)**2+(hypot(*v)/shear_capacity_each)**2)
                              for t,v in zip(tensions, shear_vectors))
            contact_solutions[-1]["anchor_shear_vectors_kn"] = shear_vectors
            contact_solutions[-1]["anchor_shear_model"] = "rigid_plate_equal_shear_stiffness_all_engaged_no_slip"
        else:
            shear_each = shear / anchor_count
            interaction = sqrt((tension_each/tension_capacity_each)**2+(shear_each/shear_capacity_each)**2)
            torsion_pending = torsion_pending or abs(_component(item, "T")) > 1e-9
        # Continuous rectangular weld-group solution gives the force per weld
        # length. Multiplying by the full length preserves the legacy kN display.
        weld_case_demand = hypot(shear, moment / 0.1)
        if continuous_weld:
            weld_case_demand = rectangular_weld_peak_line_force(
                column_depth,column_width,max(-axial,0),_component(item,"Vx"),
                _component(item,"Vy"),_component(item,"Mx"),_component(item,"My"),
                _component(item,"T")) * 2*(column_depth+column_width)/1000

        tension_concrete_ratio = tension_each / max(anchor_concrete_tension_capacity, 1e-9)
        shear_concrete_ratio = shear_each / max(anchor_concrete_shear_capacity, 1e-9)
        pullout_ratio = tension_each / max(anchor_pullout_capacity, 1e-9)
        splitting_ratio = tension_each / max(anchor_splitting_capacity, 1e-9)
        plate_moment_per_mm = pressure * projection**2 / 2
        plate_stress = 6 * plate_moment_per_mm / plate_thickness**2
        for name, demand in {
            "底板下混凝土局部承压（快算）": pressure,
            "底板悬臂弯曲": plate_stress,
            "锚栓钢材拉剪组合": interaction,
            "锚栓受拉混凝土锥体破坏验算": tension_each,
            "锚栓受剪混凝土边缘破坏验算": shear_each,
            "锚栓头部拔出破坏验算": tension_each,
            "锚栓劈裂破坏验算": tension_each,
            "柱底角焊缝承载力（快算）": weld_case_demand,
        }.items():
            if name not in demands_by_check or demand > demands_by_check[name][0]:
                demands_by_check[name] = (demand, item.combination_name)
        utilization = max(
            pressure / concrete_bearing,
            plate_stress / steel["fd"],
            interaction,
            tension_concrete_ratio,
            shear_concrete_ratio,
            pullout_ratio,
            splitting_ratio,
        )
        if utilization > governing_utilization:
            governing_utilization = utilization
            governing_values = {
                "pressure": pressure,
                "plate_stress": plate_stress,
                "tension_each": tension_each,
                "shear_each": shear_each,
                "interaction": interaction,
                "tension_concrete_ratio": tension_concrete_ratio,
                "shear_concrete_ratio": shear_concrete_ratio,
                "anchor_concrete_tension_capacity": anchor_concrete_tension_capacity,
                "anchor_concrete_shear_capacity": anchor_concrete_shear_capacity,
                "anchor_pullout_capacity": anchor_pullout_capacity,
                "anchor_splitting_capacity": anchor_splitting_capacity,
                "shear": shear,
                "moment": moment,
            }

    assert governing_values is not None
    weld_length = 2 * (column_depth + column_width)
    weld_capacity = weld_length * weld_throat * steel["fv"] / 1000
    weld_demand = hypot(governing_values["shear"], governing_values["moment"] / 0.1)
    checks = [
        _check(
            "底板下混凝土局部承压（快算）",
            governing_values["pressure"],
            concrete_bearing,
            "MPa",
            "GB 50017-2017、GB/T 50010-2010；快算映射",
            "承压设计值须由基础混凝土、灌浆和局部受压条件复核。",
        ),
        _check(
            "底板悬臂弯曲",
            governing_values["plate_stress"],
            steel["fd"],
            "MPa",
            "GB 50017-2017；柱脚底板条带模型",
        ),
        _check(
            "锚栓钢材拉剪组合",
            governing_values["interaction"],
            1.0,
            "1",
            "GB 50017-2017；显式弹性锚栓与压区平衡需求，未包含柔性底板撬力",
        ),
        _check(
            "锚栓受拉混凝土锥体破坏验算",
            governing_values["tension_each"],
            governing_values["anchor_concrete_tension_capacity"],
            "kN",
            "JGJ 145-2013 / GB 50010-2010 混凝土后锚固受拉锥体破坏",
        ),
        _check(
            "锚栓受剪混凝土边缘破坏验算",
            governing_values["shear_each"],
            governing_values["anchor_concrete_shear_capacity"],
            "kN",
            "JGJ 145-2013 / GB 50010-2010 混凝土边缘受剪破坏",
        ),
        _check(
            "锚栓头部拔出破坏验算",
            governing_values["tension_each"],
            governing_values["anchor_pullout_capacity"],
            "kN",
            "锚栓头部承压投影面积模型；方案级显式计算",
            "工程校核需由锚栓产品、头部形式和混凝土设计参数复核。",
        ),
        _check(
            "锚栓劈裂破坏验算",
            governing_values["tension_each"],
            governing_values["anchor_splitting_capacity"],
            "kN",
            "锚固区边距、间距、构件厚度及开裂状态折减模型；方案级显式计算",
            "配置附加锚固钢筋时计入其受拉贡献；当前公式仍为 unverified。",
        ),
        _check(
            "锚栓最小间距",
            3 * anchor_diameter,
            anchor_spacing,
            "mm",
            "规范构造筛查",
        ),
        _check(
            "锚栓最小边距",
            1.5 * anchor_diameter,
            anchor_edge,
            "mm",
            "规范构造筛查",
        ),
        _check(
            "柱底角焊缝承载力（快算）",
            weld_demand,
            weld_capacity,
            "kN",
            "连续周边等焊喉弹性焊缝组" if continuous_weld else "GB 50017-2017；等效合力筛查",
        ),
    ]
    for check in checks:
        if check.name in demands_by_check:
            demand, combination = demands_by_check[check.name]
            check.demand.value = demand
            check.utilization = demand / max(check.capacity.value, 1e-9)
            check.passed = demand <= check.capacity.value
            check.governing_combination = combination
    governing = max(checks, key=lambda item: item.utilization)

    outgoing = [
        ReactionEnvelope(
            name="base",
            limit_state=item.limit_state,
            combination_id=item.combination_id,
            combination_name=item.combination_name,
            sls_type=item.sls_type,
            leading_action=item.leading_action,
            direction=item.direction,
            components=_complete_components(item),  # type: ignore[arg-type]
        )
        for item in incoming
    ]
    status = "passed" if all(item.passed for item in checks) else "failed"
    warnings = [
        CalculationWarning(
            severity="info",
            code="anchor_concrete_failure_modes_checked",
            message="已显式计算锚栓混凝土锥体、受剪边缘、头部拔出和劈裂模式；结果仍须按实际锚栓产品与锚固区配筋复核。",
        )
    ]
    if partial_contact:
        unresolved_names = {"底板悬臂弯曲"}
        if not continuous_weld:
            unresolved_names.add("柱底角焊缝承载力（快算）")
        if contact_unresolved:
            unresolved_names.update({"底板下混凝土局部承压（快算）", "锚栓钢材拉剪组合",
                "锚栓受拉混凝土锥体破坏验算", "锚栓头部拔出破坏验算", "锚栓劈裂破坏验算"})
        checks = [check for check in checks if check.name not in unresolved_names]
        governing = max(checks, key=lambda item: item.utilization)
        status = "incomplete"
        warnings.append(CalculationWarning(
            severity="critical",
            code="baseplate_partial_contact_unresolved" if contact_unresolved else "baseplate_tension_plate_design_pending",
            message=("底板存在上拔或脱开；须输入支承刚度、逐根锚栓坐标/轴向刚度与来源后求解兼容平衡。"
                if contact_unresolved else "压区与各锚栓拉力已满足刚性板兼容平衡；受拉底板局部弯曲与撬力尚未完成；未声明连续周边焊缝时焊缝受拉传力亦未完成。"),
        ))
    if torsion_pending:
        status = "incomplete"
        warnings.append(CalculationWarning(
            severity="critical", code="baseplate_torsional_shear_pending",
            message="存在绕柱轴扭矩但缺逐根锚栓坐标；当前不能计算锚栓组扭转受剪。灌浆滑移亦不在模型范围。"))
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=status,  # type: ignore[arg-type]
        workflow_status="capability_unavailable" if partial_contact or torsion_pending else "ready",
        result_class=(
            "quick_estimate" if request.mode.value == "quick" else "professional_check"
        ),
        standards=[*STANDARDS["steel"], *STANDARDS["concrete"]],
        input_summary=quantity_summary(
            {
                "plate_length": (plate_length, "mm"),
                "plate_width": (plate_width, "mm"),
                "plate_thickness": (plate_thickness, "mm"),
                "column_depth": (column_depth, "mm"),
                "column_width": (column_width, "mm"),
                "steel_grade": steel_grade,
                "concrete_bearing_capacity": (concrete_bearing, "MPa"),
                "anchor_count": (anchor_count, "1"),
                "anchor_diameter": (anchor_diameter, "mm"),
                "anchor_grade": anchor_grade,
                "anchor_spacing": (anchor_spacing, "mm"),
                "anchor_edge": (anchor_edge, "mm"),
                "anchor_head_diameter": (anchor_head_diameter, "mm"),
                "anchor_member_thickness": (concrete_member_thickness, "mm"),
                "anchor_supplementary_reinforcement_area": (supplementary_area, "mm²"),
                "anchor_cracked_concrete": "是" if cracked_concrete else "否",
                "weld_throat": (weld_throat, "mm"),
                "continuous_perimeter_weld": continuous_weld,
            }
        ),
        combinations=[
            LoadCombinationResult(
                name=item.combination_name or f"柱脚组合-{index}",
                combination_id=item.combination_id,
                limit_state=item.limit_state,
                sls_type=item.sls_type,
                leading_action=item.leading_action,
                factors={},
                factored_by_kind={},
                directions_by_kind=(
                    {"upstream_reaction": [item.direction]}
                    if item.direction is not None
                    else {}
                ),
                total=Quantity(value=_component(item, "N"), unit="kN"),
                effect_components=_complete_components(item),  # type: ignore[arg-type]
            )
            for index, item in enumerate(incoming, start=1)
        ],
        reactions={},
        reaction_envelopes=outgoing,
        steps=[] if contact_unresolved else [
            CalculationStep(
                name="底板压区峰值承压",
                equation="q(x,y)=max(a+b*2x/L+c*2y/B,0); integral(q)-sum(Ti)=N",
                substitution=(
                    f"B={plate_width:.1f} mm, L={plate_length:.1f} mm"
                ),
                result=Quantity(value=governing_values["pressure"], unit="MPa"),
                reference="刚性底板快算模型",
            ),
            CalculationStep(
                name="锚栓组力矩拉力",
                equation="Ti=ki*max(-w(xi,yi),0), q=kc*max(w,0)",
                substitution="采用显式弹簧输入；缺输入时不提供需求结论",
                result=Quantity(
                    value=governing_values["tension_each"], unit="kN/根"
                ),
                reference="弹性锚栓组快算模型",
            ),
        ],
        checks=checks,
        contact_solutions=contact_solutions,
        governing_check=governing.name,
        warnings=warnings,
        assumptions=[
            "柱脚底板按刚性板与悬臂条带模型筛查。",
            "接触模型为刚性矩形板、均匀压缩单向线性支承与无预拉/无间隙拉力锚栓；柔性板撬力另需核验。",
            "上游反力包为已组合效应，本节点不再次施加荷载分项系数。",
        ],
        applicability=[
            "平面刚架矩形钢柱脚的方案快算",
            "底板和锚栓规则对称布置",
        ],
        disclaimer=DISCLAIMER
        + " 柱脚结果未覆盖锚固混凝土全部破坏模式，不可作为施工详图。",
    )
