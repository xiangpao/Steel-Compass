"""Small, parameterized calculators used by the next scene closures.

These are deliberately bounded screeners.  They expose the same result and
reaction contracts as the existing member engines, but do not claim a general
finite-element or construction-document scope.
"""

from __future__ import annotations

from math import pi

from .catalogs import LOAD_CATALOG_VERSION, MATERIAL_CATALOG_VERSION
from .common import DISCLAIMER, STANDARDS, mode_number, mode_text, quantity_summary, result_class, result_status
from .errors import CalculationInputError
from .hydrostatics import buoyancy_force, hydrostatic_lateral_action, rankine_active_earth_action
from .loads import FACTOR_SETS, line_load_envelope
from .schemas import (
    CalculationMode,
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    LoadCombinationResult,
    LoadDirection,
    LoadKind,
    Quantity,
    ReactionEnvelope,
)
from .sections import steel_section
from .steel import E_STEEL, STEEL, steel_design_strength
from .timber import TIMBER


def _check(name: str, demand: float, capacity: float, unit: str, reference: str, *, note: str | None = None) -> CheckResult:
    utilization = demand / max(capacity, 1e-9)
    return CheckResult(
        name=name,
        demand=Quantity(value=demand, unit=unit),
        capacity=Quantity(value=capacity, unit=unit),
        utilization=max(utilization, 0.0),
        passed=demand <= capacity,
        reference=reference,
        note=note,
    )


def _result(
    request: CalculationRequest,
    trace_id: str,
    *,
    standards: list[str],
    summary: dict,
    combinations: list[LoadCombinationResult],
    reactions: dict[str, Quantity],
    envelopes: list[ReactionEnvelope],
    checks: list[CheckResult],
    steps: list[CalculationStep],
    warnings: list[CalculationWarning],
    assumptions: list[str],
    applicability: list[str],
    catalog_versions: dict[str, str] | None = None,
    diagrams: list = None,
) -> CalculationResult:
    governing = max(checks, key=lambda item: item.utilization) if checks else None
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=result_status([item.utilization for item in checks]) if checks else "incomplete",
        result_class=result_class(request),
        standards=standards,
        input_summary=quantity_summary(summary),
        combinations=combinations,
        reactions=reactions,
        reaction_envelopes=envelopes,
        diagrams=diagrams or [],
        steps=steps,
        checks=checks,
        governing_check=governing.name if governing else None,
        warnings=warnings,
        assumptions=assumptions,
        applicability=applicability,
        catalog_versions=catalog_versions or {},
        disclaimer=DISCLAIMER,
    )


