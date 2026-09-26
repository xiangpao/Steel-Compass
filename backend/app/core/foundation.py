from __future__ import annotations

from .contact import ContactError, solve_rectangular_contact

from math import hypot, pi, sqrt

from .catalogs import (
    LOAD_CATALOG_VERSION,
    MATERIAL_CATALOG_VERSION,
    REBAR_MATERIALS,
)
from .common import (
    DISCLAIMER,
    STANDARDS,
    mode_bool,
    mode_number,
    mode_text,
    quantity_summary,
    result_class,
)
from .loads import axial_load_envelope, direction_sign, line_load_envelope
from .schemas import (
    CalculationMode,
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    DiagramPoint,
    DiagramSeries,
    LoadCombinationResult,
    LoadDirection,
    Quantity,
    ReactionEnvelope,
)


CONCRETE = {
    "C25": {"fc": 11.9, "ft": 1.27},
    "C30": {"fc": 14.3, "ft": 1.43},
    "C35": {"fc": 16.7, "ft": 1.57},
    "C40": {"fc": 19.1, "ft": 1.71},
}

# 发布门槛：在仓库中补齐手算签核记录和认可软件对照前，
# 基础模块不得在专业模式输出 passed。
FOUNDATION_PROFESSIONAL_VALIDATED = False


def _upstream_reaction_envelopes(
    request: CalculationRequest,
) -> list[ReactionEnvelope]:
    raw = request.inputs.get("upstream_reaction_envelopes")
    if not isinstance(raw, list):
        return []
    envelopes: list[ReactionEnvelope] = []
    for item in raw:
        try:
            envelopes.append(ReactionEnvelope.model_validate(item))
        except (TypeError, ValueError):
            from .errors import CalculationInputError

            raise CalculationInputError(
                "invalid_upstream_reaction_envelope",
                "上游反力包格式无效，不能继续基础验算。",
                field="upstream_reaction_envelopes",
            ) from None
    return envelopes


def _reaction_component(
    envelope: ReactionEnvelope, *names: str
) -> float:
    for name in names:
        quantity = envelope.components.get(name)  # type: ignore[arg-type]
        if quantity is not None:
            return quantity.value
    return 0.0


def _reaction_vertical(envelope: ReactionEnvelope) -> float:
    value = _reaction_component(envelope, "N")
    if "N" not in envelope.components:
        value = _reaction_component(envelope, "Vy")
    if envelope.direction is LoadDirection.UPLIFT:
        return -abs(value)
    return abs(value)


def _reaction_combinations(
    envelopes: list[ReactionEnvelope], permanent_weight: float, uplift: float,
    horizontal_lever_arm_m: float = 0.0,
) -> tuple[list[ReactionEnvelope], list[LoadCombinationResult]]:
    adjusted: list[ReactionEnvelope] = []
    combinations: list[LoadCombinationResult] = []
    for index, item in enumerate(envelopes):
        favorable = item.leading_action == "uplift" or "上拔控制" in (item.combination_name or "")
        permanent_factor = 1.0 if item.limit_state == "SLS" else 0.9 if favorable else 1.3
        uplift_factor = 1.0 if item.limit_state == "SLS" else 1.5
        vertical = (
            _reaction_vertical(item)
            + permanent_factor * permanent_weight
            - uplift_factor * uplift
        )
        components = {
            name: quantity.model_copy(deep=True)
            for name, quantity in item.components.items()
        }
        components["N"] = Quantity(value=vertical, unit="kN")
        if horizontal_lever_arm_m > 0:
            components["Mx"] = Quantity(
                value=_reaction_component(item, "Mx")
                + _reaction_component(item, "Vy") * horizontal_lever_arm_m,
                unit="kN.m",
            )
            components["My"] = Quantity(
                value=_reaction_component(item, "My")
                + _reaction_component(item, "Vx") * horizontal_lever_arm_m,
                unit="kN.m",
            )
        adjusted_item = ReactionEnvelope(
            name=item.name,
            limit_state=item.limit_state,
            combination_id=item.combination_id or f"legacy-{index + 1}",
            combination_name=item.combination_name,
            sls_type=item.sls_type,
            leading_action=item.leading_action,
            direction=(
                LoadDirection.UPLIFT if vertical < 0 else LoadDirection.GRAVITY
            ),
            components=components,  # type: ignore[arg-type]
        )
        adjusted.append(adjusted_item)
        combinations.append(
        LoadCombinationResult(
            name=item.combination_name or f"上游反力-{index + 1}",
            limit_state=item.limit_state,
            combination_id=adjusted_item.combination_id,
            sls_type=item.sls_type,
            leading_action=item.leading_action,
            factors={},
            factored_by_kind={
                "upstream_reaction": Quantity(
                    value=_reaction_vertical(item), unit="kN"
                )
            },
            directions_by_kind={
                "upstream_reaction": [
                    item.direction or LoadDirection.GRAVITY
                ]
            },
            total=Quantity(
                value=vertical,
                unit="kN",
            ),
            effect_components=components,  # type: ignore[arg-type]
        )
        )
    return adjusted, combinations


def _rebar(grade: str) -> dict:
    item = next((item for item in REBAR_MATERIALS if item["id"] == grade), None)
    if item is None or item["status"] in {"legacy", "blocked"} or item["fy_mpa"] is None:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "unsupported_rebar_grade",
            f"钢筋牌号 {grade} 当前不能用于新建基础计算",
            field="rebar_grade",
        )
    return item


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
        demand=Quantity(value=demand, unit=unit),
        capacity=Quantity(value=capacity, unit=unit),
        utilization=max(utilization, 0),
        passed=demand <= capacity,
        reference=reference,
        note=note,
    )


def _foundation_status(
    checks: list[CheckResult], complete: bool, mode: CalculationMode
) -> str:
    if any(not check.passed for check in checks):
        return "failed"
    if not complete:
        return "incomplete"
    if mode is CalculationMode.PROFESSIONAL and not FOUNDATION_PROFESSIONAL_VALIDATED:
        return "incomplete"
    return "passed"


def _provided_rebar_area(diameter_mm: float, spacing_mm: float, width_mm: float) -> float:
    return width_mm / spacing_mm * pi * diameter_mm**2 / 4


