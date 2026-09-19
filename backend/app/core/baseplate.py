from __future__ import annotations

from math import hypot, pi, sqrt

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
    lever_arm = max(anchor_spacing / 1000, 1e-6)

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
    demands_by_check: dict[str, tuple[float, str | None]] = {}
    for item in design:
        axial = _component(item, "N")
        if item.direction is LoadDirection.UPLIFT:
            axial = -abs(axial)
        shear = hypot(_component(item, "Vx"), _component(item, "Vy"))
        moment = hypot(_component(item, "Mx"), _component(item, "My"))
        compression = max(axial, 0.0)
        if (compression <= 0 and moment > 0) or (
            compression > 0 and 6 * abs(_component(item, "Mx")) / (compression * plate_width / 1000)
            + 6 * abs(_component(item, "My")) / (compression * plate_length / 1000) > 1
        ):
            partial_contact = True
        uplift = max(-axial, 0.0)
        # Full-contact rigid plate: maximum corner pressure, including both axes.
        # Using this maximum over the whole projection is conservative for plate bending.
        pressure = (compression * 1000 / plate_area
                    + 6 * abs(_component(item, "Mx")) * 1e6 / (plate_length * plate_width**2)
                    + 6 * abs(_component(item, "My")) * 1e6 / (plate_width * plate_length**2))
        moment_tension = moment / lever_arm
        raw_anchor_tension = uplift + max(moment_tension - compression / 2, 0.0)
        # 计入弹性底板撬力放大系数 1.25
        total_anchor_tension = raw_anchor_tension * 1.25
        tension_each = total_anchor_tension / max(anchor_count / 2, 1)
        shear_each = shear / anchor_count
        interaction = sqrt(
            (tension_each / max(tension_capacity_each, 1e-9)) ** 2
            + (shear_each / max(shear_capacity_each, 1e-9)) ** 2
        )
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
            "柱底角焊缝承载力（快算）": hypot(shear, moment / 0.1),
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
            "GB 50017-2017；已按 1.25 系数引入底板撬力放大",
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
            "GB 50017-2017；等效合力筛查",
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
        # Average N/A and a cantilever strip are not a partial-contact solution.
        # Keep anchor screening, but do not publish fictitious zero-pressure passes.
        checks = checks[2:]
        governing = max(checks, key=lambda item: item.utilization)
        status = "incomplete"
        warnings.append(CalculationWarning(
            severity="critical", code="baseplate_partial_contact_unresolved",
            message="底板存在脱开或纯弯矩；平均承压和底板条带模型不适用，承压区与锚栓耦合尚未计算。",
        ))
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=status,  # type: ignore[arg-type]
        workflow_status="capability_unavailable" if partial_contact else "ready",
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
        steps=[
            CalculationStep(
                name="底板平均承压",
                equation="q = N_c / (B L)",
                substitution=(
                    f"B={plate_width:.1f} mm, L={plate_length:.1f} mm"
                ),
                result=Quantity(value=governing_values["pressure"], unit="MPa"),
                reference="刚性底板快算模型",
            ),
            CalculationStep(
                name="锚栓组力矩拉力",
                equation="T = max(M/z - N_c/2, 0) + N_t",
                substitution=f"z={lever_arm:.3f} m",
                result=Quantity(
                    value=governing_values["tension_each"], unit="kN/根"
                ),
                reference="弹性锚栓组快算模型",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=warnings,
        assumptions=[
            "柱脚底板按刚性板与悬臂条带模型筛查。",
            "锚栓按两侧对称布置并采用弹性拉剪分配。",
            "上游反力包为已组合效应，本节点不再次施加荷载分项系数。",
        ],
        applicability=[
            "平面刚架矩形钢柱脚的方案快算",
            "底板和锚栓规则对称布置",
        ],
        disclaimer=DISCLAIMER
        + " 柱脚结果未覆盖锚固混凝土全部破坏模式，不可作为施工详图。",
    )