def _combination_actions(
    *,
    permanent_kn: float,
    live_kn: float = 0.0,
    uplift_kn: float = 0.0,
    horizontal_kn: float = 0.0,
    horizontal_direction: LoadDirection = LoadDirection.X_POSITIVE,
    horizontal_moment_kn_m: float = 0.0,
    unit: str = "kN",
) -> list[tuple[LoadCombinationResult, float, float, float]]:
    """Build combination-consistent vertical, horizontal and moment actions."""

    combinations: list[tuple[LoadCombinationResult, float, float, float]] = []
    for index, (name, limit_state, factors) in enumerate(FACTOR_SETS, start=1):
        vertical = (
            permanent_kn * factors["self_weight"]
            + live_kn * factors["live"]
            - uplift_kn * factors["wind"]
        )
        horizontal_magnitude = abs(horizontal_kn) * factors["wind"]
        moment_magnitude = abs(horizontal_moment_kn_m) * factors["wind"]
        horizontal = (
            -horizontal_magnitude
            if horizontal_direction in {LoadDirection.X_NEGATIVE, LoadDirection.Y_NEGATIVE}
            else horizontal_magnitude
        )
        moment = (
            -moment_magnitude
            if horizontal_direction in {LoadDirection.X_NEGATIVE, LoadDirection.Y_NEGATIVE}
            else moment_magnitude
        )
        sls_type = "standard" if "标准组合" in name else "frequent" if "频遇组合" in name else "quasi_permanent" if "准永久组合" in name else None
        leading = "live" if "活荷载控制" in name else "wind" if "风荷载控制" in name else "snow" if "雪荷载控制" in name else "uplift" if "上拔控制" in name else None
        result = LoadCombinationResult(
            name=name,
            limit_state=limit_state,  # type: ignore[arg-type]
            combination_id=f"{limit_state.lower()}-advanced-{index}",
            sls_type=sls_type,  # type: ignore[arg-type]
            leading_action=leading,
            factors=factors,
            factored_by_kind={
                "self_weight": Quantity(value=permanent_kn * factors["self_weight"], unit=unit),
                "live": Quantity(value=live_kn * factors["live"], unit=unit),
                "wind": Quantity(value=horizontal, unit=unit),
                "uplift": Quantity(value=-uplift_kn * factors["wind"], unit=unit),
            },
            directions_by_kind={
                "self_weight": [LoadDirection.GRAVITY],
                "live": [LoadDirection.GRAVITY],
                "wind": [horizontal_direction],
                "uplift": [LoadDirection.UPLIFT],
            },
            total=Quantity(value=vertical, unit=unit),
            effect_components={
                "N": Quantity(value=vertical, unit=unit),
                "Vx": Quantity(value=horizontal, unit=unit),
                "Vy": Quantity(value=0.0, unit=unit),
                "Mx": Quantity(value=0.0, unit="kN·m"),
                "My": Quantity(value=moment, unit="kN·m"),
                "T": Quantity(value=0.0, unit="kN·m"),
            },
        )
        combinations.append((result, vertical, horizontal, moment))
    return combinations


def calculate_timber_deck_panel(request: CalculationRequest, trace_id: str) -> CalculationResult:
    grade_name = mode_text(request, "timber_grade", quick_default="TC13", allowed=set(TIMBER))
    material = TIMBER[grade_name]
    span = mode_number(request, "span_m", quick_default=1.2, minimum=0.3, maximum=6)
    thickness = mode_number(request, "thickness_mm", quick_default=50, minimum=20, maximum=200)
    strip_width = mode_number(request, "strip_width_m", quick_default=1.0, minimum=0.2, maximum=2)
    envelope = line_load_envelope(request.loads, tributary_width_m=strip_width, automatic_self_weight_kn_m=thickness / 1000 * strip_width * material["density"])
    q_uls = abs(envelope.governing_uls.total.value)
    q_sls = abs(envelope.governing_sls.total.value)
    b = strip_width * 1000
    h = thickness
    z = b * h * h / 6
    inertia = b * h**3 / 12
    moment = q_uls * span**2 / 8
    shear = q_uls * span / 2
    deflection = 5 * q_sls * (span * 1000) ** 4 / (384 * material["e"] * inertia)
    checks = [
        _check("铺板抗弯", moment, material["fm"] * z / 1e6, "kN·m", "GB 50005-2017 木构件受弯 Beta筛查"),
        _check("铺板抗剪", shear, material["fv"] * b * h * 2 / 3 / 1000, "kN", "GB 50005-2017 木构件受剪 Beta筛查"),
        _check("铺板挠度", deflection, span * 1000 / 250, "mm", "GB 55005-2021 正常使用限值"),
    ]
    envelopes = [
        ReactionEnvelope(
            name=name,
            limit_state=comb.limit_state,
            combination_id=comb.combination_id,
            combination_name=comb.name,
            sls_type=comb.sls_type,
            leading_action=comb.leading_action,
            direction=LoadDirection.UPLIFT if comb.total.value < 0 else LoadDirection.GRAVITY,
            components={"Vy": Quantity(value=comb.total.value * span / 2, unit="kN")},
        )
        for comb in envelope.combinations
        for name in ("left_support", "right_support")
    ]
    return _result(
        request, trace_id, standards=STANDARDS["timber"],
        summary={"timber_grade": grade_name, "span": (span, "m"), "thickness": (thickness, "mm"), "strip_width": (strip_width, "m")},
        combinations=envelope.combinations, reactions={"left_vertical": Quantity(value=envelope.governing_sls.total.value * span / 2, unit="kN"), "right_vertical": Quantity(value=envelope.governing_sls.total.value * span / 2, unit="kN")}, envelopes=envelopes, checks=checks,
        steps=[CalculationStep(name="铺板最大弯矩", equation="M=qL²/8", substitution=f"q={q_uls:.3f} kN/m, L={span:.3f} m", result=Quantity(value=moment, unit="kN·m"), reference="结构力学简支均布荷载")],
        warnings=[CalculationWarning(severity="warning", code="timber_deck_beta", message="木铺板按一米条带简支快算，不包含连接、湿度和长期变形。")],
        assumptions=["水平直线铺板，荷载沿次梁方向单向分配。", "每个计算条带两端简支。"], applicability=["矩形木铺板、静力均布荷载"], catalog_versions={"materials": MATERIAL_CATALOG_VERSION, "loads": LOAD_CATALOG_VERSION},
    )