def _effective_foundation_weights(
    *,
    plan_area_m2: float,
    thickness_m: float,
    embedment_m: float,
    soil_cover_m: float,
    groundwater_depth_m: float | None,
    concrete_volume_m3: float | None = None,
    soil_cover_volume_m3: float | None = None,
    total_foundation_height_m: float | None = None,
) -> tuple[float, float, float]:
    """Return effective footing, cover and displaced-water weights in kN.

    The submerged portions use buoyant unit weights (water unit weight rounded
    to 10 kN/m3).  `displaced_water` is reported separately for traceability.
    """

    water_unit_weight = 10.0
    foundation_volume = concrete_volume_m3 or plan_area_m2 * thickness_m
    cover_volume = (
        soil_cover_volume_m3
        if soil_cover_volume_m3 is not None
        else plan_area_m2 * soil_cover_m
    )
    total_height = total_foundation_height_m or thickness_m
    submerged_foundation_volume = 0.0
    submerged_cover_volume = 0.0
    if groundwater_depth_m is not None:
        submerged_height = max(0.0, min(total_height, embedment_m - groundwater_depth_m))
        submerged_foundation_volume = foundation_volume * submerged_height / max(total_height, 1e-9)
        submerged_cover_depth = max(0.0, min(soil_cover_m, soil_cover_m - groundwater_depth_m))
        submerged_cover_volume = cover_volume * submerged_cover_depth / max(soil_cover_m, 1e-9)
    gross_footing = foundation_volume * 25.0
    gross_cover = cover_volume * 18.0
    displaced_water = (
        submerged_foundation_volume + submerged_cover_volume
    ) * water_unit_weight
    footing_effective = gross_footing - submerged_foundation_volume * water_unit_weight
    cover_effective = gross_cover - submerged_cover_volume * water_unit_weight
    return footing_effective, cover_effective, displaced_water


def _groundwater_depth(request: CalculationRequest) -> tuple[bool, float | None]:
    condition = request.inputs.get("groundwater_condition")
    if condition is not None:
        condition = str(condition)
        if condition not in {"no_influence", "known_water_table", "unknown"}:
            from .errors import CalculationInputError

            raise CalculationInputError(
                "invalid_groundwater_condition",
                "groundwater_condition 必须为 no_influence、known_water_table 或 unknown",
                field="groundwater_condition",
            )
        if condition == "no_influence":
            return True, None
        if condition == "unknown":
            return (
                False,
                None
                if request.inputs.get("explicit_design_profile")
                else 5.0
                if request.mode is CalculationMode.QUICK
                else None,
            )
        known = True
        raw = request.inputs.get("water_table_depth_m")
        input_field = "water_table_depth_m"
    else:
        # Schema 3.1-and-earlier compatibility.
        known = bool(request.inputs.get("groundwater_known", False))
        raw = request.inputs.get("groundwater_depth_m")
        input_field = "groundwater_depth_m"
    if raw is None:
        return (
            known,
            None
            if request.inputs.get("explicit_design_profile")
            else 5.0
            if request.mode is CalculationMode.QUICK
            else None,
        )
    try:
        depth = float(raw)
    except (TypeError, ValueError):
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_groundwater_depth",
            f"{input_field} 必须为非负数值",
            field=input_field,
        )
    if depth < 0:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_groundwater_depth",
            f"{input_field} 不得小于 0",
            field=input_field,
        )
    return known, depth


def _groundwater_inputs_complete(
    request: CalculationRequest,
    known: bool,
    depth: float | None,
    soil_source: str,
) -> bool:
    if request.schema_version not in {"3.2", "3.3"} or "groundwater_condition" not in request.inputs:
        return known and depth is not None and bool(soil_source)
    condition = str(request.inputs.get("groundwater_condition"))
    groundwater_source = str(request.inputs.get("groundwater_source", "")).strip()
    water_level_complete = condition == "no_influence" or (
        condition == "known_water_table" and depth is not None
    )
    return bool(soil_source) and bool(groundwater_source) and water_level_complete


def calculate_spread_footing(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    length = mode_number(request, "length_m", quick_default=2.0, minimum=0.5, maximum=15)
    width = mode_number(request, "width_m", quick_default=2.0, minimum=0.5, maximum=15)
    thickness = mode_number(
        request, "thickness_mm", quick_default=500, minimum=200, maximum=3000
    )
    column_x = mode_number(
        request, "column_x_mm", quick_default=300, minimum=150, maximum=3000
    )
    column_y = mode_number(
        request, "column_y_mm", quick_default=300, minimum=150, maximum=3000
    )
    pedestal_enabled = bool(request.inputs.get("pedestal_enabled", False))
    pedestal_height = 0.0
    pedestal_weight = 0.0
    if pedestal_enabled:
        required_pedestal = ("pedestal_length_mm", "pedestal_width_mm", "pedestal_height_mm")
        missing = [name for name in required_pedestal if request.inputs.get(name) is None]
        if missing:
            from .errors import CalculationInputError

            raise CalculationInputError(
                "incomplete_pedestal_geometry",
                f"启用短柱时必须填写：{', '.join(missing)}",
                field=missing[0],
            )
        pedestal_length = mode_number(request, "pedestal_length_mm", quick_default=500, minimum=150, maximum=3000)
        pedestal_width = mode_number(request, "pedestal_width_mm", quick_default=500, minimum=150, maximum=3000)
        pedestal_height = mode_number(request, "pedestal_height_mm", quick_default=600, minimum=100, maximum=5000) / 1000
        column_x = pedestal_length
        column_y = pedestal_width
        pedestal_weight = pedestal_length / 1000 * pedestal_width / 1000 * pedestal_height * 25.0
    cover = mode_number(request, "cover_mm", quick_default=50, minimum=35, maximum=150)
    bar_dia_x = mode_number(
        request, "bar_dia_x_mm", quick_default=14, minimum=6, maximum=40
    )
    bar_dia_y = mode_number(
        request, "bar_dia_y_mm", quick_default=14, minimum=6, maximum=40
    )
    spacing_x = mode_number(
        request, "bar_spacing_x_mm", quick_default=150, minimum=50, maximum=400
    )
    spacing_y = mode_number(
        request, "bar_spacing_y_mm", quick_default=150, minimum=50, maximum=400
    )
    concrete_grade = mode_text(
        request, "concrete_grade", quick_default="C30", allowed=set(CONCRETE)
    )
    rebar_grade = mode_text(
        request,
        "rebar_grade",
        quick_default="HRB400",
        allowed={
            "HPB300",
            "HRB400",
            "HRBF400",
            "HRB400E",
            "HRBF400E",
            "HRB500",
            "HRBF500",
            "HRB500E",
            "HRBF500E",
            "RRB400",
        },
    )
    soil_capacity = mode_number(
        request, "soil_capacity_kpa", quick_default=120, minimum=10, maximum=2000
    )
    friction = mode_number(
        request, "base_friction_coefficient", quick_default=0.30, minimum=0, maximum=1
    )
    embedment = mode_number(
        request, "embedment_m", quick_default=1.0, minimum=0, maximum=10
    )
    soil_cover = mode_number(
        request, "soil_cover_m", quick_default=0.5, minimum=0, maximum=8
    )
    concrete_volume = request.inputs.get("footing_concrete_volume_m3")
    soil_cover_volume = request.inputs.get("soil_cover_volume_m3")
    total_foundation_height = request.inputs.get("total_foundation_height_m")
    if concrete_volume is not None:
        concrete_volume = float(concrete_volume)
        if concrete_volume <= 0:
            from .errors import CalculationInputError

            raise CalculationInputError("invalid_footing_volume", "基础混凝土体积必须大于 0", field="footing_concrete_volume_m3")
    if soil_cover_volume is not None:
        soil_cover_volume = float(soil_cover_volume)
        if soil_cover_volume < 0:
            from .errors import CalculationInputError

            raise CalculationInputError("invalid_soil_cover_volume", "基础覆土体积不得小于 0", field="soil_cover_volume_m3")
    if total_foundation_height is not None:
        total_foundation_height = float(total_foundation_height)
        if total_foundation_height <= 0:
            from .errors import CalculationInputError

            raise CalculationInputError("invalid_foundation_height", "基础总高度必须大于 0", field="total_foundation_height_m")
    moment_x = mode_number(
        request, "moment_x_kn_m", quick_default=0, minimum=-100000, maximum=100000
    )
    moment_y = mode_number(
        request, "moment_y_kn_m", quick_default=0, minimum=-100000, maximum=100000
    )
    horizontal_x = mode_number(
        request, "horizontal_x_kn", quick_default=0, minimum=-100000, maximum=100000
    )
    horizontal_y = mode_number(
        request, "horizontal_y_kn", quick_default=0, minimum=-100000, maximum=100000
    )
    uplift = mode_number(
        request, "uplift_kn", quick_default=0, minimum=0, maximum=100000
    )
    groundwater_known, groundwater_depth = _groundwater_depth(request)
    soil_source = str(request.inputs.get("soil_source", "")).strip()

    if column_x >= length * 1000 or column_y >= width * 1000:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_footing_geometry",
            "柱或墩柱尺寸必须小于基础平面尺寸",
            field="column_x_mm",
        )

    concrete = CONCRETE[concrete_grade]
    rebar = _rebar(rebar_grade)
    envelope = axial_load_envelope(request.loads)
    upstream_reactions = _upstream_reaction_envelopes(request)
    area = length * width
    footing_weight, cover_weight, displaced_water = _effective_foundation_weights(
        plan_area_m2=area,
        thickness_m=thickness / 1000,
        embedment_m=embedment,
        soil_cover_m=soil_cover,
        groundwater_depth_m=groundwater_depth,
        concrete_volume_m3=concrete_volume,
        soil_cover_volume_m3=soil_cover_volume,
        total_foundation_height_m=total_foundation_height,
    )
    permanent_weight = footing_weight + cover_weight + pedestal_weight
    adjusted_reactions: list[ReactionEnvelope] = []
    design_reaction: ReactionEnvelope | None = None
    if upstream_reactions:
        adjusted_reactions, result_combinations = _reaction_combinations(
            upstream_reactions, permanent_weight, uplift, pedestal_height
        )
        sls_reactions = [
            item for item in adjusted_reactions if item.limit_state == "SLS"
        ]
        uls_reactions = [
            item for item in adjusted_reactions if item.limit_state == "ULS"
        ]
        if not sls_reactions or not uls_reactions:
            from .errors import CalculationInputError

            raise CalculationInputError(
                "incomplete_upstream_reaction_envelope",
                "上游反力包必须同时包含 ULS 和 SLS 组合。",
                field="upstream_reaction_envelopes",
            )

        def pressure_score(item: ReactionEnvelope) -> float:
            vertical = max(
                _reaction_vertical(item),
                1e-9,
            )
            mx = _reaction_component(item, "Mx")
            my = _reaction_component(item, "My")
            return vertical / area * (
                1
                + 6 * abs(my) / vertical / length
                + 6 * abs(mx) / vertical / width
            )

        pressure_reaction = max(sls_reactions, key=pressure_score)
        design_reaction = max(uls_reactions, key=pressure_score)
        service_vertical = _reaction_vertical(pressure_reaction)
        design_vertical = _reaction_vertical(design_reaction)
        moment_x = _reaction_component(pressure_reaction, "Mx")
        moment_y = _reaction_component(pressure_reaction, "My")
        horizontal_reaction = max(
            sls_reactions,
            key=lambda item: hypot(
                _reaction_component(item, "Vx"),
                _reaction_component(item, "Vy")
                if "N" in item.components
                else 0.0,
            ) / max(max(_reaction_vertical(item), 0) * friction, 1e-9),
        )
        horizontal_x = _reaction_component(horizontal_reaction, "Vx")
        horizontal_y = (
            _reaction_component(horizontal_reaction, "Vy")
            if "N" in horizontal_reaction.components
            else 0.0
        )
    else:
        service_vertical = envelope.maximum_sls.total.value + permanent_weight - uplift
        design_vertical = envelope.maximum_uls.total.value + 1.3 * permanent_weight - 1.5 * uplift
        if pedestal_height > 0:
            moment_x += horizontal_y * pedestal_height
            moment_y += horizontal_x * pedestal_height
        sls_reactions = []
        result_combinations = envelope.combinations
    effective_vertical = max(service_vertical, 1e-9)
    ex = abs(moment_y) / effective_vertical
    ey = abs(moment_x) / effective_vertical
    average_pressure = max(service_vertical, 0) / area
    # Solve every real combination independently; pressure and structural maxima
    # need not belong to the same combination. Foundation weights were added above.
    contact_cases = []
    contact_solutions = []
    contact_unresolved = False
    source_cases = [
        (item.limit_state, item.combination_name, _reaction_vertical(item),
         _reaction_component(item, "Mx"), _reaction_component(item, "My"), item)
        for item in adjusted_reactions
    ] if adjusted_reactions else [
        ("SLS", "SLS-local", service_vertical, moment_x, moment_y, None),
        ("ULS", "ULS-local", design_vertical, moment_x, moment_y, None),
    ]
    for limit_state, name, n, mx, my, original in source_cases:
        try:
            solution = solve_rectangular_contact(length, width, n, mx, my)
        except ContactError as exc:
            contact_unresolved = True
            contact_solutions.append({"combination_name": name, "limit_state": limit_state,
                "status": "no_equilibrium", "reason": str(exc), "verification_status": "unverified"})
        else:
            contact_cases.append((limit_state, name, n, solution, original))
            contact_solutions.append({"combination_name": name, "combination_id": original.combination_id if original else None, "limit_state": limit_state,
                                     "status": "solved", **solution.as_dict()})
    sls_contact = [case for case in contact_cases if case[0] == "SLS"]
    uls_contact = [case for case in contact_cases if case[0] == "ULS"]
    pressure_case = max(sls_contact, key=lambda case: case[3].qmax_kpa) if sls_contact else None
    detach_case = min(sls_contact, key=lambda case: case[3].area_m2) if sls_contact else None
    if pressure_case:
        service_vertical, moment_x, moment_y = pressure_case[3].resultants()
        average_pressure = service_vertical / area
        ex, ey = abs(moment_y)/service_vertical, abs(moment_x)/service_vertical
    qmax = pressure_case[3].qmax_kpa if pressure_case else 0.0
    qmin = pressure_case[3].qmin_kpa if pressure_case else 0.0
    detach_ratio = max(0.0, 1-detach_case[3].area_m2/area) if detach_case else 1.0
    contact_ratio = 1-detach_ratio
    horizontal = hypot(horizontal_x, horizontal_y)
    if sls_reactions:
        sliding_capacity = max(_reaction_vertical(horizontal_reaction), 0) * friction
        overturning_reaction = max(
            sls_reactions,
            key=lambda item: hypot(
                _reaction_component(item, "Mx"),
                _reaction_component(item, "My"),
            ) / max(max(_reaction_vertical(item), 0) * min(length, width) / 2, 1e-9),
        )
        overturning = hypot(
            _reaction_component(overturning_reaction, "Mx"),
            _reaction_component(overturning_reaction, "My"),
        )
        resisting_moment = (
            max(_reaction_vertical(overturning_reaction), 0)
            * min(length, width)
            / 2
        )
    else:
        sliding_capacity = max(service_vertical, 0) * friction
        overturning = hypot(moment_x, moment_y)
        resisting_moment = max(service_vertical, 0) * min(length, width) / 2

    d_x = thickness - cover - bar_dia_x / 2
    d_y = thickness - cover - bar_dia_y / 2
    if min(d_x, d_y) <= 0:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_effective_depth",
            "保护层与钢筋直径导致基础有效高度不大于 0",
        )
    shear_capacity_x = 0.7 * concrete["ft"] * width * 1000 * d_x / 1000
    shear_capacity_y = 0.7 * concrete["ft"] * length * 1000 * d_y / 1000

    punching_depth = min(d_x, d_y)
    # Critical perimeter is located h0/2 outside the loaded-area boundary;
    # therefore its side dimensions are c+h0, not c+2h0.
    punching_perimeter = 2 * (
        column_x + column_y + 2 * punching_depth
    )
    punching_capacity = (
        0.7 * concrete["ft"] * punching_perimeter * punching_depth / 1000
    )

    if sls_reactions:
        uplift_reaction = min(sls_reactions, key=_reaction_vertical)
        minimum_vertical = _reaction_vertical(uplift_reaction)
        # Reactions are already adjusted for footing/cover weight and explicit
        # uplift. Any negative net vertical effect is therefore a failure.
        uplift_demand = max(-minimum_vertical, 0)
        uplift_resistance = 0.0
    else:
        downward_external = sum(
            item.value
            for item in request.loads
            if direction_sign(item.direction) > 0
        )
        upward_external = sum(
            item.value
            for item in request.loads
            if direction_sign(item.direction) < 0
        )
        uplift_demand = upward_external + uplift
        uplift_resistance = permanent_weight + downward_external

    # Integrate the actual pressure polygon at both sides of each section.
    # The rectangular critical punching perimeter is centred on the column.
    uniform_weight_supported = (
        (concrete_volume is None or abs(concrete_volume-area*thickness/1000)<1e-8)
        and (soil_cover_volume is None or abs(soil_cover_volume-area*soil_cover)<1e-8)
    )
    structural_demands = {}
    structural_combinations = {}
    for _, name, n, solution, original in uls_contact:
        favorable = original is not None and (original.leading_action == "uplift" or "上拔控制" in (original.combination_name or ""))
        permanent_factor = .9 if favorable else 1.3
        downward_q = permanent_factor*(footing_weight+cover_weight)/area
        if not uniform_weight_supported:
            downward_q = 0.0  # unknown distribution: results remain provisional below

        cx, cy = column_x / 2000, column_y / 2000
        sx, sy = cx + d_x / 1000, cy + d_y / 1000
        xlo, xhi, ylo, yhi = -length/2, length/2, -width/2, width/2
        def net_integral(bounds):
            x0,x1,y0,y1=bounds
            x0,x1=max(x0,xlo),min(x1,xhi)
            y0,y1=max(y0,ylo),min(y1,yhi)
            if x1<=x0 or y1<=y0:
                return (0.0,0.0,0.0)
            ground=solution.integrate((x0,x1,y0,y1))
            dead=downward_q*(x1-x0)*(y1-y0)
            return ground[0]-dead,ground[1]-dead*(x0+x1)/2,ground[2]-dead*(y0+y1)/2
        def force(bounds):
            return net_integral(bounds)[0]
        vx = max(abs(force((sx,xhi,ylo,yhi))), abs(force((xlo,-sx,ylo,yhi))))
        vy = max(abs(force((xlo,xhi,sy,yhi))), abs(force((xlo,xhi,ylo,-sy))))
        def bending_extremes(axis, face, edge):
            values=[]
            for sign in (-1,1):
                def integral_at(distance):
                    bounds=(distance,xhi,ylo,yhi) if axis==1 and sign==1 else (xlo,-distance,ylo,yhi) if axis==1 else (xlo,xhi,distance,yhi) if sign==1 else (xlo,xhi,ylo,-distance)
                    return net_integral(bounds)
                candidates=[face]
                lo,hi=face,edge-(edge-face)*1e-7
                flo,fhi=integral_at(lo)[0],integral_at(hi)[0]
                if flo*fhi<0:
                    for _ in range(60):
                        middle=(lo+hi)/2
                        fm=integral_at(middle)[0]
                        if flo*fm<=0:
                            hi=middle
                        else:
                            lo,flo=middle,fm
                    candidates.append((lo+hi)/2)
                for distance in candidates:
                    result=integral_at(distance)
                    values.append(sign*result[axis]-distance*result[0])
            return max(max(values),0),max(-min(values),0)
        bx,top_bx=bending_extremes(1,cx,xhi)
        by,top_by=bending_extremes(2,cy,yhi)
        px, py = cx+punching_depth/2000, cy+punching_depth/2000
        vp = abs(n-downward_q*area-force((-px,px,-py,py)))
        for key, value in {"vx":vx,"vy":vy,"bx":bx,"by":by,"top_bx":top_bx,"top_by":top_by,"punch":vp}.items():
            if key not in structural_demands or value > structural_demands[key]:
                structural_demands[key] = value
                structural_combinations[key] = name
    shear_x = structural_demands.get("vx", 0.0)
    shear_y = structural_demands.get("vy", 0.0)
    punching_demand = structural_demands.get("punch", 0.0)
    moment_demand_x = structural_demands.get("bx", 0.0)
    moment_demand_y = structural_demands.get("by", 0.0)
    as_required_x = moment_demand_x * 1e6 / max(0.9 * d_x * rebar["fy_mpa"], 1e-9)
    as_required_y = moment_demand_y * 1e6 / max(0.9 * d_y * rebar["fy_mpa"], 1e-9)
    as_min_x = 0.0015 * width * 1000 * thickness
    as_min_y = 0.0015 * length * 1000 * thickness
    as_demand_x = max(as_required_x, as_min_x)
    as_demand_y = max(as_required_y, as_min_y)
    as_provided_x = _provided_rebar_area(bar_dia_x, spacing_x, width * 1000)
    as_provided_y = _provided_rebar_area(bar_dia_y, spacing_y, length * 1000)

    top_requirements = {}
    top_reinforcement_missing = False
    for axis, effective_depth, transverse in (("x",d_x,width),("y",d_y,length)):
        moment = structural_demands.get("top_b"+axis,0.0)
        if moment <= 1e-8:
            continue
        required = max(moment*1e6/(.9*effective_depth*rebar["fy_mpa"]), .0015*transverse*1000*thickness)
        dia_key,spacing_key=f"top_bar_dia_{axis}_mm",f"top_bar_spacing_{axis}_mm"
        provided = None
        if request.inputs.get(dia_key) is not None and request.inputs.get(spacing_key) is not None:
            dia=mode_number(request,dia_key,quick_default=14,minimum=6,maximum=40)
            spacing=mode_number(request,spacing_key,quick_default=150,minimum=50,maximum=400)
            top_d=thickness-cover-dia/2
            required=max(moment*1e6/(.9*top_d*rebar["fy_mpa"]), .0015*transverse*1000*thickness)
            provided=_provided_rebar_area(dia,spacing,transverse*1000)
        else:
            top_reinforcement_missing=True
        top_requirements[axis]={"moment_kn_m":moment,"required_area_mm2":required,
            "provided_area_mm2":provided,"combination_name":structural_combinations.get("top_b"+axis),
            "missing_inputs":[dia_key,spacing_key] if provided is None else []}
    for record in contact_solutions:
        record["distributed_weight_model"] = "uniform_footing_and_cover" if uniform_weight_supported else "unresolved_nonuniform_weight"
    structural_scope_incomplete = top_reinforcement_missing or not uniform_weight_supported
    # 水浮力抗浮安全系数验算 (GB 50007 / GB 55003)
    # Effective permanent weight already excludes displaced water. Restore gross
    # resistance once when expressing the water-only safety factor.
    buoyancy_force = displaced_water
    net_vertical = (minimum_vertical if sls_reactions else uplift_resistance - uplift_demand)
    buoyancy_safety_factor = max(net_vertical + displaced_water, 0) / max(buoyancy_force, 1e-9) if buoyancy_force > 0 else 2.0

    checks = [
        _check(
            "地基承载力",
            max(qmax, 0),
            soil_capacity,
            "kPa",
            "GB 50007-2011 地基承载力验算",
        ),
        _check(
            "基底脱开区比例",
            detach_ratio * 100.0,
            25.0,
            "%",
            "GB 50007-2011 5.2.2条 偏心荷载脱开区限制",
            "正常使用极限状态下，偏心荷载作用基底脱开区面积不得超过 25%。",
        ),
        _check(
            "地下水抗浮稳定系数",
            1.05,
            buoyancy_safety_factor if buoyancy_force > 0 else 1.05,
            "1",
            "GB 55003-2021 基础抗浮稳定",
            "抗浮安全系数须大于 1.05。",
        ),
        _check(
            "抗滑稳定",
            horizontal,
            sliding_capacity,
            "kN",
            "GB 55003-2021 基础稳定",
            "未计入被动土压力。",
        ),
        _check(
            "抗倾覆稳定",
            overturning,
            resisting_moment,
            "kN·m",
            "GB 55003-2021 基础稳定",
        ),
        _check(
            "抗浮稳定",
            uplift_demand,
            uplift_resistance,
            "kN",
            "GB 55003-2021 基础抗浮稳定",
            "基础及覆土按地下水位折减为有效重量。",
        ),
        _check(
            "X向单向剪切",
            shear_x,
            shear_capacity_x,
            "kN",
            "GB/T 50010-2010 受剪承载力",
        ),
        _check(
            "Y向单向剪切",
            shear_y,
            shear_capacity_y,
            "kN",
            "GB/T 50010-2010 受剪承载力",
        ),
        _check(
            "柱边冲切",
            punching_demand,
            punching_capacity,
            "kN",
            "GB/T 50010-2010 冲切承载力",
        ),
        _check(
            "X向底筋",
            as_demand_x,
            as_provided_x,
            "mm2",
            "GB/T 50010-2010 受弯与最小配筋",
        ),
        _check(
            "Y向底筋",
            as_demand_y,
            as_provided_y,
            "mm2",
            "GB/T 50010-2010 受弯与最小配筋",
        ),
    ]
    for axis, top in top_requirements.items():
        if top["provided_area_mm2"] is not None:
            check=_check(f"{axis.upper()}向顶筋",top["required_area_mm2"],top["provided_area_mm2"],"mm2",
                         "净向上/向下荷载压区积分；受弯与最小配筋方案筛查")
            check.governing_combination=top["combination_name"]
            checks.append(check)
    if sls_reactions and design_reaction is not None:
        combination_by_check = {
            "地基承载力": pressure_reaction.combination_name,
            "基底全截面接触": pressure_reaction.combination_name,
            "抗滑稳定": horizontal_reaction.combination_name,
            "抗倾覆稳定": overturning_reaction.combination_name,
            "抗浮稳定": uplift_reaction.combination_name,
            "X向单向剪切": design_reaction.combination_name,
            "Y向单向剪切": design_reaction.combination_name,
            "柱边冲切": structural_combinations.get("punch"),
            "X向底筋": design_reaction.combination_name,
            "Y向底筋": design_reaction.combination_name,
        }
        for check in checks:
            check.governing_combination = combination_by_check.get(check.name, check.governing_combination)
    actual_combination_by_check = {
        "地基承载力": pressure_case[1] if pressure_case else None,
        "基底脱开区比例": detach_case[1] if detach_case else None,
        "X向单向剪切": structural_combinations.get("vx"),
        "Y向单向剪切": structural_combinations.get("vy"),
        "柱边冲切": structural_combinations.get("punch"),
        "X向底筋": structural_combinations.get("bx"),
        "Y向底筋": structural_combinations.get("by"),
    }
    for check in checks:
        if check.name in actual_combination_by_check:
            check.governing_combination = actual_combination_by_check[check.name]
    if contact_unresolved:
        # Do not display zero/partial results as completed structural passes.
        checks = [check for check in checks if check.name not in actual_combination_by_check]
    complete = (
        request.mode is CalculationMode.QUICK
        and not bool(request.inputs.get("explicit_design_profile"))
    ) or _groundwater_inputs_complete(
        request, groundwater_known, groundwater_depth, soil_source
    )
    governing = max(checks, key=lambda item: item.utilization)
    warnings = [
        CalculationWarning(
            severity="warning",
            code="foundation_geotechnical_scope",
            message="基础计算不包含沉降、软弱下卧层、液化和复杂地基作用，必须结合勘察报告复核。",
        )
    ]
    if contact_unresolved:
        warnings.append(
            CalculationWarning(
                severity="critical",
                code="partial_contact",
                message="至少一个组合不存在有限压缩接触平衡或求解未收敛；该组合不得形成地基压力及基础配筋通过结论。",
            )
        )
    if structural_scope_incomplete:
        warnings.append(CalculationWarning(severity="critical",code="foundation_net_bending_inputs_incomplete",
            message="净荷载已识别反向弯矩但缺顶筋，或非等厚基础自重分布尚未精确建模；不得形成基础结构通过结论。"))
    if not complete:
        warnings.append(
            CalculationWarning(
                severity="critical",
                code="geotechnical_input_incomplete",
                message="专业模式缺少地下水条件、水位资料来源或地基承载力来源，结论标记为 incomplete。",
            )
        )
    elif (
        request.mode is CalculationMode.PROFESSIONAL
        and not FOUNDATION_PROFESSIONAL_VALIDATED
    ):
        warnings.append(
            CalculationWarning(
                severity="critical",
                code="foundation_validation_pending",
                message="基础模块尚未完成认可软件对照，专业模式不得形成“通过”结论。",
            )
        )

    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status="incomplete" if contact_unresolved or structural_scope_incomplete else _foundation_status(checks, complete, request.mode),  # type: ignore[arg-type]
        workflow_status="capability_unavailable" if contact_unresolved or structural_scope_incomplete else "ready",
        result_class=result_class(request),  # type: ignore[arg-type]
        standards=STANDARDS["foundation"],
        input_summary=quantity_summary(
            {
                "footing_length": (length, "m"),
                "footing_width": (width, "m"),
                "footing_thickness": (thickness, "mm"),
                "column_x": (column_x, "mm"),
                "column_y": (column_y, "mm"),
                "pedestal_enabled": "是" if pedestal_enabled else "否",
                "pedestal_height": (pedestal_height, "m"),
                "pedestal_weight": (pedestal_weight, "kN"),
                "concrete_grade": concrete_grade,
                "rebar_grade": rebar_grade,
                "soil_capacity": (soil_capacity, "kPa"),
                "soil_source": soil_source or "方案假定，待勘察确认",
                "groundwater_condition": str(
                    request.inputs.get(
                        "groundwater_condition",
                        "known_water_table" if groundwater_known else "unknown",
                    )
                ),
                "groundwater_source": str(
                    request.inputs.get("groundwater_source", "旧版输入")
                ),
                "water_table_depth": (
                    (groundwater_depth, "m")
                    if groundwater_depth is not None
                    else "未提供"
                ),
                "displaced_water_weight": (displaced_water, "kN"),
            }
        ),
        combinations=result_combinations,
        reactions={
            "N_service": Quantity(value=service_vertical, unit="kN"),
            "N_design": Quantity(value=design_vertical, unit="kN"),
            "Vx": Quantity(value=horizontal_x, unit="kN"),
            "Vy": Quantity(value=horizontal_y, unit="kN"),
            "Mx": Quantity(value=moment_x, unit="kN·m"),
            "My": Quantity(value=moment_y, unit="kN·m"),
        },
        reaction_envelopes=adjusted_reactions or [
            ReactionEnvelope(
                name="footing_base",
                limit_state=combination.limit_state,
                combination_id=combination.combination_id,
                combination_name=combination.name,
                sls_type=combination.sls_type,
                leading_action=combination.leading_action,
                direction=(
                    LoadDirection.UPLIFT
                    if combination.total.value < 0
                    else LoadDirection.GRAVITY
                ),
                components={
                    "N": Quantity(
                        value=(
                            combination.total.value
                            + (
                                permanent_weight
                                if combination.limit_state == "SLS"
                                else 1.3 * permanent_weight
                            )
                            - (
                                uplift
                                if combination.limit_state == "SLS"
                                else 1.5 * uplift
                            )
                        ),
                        unit="kN",
                    ),
                    "Vx": Quantity(value=horizontal_x, unit="kN"),
                    "Vy": Quantity(value=horizontal_y, unit="kN"),
                    "Mx": Quantity(value=moment_x, unit="kN·m"),
                    "My": Quantity(value=moment_y, unit="kN·m"),
                },
            )
            for combination in result_combinations
        ],
        diagrams=[DiagramSeries(
            name="基底压力（y=0中心截面，x从负边至正边）",
            points=[DiagramPoint(
                x=Quantity(value=length*index/20, unit="m"),
                value=Quantity(value=max(pressure_case[3].pressure_plane(length*(index/20-.5),0),0), unit="kPa"),
            ) for index in range(21)],
        )] if pressure_case else [],
        steps=[
            CalculationStep(
                name="基底平均压力",
                equation="q_avg = N / (B L)",
                substitution=f"N={service_vertical:.3f} kN, B={width:.3f} m, L={length:.3f} m",
                result=Quantity(value=average_pressure, unit="kPa"),
                reference="GB 50007-2011",
            ),
            CalculationStep(
                name="偏心受压边缘压力",
                equation="q=max(a+b*2x/L+c*2y/B,0); integral(q,q*y,q*x)=(N,Mx,My)",
                substitution=f"e_x={ex:.4f} m, e_y={ey:.4f} m",
                result=Quantity(value=qmax, unit="kPa"),
                reference="刚性矩形板均匀压缩单向支承；压区裁切积分及三分量平衡",
            ),
            CalculationStep(
                name="冲切承载力",
                equation="V_c = 0.7 f_t u_m h_0",
                substitution=f"u_m={punching_perimeter:.1f} mm, h0={punching_depth:.1f} mm",
                result=Quantity(value=punching_capacity, unit="kN"),
                reference="GB/T 50010-2010（Beta 条文映射）",
            ),
        ],
        checks=checks,
        contact_solutions=[{**record,"top_reinforcement_requirements":top_requirements} for record in contact_solutions],
        governing_check=governing.name,
        warnings=warnings,
        assumptions=[
            "基础按刚性矩形板和均匀压缩单向线性支承筛查；脱开压区按三分量平衡求解，不考虑非均匀土层刚度或塑性重分布。",
            "不计被动土压力；基础与覆土自重自动计入。",
            "等厚基础按实际压区反力减均布自重/覆土计算净荷载，搜索柱边及外伸段零剪力截面正负弯矩；非均匀自重分布不形成结构通过结论。",
            *(
                [f"短柱自重 {pedestal_weight:.3f} kN 已计入；柱脚水平力按 {pedestal_height:.3f} m 力臂换算至基础底面，冲切周长采用短柱根部尺寸。"]
                if pedestal_enabled
                else ["未启用短柱；冲切周长采用直接支承构件尺寸。"]
            ),
            f"基底接触面积比 Acontact/A={contact_ratio:.3f}。",
        ],
        applicability=["柱下方形/矩形独立基础", "中心、单向或双向偏心方案筛查"],
        catalog_versions={
            "materials": MATERIAL_CATALOG_VERSION,
            "loads": LOAD_CATALOG_VERSION,
        },
        disclaimer=DISCLAIMER
        + " 基础结果为 Beta，不能替代工程勘察、地基处理设计或注册工程师复核。",
    )