def calculate_steel_cantilever_post(request: CalculationRequest, trace_id: str) -> CalculationResult:
    section = steel_section({
        "section_type": request.inputs.get("section_type", "SHS"),
        "b_mm": request.inputs.get("b_mm", 180),
        "h_mm": request.inputs.get("h_mm", 180),
        "t_mm": request.inputs.get("t_mm", 8),
        "diameter_mm": request.inputs.get("diameter_mm", 180),
    })
    grade_name = mode_text(request, "steel_grade", quick_default="Q355B", allowed=set(STEEL))
    grade = steel_design_strength(grade_name, float(request.inputs.get("t_mm", 8)))
    height = mode_number(request, "height_m", quick_default=2.8, minimum=0.5, maximum=12)
    panel_area = mode_number(request, "panel_area_m2", quick_default=1.5, minimum=0.05, maximum=50)
    panel_cg = mode_number(request, "panel_cg_height_m", quick_default=height * 0.75, minimum=0.1, maximum=height)
    eccentricity = mode_number(request, "panel_eccentricity_m", quick_default=0.0, minimum=-5, maximum=5)
    horizontal = 0.0
    vertical = 0.0
    wind_cases: dict[LoadDirection, float] = {}
    for item in request.loads:
        sign = -1.0 if item.direction in {LoadDirection.X_NEGATIVE, LoadDirection.Y_NEGATIVE, LoadDirection.UPLIFT} else 1.0
        if item.kind is LoadKind.WIND:
            if item.unit == "kN/m2":
                force = item.value * panel_area
            elif item.unit == "kN":
                force = item.value
            else:
                raise CalculationInputError("invalid_post_wind_unit", "导视牌风荷载必须为 kN/m² 或 kN。", field="loads")
            direction = item.direction
            if direction not in {LoadDirection.X_POSITIVE, LoadDirection.X_NEGATIVE, LoadDirection.Y_POSITIVE, LoadDirection.Y_NEGATIVE}:
                direction = LoadDirection.X_NEGATIVE if sign < 0 else LoadDirection.X_POSITIVE
            wind_cases[direction] = wind_cases.get(direction, 0.0) + force
        elif item.kind in {LoadKind.DEAD, LoadKind.SELF_WEIGHT}:
            if item.unit == "kN/m2":
                vertical += sign * item.value * panel_area
            elif item.unit == "kN":
                vertical += sign * item.value
            elif item.unit != "kN/m":
                raise CalculationInputError(
                    "invalid_post_vertical_unit",
                    "导视牌自重必须使用 kN/m² 或 kN。",
                    field="loads",
                )
    if not wind_cases:
        wind_cases = {LoadDirection.X_POSITIVE: 0.0}
    horizontal = max(wind_cases.values(), key=abs)
    moment = abs(horizontal) * panel_cg + abs(horizontal * eccentricity)
    axial = abs(vertical)
    slenderness = height * 1000 / min(section.rx_mm, section.ry_mm)
    phi = max(0.35, min(1.0, 1 - slenderness / 500))
    axial_capacity = phi * section.area_mm2 * grade["fd"] / 1000
    bending_capacity = grade["fd"] * section.wx_mm3 / 1e6
    checks = [
        _check("钢柱轴压", axial, axial_capacity, "kN", "GB 50017-2017 轴压构件 Beta筛查"),
        _check("钢柱抗弯", moment, bending_capacity, "kN·m", "GB 50017-2017 压弯构件 Beta筛查"),
        _check("长细比", slenderness, 150, "1", "GB 50017-2017 构件长细比"),
        _check("抗倾覆力矩输入", moment, max(abs(horizontal) * height * 1.5, 1e-9), "kN·m", "GB 55001-2021 作用效应筛查", note="基础节点继续验算完整抗倾覆。"),
    ]
    combinations = []
    for direction, force in wind_cases.items():
        branch = _combination_actions(permanent_kn=vertical, horizontal_kn=abs(force), horizontal_direction=direction, horizontal_moment_kn_m=abs(force) * panel_cg + abs(force * eccentricity))
        for combo, n, v, m in branch:
            combo.combination_id = f"{combo.combination_id}-{direction.value}"
            combinations.append((combo, n, v, m))
    combo_results = [item[0] for item in combinations]
    envelopes = [
        ReactionEnvelope(name="post_base", limit_state=comb.limit_state, combination_id=comb.combination_id, combination_name=comb.name, sls_type=comb.sls_type, leading_action=comb.leading_action, direction=(comb.directions_by_kind.get("wind") or [LoadDirection.UPLIFT if n < 0 else LoadDirection.GRAVITY])[0], components={"N": Quantity(value=n, unit="kN"), "Vx": Quantity(value=v, unit="kN"), "My": Quantity(value=m, unit="kN·m"), "T": Quantity(value=v * eccentricity, unit="kN·m")})
        for comb, n, v, m in combinations
    ]
    return _result(
        request, trace_id, standards=STANDARDS["steel"], summary={"steel_grade": grade_name, "section": section.description, "height": (height, "m"), "panel_area": (panel_area, "m²"), "panel_cg": (panel_cg, "m"), "eccentricity": (eccentricity, "m")}, combinations=combo_results,
        reactions={"base_vertical": Quantity(value=vertical, unit="kN"), "base_horizontal": Quantity(value=horizontal, unit="kN"), "base_moment": Quantity(value=moment, unit="kN·m")}, envelopes=envelopes, checks=checks,
        steps=[CalculationStep(name="面板风合力", equation="F_w=pA", substitution=f"pA={horizontal:.3f} kN", result=Quantity(value=horizontal, unit="kN"), reference="GB 50009-2012 风荷载向导"), CalculationStep(name="柱底弯矩", equation="M=Fh+Fe", substitution=f"F={abs(horizontal):.3f} kN, h={panel_cg:.3f} m, e={eccentricity:.3f} m", result=Quantity(value=moment, unit="kN·m"), reference="悬臂柱静力平衡")],
        warnings=[CalculationWarning(severity="warning", code="post_anchor_concrete_pending", message="锚栓混凝土锥体、拔出、劈裂和基础完整抗倾覆由下游节点继续核查。")], assumptions=["面板按刚性平面、风压均匀作用。", "立柱按等截面悬臂构件。"], applicability=["单柱、矩形面板、水平风作用"], catalog_versions={"loads": LOAD_CATALOG_VERSION},
    )