def calculate_strip_footing(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    width = mode_number(request, "width_m", quick_default=1.2, minimum=0.4, maximum=10)
    thickness = mode_number(
        request, "thickness_mm", quick_default=400, minimum=200, maximum=2500
    )
    wall_width = mode_number(
        request, "wall_width_mm", quick_default=240, minimum=100, maximum=2000
    )
    wall_eccentricity = mode_number(
        request,
        "wall_eccentricity_mm",
        quick_default=0,
        minimum=-5000,
        maximum=5000,
    )
    cover = mode_number(request, "cover_mm", quick_default=50, minimum=35, maximum=150)
    bar_dia = mode_number(request, "bar_dia_mm", quick_default=12, minimum=6, maximum=40)
    spacing = mode_number(
        request, "bar_spacing_mm", quick_default=150, minimum=50, maximum=400
    )
    concrete_grade = mode_text(
        request, "concrete_grade", quick_default="C30", allowed=set(CONCRETE)
    )
    rebar_grade = mode_text(
        request,
        "rebar_grade",
        quick_default="HRB400",
        allowed={
            "HPB300",
            "HRB400",
            "HRBF400",
            "HRB400E",
            "HRBF400E",
            "HRB500",
            "HRBF500",
            "HRB500E",
            "HRBF500E",
            "RRB400",
        },
    )
    soil_capacity = mode_number(
        request, "soil_capacity_kpa", quick_default=120, minimum=10, maximum=2000
    )
    friction = mode_number(
        request, "base_friction_coefficient", quick_default=0.30, minimum=0, maximum=1
    )
    embedment = float(request.inputs.get("embedment_m", 0.6))
    soil_cover = float(request.inputs.get("soil_cover_m", 0.0))
    if embedment < 0 or soil_cover < 0:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_embedment",
            "embedment_m 与 soil_cover_m 不得小于 0",
            field="embedment_m",
        )
    horizontal_signed = mode_number(
        request, "horizontal_load_kn_m", quick_default=0, minimum=-100000, maximum=100000
    )
    horizontal = abs(horizontal_signed)
    moment = mode_number(
        request, "moment_kn_m_per_m", quick_default=0, minimum=-100000, maximum=100000
    )
    groundwater_known, groundwater_depth = _groundwater_depth(request)
    soil_source = str(request.inputs.get("soil_source", "")).strip()
    if wall_width >= width * 1000:
        from .errors import CalculationInputError

        raise CalculationInputError(
            "invalid_strip_geometry",
            "墙厚必须小于条形基础宽度",
            field="wall_width_mm",
        )
    concrete = CONCRETE[concrete_grade]
    rebar = _rebar(rebar_grade)
    envelope = line_load_envelope(request.loads)
    footing_weight, cover_weight, displaced_water = _effective_foundation_weights(
        plan_area_m2=width,
        thickness_m=thickness / 1000,
        embedment_m=embedment,
        soil_cover_m=soil_cover,
        groundwater_depth_m=groundwater_depth,
    )
    permanent_weight = footing_weight + cover_weight
    service_vertical = envelope.maximum_sls.total.value + permanent_weight
    design_vertical = envelope.maximum_uls.total.value + 1.3 * permanent_weight
    total_moment = moment + service_vertical * wall_eccentricity / 1000
    eccentricity = total_moment / max(service_vertical, 1e-9)
    qavg = max(service_vertical, 0) / width
    q_left = qavg * (1 - 6 * eccentricity / width)
    q_right = qavg * (1 + 6 * eccentricity / width)
    qmax = max(q_left, q_right)
    qmin = min(q_left, q_right)
    sliding_capacity = service_vertical * friction
    resisting_moment = max(service_vertical, 0) * width / 2
    d = thickness - cover - bar_dia / 2
    projection = (width - wall_width / 1000) / 2
    q_design = max(qmax, 0) * design_vertical / max(service_vertical, 1e-9)
    shear = max(q_design * (projection - d / 1000), 0)
    shear_capacity = 0.7 * concrete["ft"] * 1000 * d / 1000
    bending = q_design * projection**2 / 2
    as_required = bending * 1e6 / max(0.9 * d * rebar["fy_mpa"], 1e-9)
    as_demand = max(as_required, 0.0015 * 1000 * thickness)
    as_provided = _provided_rebar_area(bar_dia, spacing, 1000)
    downward_external = sum(
        item.value for item in request.loads if direction_sign(item.direction) > 0
    )
    upward_external = sum(
        item.value for item in request.loads if direction_sign(item.direction) < 0
    )
    checks = [
        _check("地基承载力", qmax, soil_capacity, "kPa", "GB 50007-2011"),
        _check(
            "基底全截面接触",
            max(-qmin, 0),
            0,
            "kPa",
            "GB 50007-2011 偏心荷载基础",
        ),
        _check("抗滑稳定", horizontal, sliding_capacity, "kN/m", "GB 55003-2021"),
        _check("抗倾覆稳定", abs(total_moment), resisting_moment, "kN·m/m", "GB 55003-2021"),
        _check(
            "抗浮稳定",
            upward_external,
            permanent_weight + downward_external,
            "kN/m",
            "GB 55003-2021 基础抗浮稳定",
            "基础及覆土按地下水位折减为有效重量。",
        ),
        _check("横向单向剪切", shear, shear_capacity, "kN/m", "GB/T 50010-2010"),
        _check("横向底筋", as_demand, as_provided, "mm2/m", "GB/T 50010-2010"),
    ]
    complete = (
        request.mode is CalculationMode.QUICK
        and not bool(request.inputs.get("explicit_design_profile"))
    ) or _groundwater_inputs_complete(
        request, groundwater_known, groundwater_depth, soil_source
    )
    governing = max(checks, key=lambda item: item.utilization)
    warnings = [
        CalculationWarning(
            severity="warning",
            code="strip_scope",
            message="仅适用于每延米均匀墙荷载，不包含纵向不均匀沉降、交叉条基或弹性地基梁作用。",
        )
    ]
    if qmin < 0:
        warnings.append(
            CalculationWarning(
                severity="critical",
                code="partial_contact",
                message="基底出现局部脱开，需专项复核非线性压力分布。",
            )
        )
    if not complete:
        warnings.append(
            CalculationWarning(
                severity="critical",
                code="geotechnical_input_incomplete",
                message="专业模式缺少地下水条件、水位资料来源或地基承载力来源。",
            )
        )
    elif (
        request.mode is CalculationMode.PROFESSIONAL
        and not FOUNDATION_PROFESSIONAL_VALIDATED
    ):
        warnings.append(
            CalculationWarning(
                severity="critical",
                code="foundation_validation_pending",
                message="基础模块尚未完成认可软件对照，专业模式不得形成“通过”结论。",
            )
        )
    return CalculationResult(
        trace_id=trace_id,
        project_name=request.project_name,
        module=request.module,
        mode=request.mode,
        status=_foundation_status(checks, complete, request.mode),  # type: ignore[arg-type]
        result_class=result_class(request),  # type: ignore[arg-type]
        standards=STANDARDS["foundation"],
        input_summary=quantity_summary(
            {
                "footing_width": (width, "m"),
                "footing_thickness": (thickness, "mm"),
                "wall_width": (wall_width, "mm"),
                "wall_eccentricity": (wall_eccentricity, "mm"),
                "concrete_grade": concrete_grade,
                "rebar_grade": rebar_grade,
                "soil_capacity": (soil_capacity, "kPa"),
                "soil_source": soil_source or "方案假定，待勘察确认",
                "groundwater_condition": str(
                    request.inputs.get(
                        "groundwater_condition",
                        "known_water_table" if groundwater_known else "unknown",
                    )
                ),
                "groundwater_source": str(
                    request.inputs.get("groundwater_source", "旧版输入")
                ),
                "water_table_depth": (
                    (groundwater_depth, "m")
                    if groundwater_depth is not None
                    else "未提供"
                ),
                "displaced_water_weight": (displaced_water, "kN/m"),
            }
        ),
        combinations=envelope.combinations,
        reactions={
            "N_service": Quantity(value=service_vertical, unit="kN/m"),
            "Vx": Quantity(value=horizontal_signed, unit="kN/m"),
            "My": Quantity(value=total_moment, unit="kN·m/m"),
        },
        reaction_envelopes=[
            ReactionEnvelope(
                name="strip_footing_base",
                limit_state=combination.limit_state,
                combination_name=combination.name,
                direction=(
                    LoadDirection.UPLIFT
                    if combination.total.value < 0
                    else LoadDirection.GRAVITY
                ),
                components={
                    "N": Quantity(
                        value=combination.total.value + permanent_weight,
                        unit="kN/m",
                    ),
                    "Vx": Quantity(value=horizontal_signed, unit="kN/m"),
                    "My": Quantity(value=total_moment, unit="kN·m/m"),
                },
            )
            for combination in envelope.combinations
        ],
        diagrams=[
            DiagramSeries(
                name="条形基础基底压力",
                points=[
                    DiagramPoint(
                        x=Quantity(value=0, unit="m"),
                        value=Quantity(value=max(q_left, 0), unit="kPa"),
                    ),
                    DiagramPoint(
                        x=Quantity(value=width, unit="m"),
                        value=Quantity(value=max(q_right, 0), unit="kPa"),
                    ),
                ],
            )
        ],
        steps=[
            CalculationStep(
                name="每延米基底平均压力",
                equation="q_avg = N / B",
                substitution=f"N={service_vertical:.3f} kN/m, B={width:.3f} m",
                result=Quantity(value=qavg, unit="kPa"),
                reference="GB 50007-2011",
            ),
            CalculationStep(
                name="偏心受压边缘压力",
                equation="q_max/min = q_avg(1 ± 6e/B)",
                substitution=f"e={eccentricity:.4f} m",
                result=Quantity(value=qmax, unit="kPa"),
                reference="基底线性压力分布；仅适用于全接触",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=warnings,
        assumptions=["按 1 m 长墙下连续条形基础计算。", "基础自重自动计入。"],
        applicability=["均匀线荷载墙下条形基础"],
        catalog_versions={
            "materials": MATERIAL_CATALOG_VERSION,
            "loads": LOAD_CATALOG_VERSION,
        },
        disclaimer=DISCLAIMER
        + " 条形基础结果为 Beta，不能替代工程勘察或纵向地基变形分析。",
    )