def calculate_masonry_wall(request: CalculationRequest, trace_id: str) -> CalculationResult:
    height = mode_number(request, "height_m", quick_default=2.0, minimum=0.5, maximum=8)
    spacing = mode_number(request, "column_spacing_m", quick_default=3.0, minimum=0.5, maximum=8)
    thickness = mode_number(request, "thickness_mm", quick_default=240, minimum=100, maximum=600)
    wind_cases: dict[LoadDirection, float] = {}
    for item in request.loads:
        if item.kind is LoadKind.WIND and item.unit == "kN/m2":
            direction = item.direction if item.direction in {LoadDirection.X_POSITIVE, LoadDirection.X_NEGATIVE, LoadDirection.Y_POSITIVE, LoadDirection.Y_NEGATIVE} else LoadDirection.X_POSITIVE
            wind_cases[direction] = wind_cases.get(direction, 0.0) + item.value
    if not wind_cases:
        wind_cases = {LoadDirection.X_POSITIVE: 0.0}
    wind = max(wind_cases.values(), key=abs)
    gravity = sum(item.value for item in request.loads if item.kind in {LoadKind.DEAD, LoadKind.SELF_WEIGHT} and item.unit == "kN/m2") * spacing * height
    # Capacity checks use the magnitude of the governing wind branch.  The
    # sign is carried independently by each reaction envelope below.
    q = abs(wind) * height
    moment = q * spacing**2 / 8
    shear = q * spacing / 2
    section_modulus = 1000 * thickness**2 / 6
    masonry_allowable = mode_number(request, "masonry_bending_strength_mpa", quick_default=0.20, minimum=0.05, maximum=2)
    checks = [_check("砌体墙片平面外弯曲", moment * 1e6 / section_modulus, masonry_allowable, "MPa", "GB 50003-2011 砌体墙片 Beta筛查"), _check("构造柱间距", spacing, 4.0, "m", "GB 50003-2011 构造限制"), _check("墙片剪力", shear, max(masonry_allowable * 1000 * thickness / 6, 1e-9), "kN", "GB 50003-2011 砌体抗剪 Beta筛查")]
    envelopes = []
    combinations = []
    for direction, pressure in wind_cases.items():
        branch_q = abs(pressure) * height
        branch_moment = branch_q * spacing**2 / 8
        branch_shear = branch_q * spacing / 2
        for comb, n, h_force, m in _combination_actions(permanent_kn=gravity, horizontal_kn=branch_shear, horizontal_direction=direction, horizontal_moment_kn_m=branch_moment):
            comb.combination_id = f"{comb.combination_id}-{direction.value}"
            combinations.append(comb)
            for support in ("left", "right"):
                signed_force = h_force
                envelopes.append(ReactionEnvelope(name=f"{support}_wall_support", limit_state=comb.limit_state, combination_id=comb.combination_id, combination_name=comb.name, sls_type=comb.sls_type, leading_action=comb.leading_action, direction=direction, components={"N": Quantity(value=n / 2, unit="kN"), "Vx": Quantity(value=signed_force / 2, unit="kN"), "My": Quantity(value=m / 2, unit="kN·m") }))
    return _result(request, trace_id, standards=STANDARDS["concrete"], summary={"height": (height, "m"), "column_spacing": (spacing, "m"), "thickness": (thickness, "mm"), "wind_pressure": (wind, "kN/m²"), "gravity": (gravity, "kN")}, combinations=combinations, reactions={"left_vertical": Quantity(value=gravity / 2, unit="kN"), "right_vertical": Quantity(value=gravity / 2, unit="kN")}, envelopes=envelopes, checks=checks, steps=[CalculationStep(name="墙片风荷载线值", equation="q=pH", substitution=f"p={wind:.3f} kN/m², H={height:.3f} m", result=Quantity(value=q, unit="kN/m"), reference="墙片均布压力转换")], warnings=[CalculationWarning(severity="warning", code="masonry_confinement_beta", message="默认按 RC 构造柱、地梁和压顶梁约束；砌体强度等级与开洞边界需项目复核。")], assumptions=["直线、等高、规则柱距。", "不含地震、沉降和复杂开洞。"], applicability=["RC 构造柱+砖砌体填充景墙"], catalog_versions={"materials": MATERIAL_CATALOG_VERSION, "loads": LOAD_CATALOG_VERSION})


def calculate_rc_wall(request: CalculationRequest, trace_id: str) -> CalculationResult:
    height = mode_number(request, "height_m", quick_default=1.2, minimum=0.3, maximum=6)
    thickness = mode_number(request, "thickness_mm", quick_default=180, minimum=100, maximum=600)
    width = mode_number(request, "strip_width_m", quick_default=1.0, minimum=0.3, maximum=3)
    concrete_grade = mode_text(request, "concrete_grade", quick_default="C30", allowed={"C25", "C30", "C35", "C40"})
    rebar_dia = mode_number(request, "bar_dia_mm", quick_default=12, minimum=6, maximum=40)
    spacing = mode_number(request, "bar_spacing_mm", quick_default=200, minimum=50, maximum=400)
    # Soil pressure is optional for a free-standing landscape wall, but when
    # a planter binds a soil height the geotechnical inputs become mandatory.
    soil_height = (
        mode_number(request, "soil_height_m", quick_default=0.0, minimum=0.0, maximum=height)
        if "soil_height_m" in request.inputs
        else 0.0
    )
    if soil_height > 0:
        soil_weight = mode_number(request, "soil_unit_weight_kn_m3", quick_default=18.0, minimum=12.0, maximum=25.0)
        soil_phi = mode_number(request, "soil_friction_angle_deg", quick_default=30.0, minimum=5.0, maximum=44.0)
        soil_surcharge = mode_number(request, "soil_surcharge_kpa", quick_default=0.0, minimum=0.0, maximum=100.0)
    else:
        soil_weight, soil_phi, soil_surcharge = 18.0, 30.0, 0.0
    wind_cases: dict[LoadDirection, float] = {}
    permanent_pressure = 0.0
    for item in request.loads:
        if item.unit != "kN/m2":
            continue
        if item.kind is LoadKind.WIND:
            direction = item.direction if item.direction in {LoadDirection.X_POSITIVE, LoadDirection.X_NEGATIVE, LoadDirection.Y_POSITIVE, LoadDirection.Y_NEGATIVE} else LoadDirection.X_POSITIVE
            wind_cases[direction] = wind_cases.get(direction, 0.0) + item.value
        elif item.kind is LoadKind.DEAD:
            permanent_pressure += item.value
    if not wind_cases:
        wind_cases = {LoadDirection.X_POSITIVE: 0.0}
    # Wall self-weight is generated from the geometry once; catalog dead loads
    # remain additional finishes/soil and are not silently duplicated.
    permanent_pressure += 25.0 * thickness / 1000.0
    wind_demand = max(abs(value) for value in wind_cases.values())
    soil_action = (
        rankine_active_earth_action(
            height_m=soil_height,
            friction_angle_deg=soil_phi,
            soil_unit_weight_kn_m3=soil_weight,
            surcharge_kpa=soil_surcharge,
        )
        if soil_height > 0
        else None
    )
    soil_force = soil_action.total_resultant_kn_per_m if soil_action else 0.0
    soil_moment = soil_action.overturning_moment_kn_m_per_m if soil_action else 0.0
    line = wind_demand * height + soil_force
    moment = wind_demand * height**2 / 2 + soil_moment
    shear = line
    fc = {"C25": 11.9, "C30": 14.3, "C35": 16.7, "C40": 19.1}[concrete_grade]
    as_provided = 1000 / spacing * pi * rebar_dia**2 / 4
    capacity = 360 * as_provided * (0.85 * thickness) / 1e6
    checks = [_check("墙身受弯", moment, capacity, "kN·m/m", "GB/T 50010-2010 墙身受弯 Beta筛查"), _check("墙身受剪", shear, 0.7 * 1.43 * width * thickness / 1000, "kN", "GB/T 50010-2010 墙身受剪 Beta筛查"), _check("最小配筋", as_provided, 0.0015 * 1000 * thickness, "mm²/m", "GB/T 50010-2010 构造配筋")]
    combinations = []
    for direction, wind_pressure in wind_cases.items():
        branch_line = abs(wind_pressure) * height + soil_force
        branch_moment = abs(wind_pressure) * height**2 / 2 + soil_moment
        for combo, _, _, _ in _combination_actions(permanent_kn=permanent_pressure * height * width, horizontal_kn=branch_line, horizontal_direction=direction, horizontal_moment_kn_m=branch_moment):
            combo.combination_id = f"{combo.combination_id}-{direction.value}"
            combinations.append(combo)
    envelopes = [ReactionEnvelope(name="wall_base", limit_state=c.limit_state, combination_id=c.combination_id, combination_name=c.name, sls_type=c.sls_type, leading_action=c.leading_action, direction=(c.directions_by_kind.get("wind") or [LoadDirection.GRAVITY])[0], components={"N": c.effect_components["N"], "Vx": c.effect_components["Vx"], "Vy": c.effect_components["Vy"], "Mx": c.effect_components["Mx"], "My": c.effect_components["My"], "T": c.effect_components["T"]}) for c in combinations]
    steps = [CalculationStep(name="墙身弯矩", equation="M=M风+M土", substitution=f"p={wind_demand:.3f} kN/m², H={height:.3f} m, P土={soil_force:.3f} kN/m", result=Quantity(value=moment, unit="kN·m/m"), reference="墙身悬臂受力")]
    if soil_action:
        steps.append(CalculationStep(name="主动土压力", equation="Pₐ=0.5KₐγH²+KₐqH", substitution=f"Kₐ={soil_action.coefficient:.3f}, H土={soil_height:.3f} m", result=Quantity(value=soil_force, unit="kN/m"), reference="Rankine 主动土压力；GB 50007-2011 映射"))
    return _result(request, trace_id, standards=STANDARDS["concrete"], summary={"concrete_grade": concrete_grade, "height": (height, "m"), "thickness": (thickness, "mm"), "reinforcement": (as_provided, "mm²/m"), "concrete_strength": (fc, "MPa"), "soil_height": (soil_height, "m")}, combinations=combinations, reactions={"base_horizontal": Quantity(value=line, unit="kN/m"), "base_moment": Quantity(value=moment, unit="kN·m/m")}, envelopes=envelopes, checks=checks, steps=steps, warnings=[CalculationWarning(severity="warning", code="rc_wall_beta", message="墙体裂缝、长期效应和边界约束仍需专业复核。")], assumptions=["按一米墙宽悬臂条带。", "不含墙顶约束和地震作用。"], applicability=["小型现浇景墙墙身"], catalog_versions={"materials": MATERIAL_CATALOG_VERSION, "loads": LOAD_CATALOG_VERSION})


def calculate_retaining_wall(request: CalculationRequest, trace_id: str) -> CalculationResult:
    height = mode_number(request, "retained_height_m", quick_default=1.5, minimum=0.5, maximum=6)
    stem = mode_number(request, "stem_thickness_mm", quick_default=200, minimum=120, maximum=600) / 1000
    base_width = mode_number(request, "base_width_m", quick_default=1.6, minimum=0.8, maximum=8)
    toe = mode_number(request, "toe_length_m", quick_default=0.45, minimum=0.1, maximum=4)
    heel = max(base_width - toe - stem, 0.1)
    soil_weight = mode_number(request, "soil_unit_weight_kn_m3", quick_default=18, minimum=12, maximum=25)
    phi = mode_number(request, "soil_friction_angle_deg", quick_default=30, minimum=5, maximum=44)
    surcharge = mode_number(request, "surcharge_kpa", quick_default=0, minimum=0, maximum=100)
    soil = rankine_active_earth_action(height_m=height, friction_angle_deg=phi, soil_unit_weight_kn_m3=soil_weight, surcharge_kpa=surcharge)
    water_depth = mode_number(request, "water_level_depth_m", quick_default=0, minimum=0, maximum=height)
    water = hydrostatic_lateral_action(depth_m=water_depth)
    water_uplift = buoyancy_force(plan_area_m2=base_width, submerged_depth_m=mode_number(request, "submerged_depth_m", quick_default=0, minimum=0, maximum=5))
    concrete_weight = (stem * height + base_width * mode_number(request, "base_thickness_m", quick_default=0.35, minimum=0.2, maximum=1.5)) * 25
    soil_over_heel = heel * height * soil_weight
    vertical = concrete_weight + soil_over_heel
    horizontal = soil.total_resultant_kn_per_m + water.resultant_kn_per_m
    overturn = soil.overturning_moment_kn_m_per_m + water.resultant_kn_per_m * water.resultant_height_from_base_m
    friction = mode_number(request, "base_friction_coefficient", quick_default=0.35, minimum=0, maximum=1)
    q_avg = vertical / base_width
    eccentricity = (overturn - vertical * (base_width / 2 - toe)) / max(vertical, 1e-9)
    qmax = q_avg * (1 + 6 * eccentricity / base_width)
    qmin = q_avg * (1 - 6 * eccentricity / base_width)
    soil_capacity = mode_number(request, "soil_capacity_kpa", quick_default=120, minimum=10, maximum=2000)
    checks = [
        _check("基底承载力", max(qmax, 0), soil_capacity, "kPa", "GB 50007-2011"),
        _check("基底全接触", max(-qmin, 0), 0, "kPa", "GB 50007-2011 偏心基础"),
        _check("抗滑", horizontal, max(vertical * friction, 1e-9), "kN/m", "GB 55003-2021"),
        _check("抗倾覆", overturn, max(vertical * (base_width / 2 - toe), 1e-9), "kN·m/m", "GB 55003-2021"),
        _check("抗浮", water_uplift, max(vertical, 1e-9), "kN/m", "GB 55003-2021"),
        _check("墙身弯曲", soil.total_resultant_kn_per_m * height / 3 + water.resultant_kn_per_m * water.resultant_height_from_base_m, max(mode_number(request, "stem_moment_capacity_kn_m_per_m", quick_default=80, minimum=1), 1e-9), "kN·m/m", "GB/T 50010-2010 Beta筛查"),
    ]
    combinations = [item[0] for item in _combination_actions(permanent_kn=vertical, horizontal_kn=horizontal, horizontal_moment_kn_m=overturn, uplift_kn=water_uplift)]
    envelopes = [ReactionEnvelope(name="retaining_base", limit_state=c.limit_state, combination_id=c.combination_id, combination_name=c.name, sls_type=c.sls_type, leading_action=c.leading_action, direction=LoadDirection.GRAVITY, components={"N": Quantity(value=c.effect_components["N"].value, unit="kN"), "Vx": Quantity(value=c.effect_components["Vx"].value, unit="kN"), "My": Quantity(value=c.effect_components["My"].value, unit="kN·m")}) for c in combinations]
    warnings = [CalculationWarning(severity="warning", code="retaining_scope", message="首版仅覆盖水平填土、单一土层、直线墙身；不含地震、整体稳定、沉降和被动土压力贡献。")]
    if qmin < 0:
        warnings.append(CalculationWarning(severity="critical", code="retaining_partial_contact", message="基底局部脱开，需按非线性接触重新复核。"))
    return _result(request, trace_id, standards=STANDARDS["foundation"], summary={"retained_height": (height, "m"), "base_width": (base_width, "m"), "soil_friction_angle": (phi, "deg"), "active_earth_coefficient": (soil.coefficient, "1"), "groundwater_depth": (water_depth, "m"), "q_max": (qmax, "kPa"), "q_min": (qmin, "kPa")}, combinations=combinations, reactions={"base_vertical": Quantity(value=vertical, unit="kN/m"), "base_horizontal": Quantity(value=horizontal, unit="kN/m"), "base_moment": Quantity(value=overturn, unit="kN·m/m")}, envelopes=envelopes, checks=checks, steps=[CalculationStep(name="主动土压力合力", equation="P_a=0.5K_aγH²+K_aqH", substitution=f"K_a={soil.coefficient:.3f}, H={height:.3f} m", result=Quantity(value=soil.total_resultant_kn_per_m, unit="kN/m"), reference="Rankine 主动土压力；GB 50007-2011 映射"), CalculationStep(name="基底偏心", equation="e=M/N", substitution=f"M={overturn:.3f} kN·m/m, N={vertical:.3f} kN/m", result=Quantity(value=eccentricity, unit="m"), reference="GB 50007-2011")], warnings=warnings, assumptions=["按每延米悬臂式钢筋混凝土挡土墙。", "地下水以静水压力和浮力计入。"], applicability=["水平填土、单一土层、直线悬臂挡土墙"], catalog_versions={"loads": LOAD_CATALOG_VERSION, "materials": MATERIAL_CATALOG_VERSION})
