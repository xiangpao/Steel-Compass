from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any

import numpy as np

from .common import (
    DISCLAIMER,
    STANDARDS,
    mode_number,
    mode_text,
    quantity_summary,
    result_status,
)
from .errors import CalculationInputError
from .loads import FACTOR_SETS, _combination_metadata, direction_sign
from .schemas import (
    CalculationRequest,
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CheckResult,
    DiagramPoint,
    DiagramSeries,
    LoadCombinationResult,
    LoadDirection,
    LoadKind,
    Quantity,
    ReactionEnvelope,
)
from .sections import SectionProperties, steel_section
from .steel import E_STEEL, STEEL, steel_design_strength


@dataclass
class Element:
    name: str
    start: int
    end: int
    area: float
    inertia: float
    section: SectionProperties
    distributed_q_n_mm: float = 0.0


@dataclass
class ElementSolution:
    element: Element
    length_mm: float
    local_end_forces: np.ndarray
    local_displacements: np.ndarray


@dataclass
class FrameSolution:
    displacements: np.ndarray
    reactions: np.ndarray
    elements: list[ElementSolution]


def _element_response(
    solution: ElementSolution, samples: int = 101
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate member forces and transverse displacement between FE nodes."""

    x = np.linspace(0.0, solution.length_mm, samples)
    forces = solution.local_end_forces
    displacement = solution.local_displacements
    q = solution.element.distributed_q_n_mm
    moment = -forces[2] + forces[1] * x + q * x**2 / 2
    shear = forces[1] + q * x
    transverse = (
        displacement[1]
        + displacement[2] * x
        + (
            -forces[2] * x**2 / 2
            + forces[1] * x**3 / 6
            + q * x**4 / 24
        )
        / (E_STEEL * solution.element.inertia)
    )
    return x, moment, shear, transverse


def _element_matrices(
    start: tuple[float, float],
    end: tuple[float, float],
    area: float,
    inertia: float,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = hypot(dx, dy)
    c = dx / length
    s = dy / length
    ea_l = E_STEEL * area / length
    ei = E_STEEL * inertia
    k_local = np.array(
        [
            [ea_l, 0, 0, -ea_l, 0, 0],
            [0, 12 * ei / length**3, 6 * ei / length**2, 0, -12 * ei / length**3, 6 * ei / length**2],
            [0, 6 * ei / length**2, 4 * ei / length, 0, -6 * ei / length**2, 2 * ei / length],
            [-ea_l, 0, 0, ea_l, 0, 0],
            [0, -12 * ei / length**3, -6 * ei / length**2, 0, 12 * ei / length**3, -6 * ei / length**2],
            [0, 6 * ei / length**2, 2 * ei / length, 0, -6 * ei / length**2, 4 * ei / length],
        ],
        dtype=float,
    )
    transform = np.array(
        [
            [c, s, 0, 0, 0, 0],
            [-s, c, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
            [0, 0, 0, c, s, 0],
            [0, 0, 0, -s, c, 0],
            [0, 0, 0, 0, 0, 1],
        ],
        dtype=float,
    )
    k_global = transform.T @ k_local @ transform
    return length, k_local, transform, k_global


def _element_dofs(element: Element) -> list[int]:
    return [
        element.start * 3,
        element.start * 3 + 1,
        element.start * 3 + 2,
        element.end * 3,
        element.end * 3 + 1,
        element.end * 3 + 2,
    ]


def solve_portal(
    coordinates: list[tuple[float, float]],
    elements: list[Element],
    *,
    support: str,
    horizontal_force_kn: float,
) -> FrameSolution:
    dof_count = len(coordinates) * 3
    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    loads = np.zeros(dof_count, dtype=float)
    metadata: list[tuple[Element, float, np.ndarray, np.ndarray, np.ndarray]] = []

    for element in elements:
        length, k_local, transform, k_global = _element_matrices(
            coordinates[element.start],
            coordinates[element.end],
            element.area,
            element.inertia,
        )
        dofs = _element_dofs(element)
        for local_i, global_i in enumerate(dofs):
            for local_j, global_j in enumerate(dofs):
                stiffness[global_i, global_j] += k_global[local_i, local_j]
        equivalent_local = np.array(
            [
                0,
                element.distributed_q_n_mm * length / 2,
                element.distributed_q_n_mm * length**2 / 12,
                0,
                element.distributed_q_n_mm * length / 2,
                -element.distributed_q_n_mm * length**2 / 12,
            ],
            dtype=float,
        )
        equivalent_global = transform.T @ equivalent_local
        loads[dofs] += equivalent_global
        metadata.append((element, length, k_local, transform, equivalent_local))

    loads[2 * 3] += horizontal_force_kn * 1000 / 2
    loads[3 * 3] += horizontal_force_kn * 1000 / 2

    restrained = [0, 1, 3, 4]
    if support == "fixed":
        restrained.extend([2, 5])
    free = [index for index in range(dof_count) if index not in restrained]
    kff = stiffness[np.ix_(free, free)]
    if np.linalg.cond(kff) > 1e14:
        raise CalculationInputError(
            "unstable_frame", "刚架刚度矩阵奇异，请检查支承与截面"
        )
    displacement = np.zeros(dof_count, dtype=float)
    displacement[free] = np.linalg.solve(kff, loads[free])
    reactions = stiffness @ displacement - loads

    element_results: list[ElementSolution] = []
    for element, length, k_local, transform, equivalent_local in metadata:
        dofs = _element_dofs(element)
        local_displacement = transform @ displacement[dofs]
        local_forces = k_local @ local_displacement - equivalent_local
        element_results.append(
            ElementSolution(
                element=element,
                length_mm=length,
                local_end_forces=local_forces,
                local_displacements=local_displacement,
            )
        )
    return FrameSolution(displacement, reactions, element_results)


def _sections(request: CalculationRequest) -> tuple[SectionProperties, SectionProperties]:
    beam_data = request.inputs.get("beam_section")
    column_data = request.inputs.get("column_section")
    if request.mode.value == "quick":
        beam_data = beam_data or {
            "section_type": "RHS",
            "h_mm": 300,
            "b_mm": 150,
            "t_mm": 6,
        }
        column_data = column_data or {
            "section_type": "SHS",
            "b_mm": 180,
            "t_mm": 8,
        }
    if not isinstance(beam_data, dict) or not isinstance(column_data, dict):
        raise CalculationInputError(
            "missing_section",
            "专业刚架计算必须分别提供 beam_section 与 column_section",
            field="beam_section/column_section",
        )
    return steel_section(beam_data), steel_section(column_data)


def _frame_loads(
    request: CalculationRequest,
    *,
    beam_self_weight: float,
    wind_area_m2: float,
    height_m: float,
) -> tuple[dict[str, float], dict[LoadDirection, float]]:
    vertical = {kind.value: 0.0 for kind in LoadKind}
    vertical["self_weight"] = beam_self_weight
    wind_by_direction: dict[LoadDirection, float] = {}
    for item in request.loads:
        sign = direction_sign(item.direction)
        is_horizontal_wind = item.kind is LoadKind.WIND and item.direction in {
            LoadDirection.GRAVITY,  # legacy requests treated wind as +X
            LoadDirection.X_POSITIVE,
            LoadDirection.X_NEGATIVE,
            LoadDirection.Y_POSITIVE,
            LoadDirection.Y_NEGATIVE,
        }
        if is_horizontal_wind:
            resolved_direction = (
                LoadDirection.X_POSITIVE
                if item.direction is LoadDirection.GRAVITY
                else item.direction
            )
            if item.unit == "kN":
                wind_value = sign * item.value
            elif item.unit == "kN/m2":
                wind_value = sign * item.value * wind_area_m2
            elif item.unit == "kN/m":
                wind_value = sign * item.value * height_m
            else:  # pragma: no cover - LoadItem currently restricts units
                wind_value = 0.0
            wind_by_direction[resolved_direction] = (
                wind_by_direction.get(resolved_direction, 0.0) + wind_value
            )
        else:
            if item.unit == "kN/m":
                vertical[item.kind.value] += sign * item.value
            elif item.unit == "kN/m2":
                tributary_width = float(request.inputs.get("tributary_width_m", 1.0))
                vertical[item.kind.value] += sign * item.value * tributary_width
            else:
                raise CalculationInputError(
                    "unsupported_frame_load",
                    "刚架竖向荷载使用 kN/m 或 kN/m2；风荷载可使用 kN、kN/m 或 kN/m2",
                    field="loads",
                )
    return vertical, wind_by_direction


def calculate_portal_frame(
    request: CalculationRequest, trace_id: str
) -> CalculationResult:
    span_m = mode_number(request, "span_m", quick_default=5.0, minimum=1, maximum=30)
    height_m = mode_number(request, "height_m", quick_default=3.2, minimum=1, maximum=15)
    support = mode_text(
        request, "base_support", quick_default="fixed", allowed={"fixed", "pinned"}
    )
    wind_area = mode_number(
        request, "wind_area_m2", quick_default=span_m * height_m, minimum=0.1
    )
    grade_name = mode_text(
        request, "steel_grade", quick_default="Q355B", allowed=set(STEEL)
    )
    beam, column = _sections(request)
    beam_input = request.inputs.get("beam_section")
    column_input = request.inputs.get("column_section")
    beam_input = beam_input if isinstance(beam_input, dict) else {"t_mm": 6}
    column_input = column_input if isinstance(column_input, dict) else {"t_mm": 8}

    def governing_thickness(data: dict[str, Any], section: SectionProperties) -> float:
        if section.section_type == "H":
            return max(float(data.get("tw_mm", 6)), float(data.get("tf_mm", 10)))
        return float(data.get("t_mm", 6))

    beam_thickness = governing_thickness(beam_input, beam)
    column_thickness = governing_thickness(column_input, column)
    beam_grade = steel_design_strength(grade_name, beam_thickness)
    column_grade = steel_design_strength(grade_name, column_thickness)
    vertical, wind_by_direction = _frame_loads(
        request,
        beam_self_weight=beam.self_weight_kn_m,
        wind_area_m2=wind_area,
        height_m=height_m,
    )
    coordinates = [
        (0.0, 0.0),
        (span_m * 1000, 0.0),
        (0.0, height_m * 1000),
        (span_m * 1000, height_m * 1000),
    ]
    combinations: list[LoadCombinationResult] = []
    solved: list[tuple[str, str, float, float, FrameSolution]] = []
    directions_by_kind: dict[str, list[LoadDirection]] = {}
    for item in request.loads:
        directions_by_kind.setdefault(item.kind.value, [])
        if item.direction not in directions_by_kind[item.kind.value]:
            directions_by_kind[item.kind.value].append(item.direction)
    directions_by_kind.setdefault("self_weight", [LoadDirection.GRAVITY])
    raw_upstream = request.inputs.get("upstream_reaction_envelopes")
    transferred_combinations: list[tuple[LoadCombinationResult, float, float]] = []
    if isinstance(raw_upstream, list) and raw_upstream:
        if request.loads:
            raise CalculationInputError(
                "duplicate_frame_load_source",
                "刚架收到上游已组合线荷载后，不得再提交普通竖向荷载重复组合。",
                field="loads",
            )
        for index, raw in enumerate(raw_upstream, start=1):
            if not isinstance(raw, dict):
                raise CalculationInputError(
                    "invalid_upstream_reaction_envelope",
                    "刚架上游组合反力包格式无效。",
                    field="upstream_reaction_envelopes",
                )
            transferred = raw.get("transferred_line_load")
            if not isinstance(transferred, dict) or transferred.get("unit") != "kN/m":
                raise CalculationInputError(
                    "missing_transferred_line_load",
                    "檩条至刚架连接必须提供按组合换算的 kN/m 线荷载。",
                    field="upstream_reaction_envelopes",
                )
            name = str(raw.get("combination_name") or f"upstream-{index}")
            limit_state = str(raw.get("limit_state") or "")
            if limit_state not in {"ULS", "SLS"}:
                raise CalculationInputError(
                    "invalid_upstream_limit_state",
                    "上游组合必须明确 ULS 或 SLS。",
                    field="upstream_reaction_envelopes",
                )
            factor_match = next(
                (factors for factor_name, _, factors in FACTOR_SETS if name.startswith(factor_name)),
                None,
            )
            if factor_match is None:
                raise CalculationInputError(
                    "unknown_upstream_combination",
                    "上游组合名称无法映射刚架自重分项系数。",
                    field="upstream_reaction_envelopes",
                    details={"combination_name": name},
                )
            transferred_q = float(transferred.get("value", 0.0))
            q = transferred_q + beam.self_weight_kn_m * factor_match["self_weight"]
            direction_raw = raw.get("direction") or (
                "uplift" if transferred_q < 0 else "gravity"
            )
            direction = LoadDirection(direction_raw)
            combination = LoadCombinationResult(
                name=name,
                combination_id=raw.get("combination_id") or f"upstream-{index}",
                limit_state=limit_state,  # type: ignore[arg-type]
                sls_type=raw.get("sls_type"),
                leading_action=raw.get("leading_action"),
                factors={"self_weight": factor_match["self_weight"]},
                factored_by_kind={
                    "upstream_line_load": Quantity(value=transferred_q, unit="kN/m"),
                    "self_weight": Quantity(
                        value=beam.self_weight_kn_m * factor_match["self_weight"],
                        unit="kN/m",
                    ),
                },
                directions_by_kind={
                    "upstream_line_load": [direction],
                    "self_weight": [LoadDirection.GRAVITY],
                },
                total=Quantity(value=q, unit="kN/m"),
            )
            transferred_combinations.append((combination, q, 0.0))

    wind_branches = list(wind_by_direction.items()) or [(LoadDirection.X_POSITIVE, 0.0)]
    if transferred_combinations:
        prepared_combinations = transferred_combinations
        combinations.extend(item[0] for item in transferred_combinations)
    else:
        prepared_combinations = []
    for name, limit_state, factors in (() if transferred_combinations else FACTOR_SETS):
        for wind_direction, base_wind_kn in wind_branches:
            q = sum(vertical[kind] * factors[kind] for kind in vertical)
            wind = base_wind_kn * factors["wind"]
            combination_name = (
                f"{name}（wind:{wind_direction.value}）"
                if len(wind_branches) > 1
                else name
            )
            combination_directions = {
                key: list(value) for key, value in directions_by_kind.items()
            }
            if wind_by_direction:
                combination_directions["wind"] = [wind_direction]
            sls_type, leading_action = _combination_metadata(name)
            combination = LoadCombinationResult(
                    name=combination_name,
                    limit_state=limit_state,  # type: ignore[arg-type]
                    combination_id=f"frame-{len(prepared_combinations) + 1}",
                    sls_type=sls_type,  # type: ignore[arg-type]
                    leading_action=leading_action,
                    factors=factors,
                    factored_by_kind={
                        **{
                            kind: Quantity(
                                value=vertical[kind] * factors[kind], unit="kN/m"
                            )
                            for kind in vertical
                            if kind != "wind"
                        },
                        "wind": Quantity(value=wind, unit="kN"),
                    },
                    directions_by_kind=combination_directions,
                    total=Quantity(value=q, unit="kN/m"),
                )
            combinations.append(combination)
            prepared_combinations.append((combination, q, wind))

    for combination, q, wind in prepared_combinations:
        combination_name = combination.name
        limit_state = combination.limit_state
        elements = [
            Element("左柱", 0, 2, column.area_mm2, column.ix_mm4, column),
            Element(
                "横梁",
                2,
                3,
                beam.area_mm2,
                beam.ix_mm4,
                beam,
                distributed_q_n_mm=-q,
            ),
            Element("右柱", 1, 3, column.area_mm2, column.ix_mm4, column),
        ]
        solution = solve_portal(
            coordinates, elements, support=support, horizontal_force_kn=wind
        )
        solved.append((combination_name, limit_state, q, wind, solution))

    uls_solutions = [entry for entry in solved if entry[1] == "ULS"]
    worst_solution: FrameSolution | None = None
    worst_name = ""
    worst_beam_m = worst_beam_v = worst_column_m = worst_column_n = 0.0
    for name, _, q, _, solution in uls_solutions:
        beam_result = next(item for item in solution.elements if item.element.name == "横梁")
        column_results = [item for item in solution.elements if "柱" in item.element.name]
        _, beam_moments, beam_shears, _ = _element_response(beam_result)
        beam_m = float(np.max(np.abs(beam_moments))) / 1e6
        beam_v = float(np.max(np.abs(beam_shears))) / 1000
        column_m = max(
            max(abs(item.local_end_forces[2]), abs(item.local_end_forces[5]))
            for item in column_results
        ) / 1e6
        column_n = max(
            max(abs(item.local_end_forces[0]), abs(item.local_end_forces[3]))
            for item in column_results
        ) / 1000
        score = max(
            beam_m / max(beam_grade["fd"] * beam.wx_mm3 / 1e6, 1e-9),
            column_m / max(column_grade["fd"] * column.wx_mm3 / 1e6, 1e-9)
            + column_n / max(column_grade["fd"] * column.area_mm2 / 1000, 1e-9),
        )
        previous_score = max(
            worst_beam_m / max(beam_grade["fd"] * beam.wx_mm3 / 1e6, 1e-9),
            worst_column_m / max(column_grade["fd"] * column.wx_mm3 / 1e6, 1e-9)
            + worst_column_n / max(column_grade["fd"] * column.area_mm2 / 1000, 1e-9),
        )
        if worst_solution is None or score > previous_score:
            worst_solution = solution
            worst_name = name
            worst_beam_m, worst_beam_v = beam_m, beam_v
            worst_column_m, worst_column_n = column_m, column_n
    assert worst_solution is not None

    sls_entries = [item for item in solved if item[1] == "SLS"]
    sls_solution = max(
        sls_entries,
        key=lambda item: max(
            abs(item[4].displacements[6]), abs(item[4].displacements[9])
        ),
    )[4]
    top_drift = max(abs(sls_solution.displacements[6]), abs(sls_solution.displacements[9]))
    sls_beam = next(item for item in sls_solution.elements if item.element.name == "横梁")
    deflection_x, _, _, deflection_values = _element_response(sls_beam)
    vertical_deflection = float(np.max(np.abs(deflection_values)))
    beam_m_cap = beam_grade["fd"] * beam.wx_mm3 / 1e6
    beam_v_cap = beam_grade["fv"] * beam.shear_area_mm2 / 1000
    column_m_cap = column_grade["fd"] * column.wx_mm3 / 1e6
    column_n_cap = column_grade["fd"] * column.area_mm2 / 1000
    interaction = worst_column_m / column_m_cap + worst_column_n / column_n_cap
    checks = [
        CheckResult(
            name="刚架梁抗弯",
            demand=Quantity(value=worst_beam_m, unit="kN·m"),
            capacity=Quantity(value=beam_m_cap, unit="kN·m"),
            utilization=worst_beam_m / beam_m_cap,
            passed=worst_beam_m <= beam_m_cap,
            reference="GB 50017-2017 受弯构件（Beta映射）",
        ),
        CheckResult(
            name="刚架梁抗剪",
            demand=Quantity(value=worst_beam_v, unit="kN"),
            capacity=Quantity(value=beam_v_cap, unit="kN"),
            utilization=worst_beam_v / beam_v_cap,
            passed=worst_beam_v <= beam_v_cap,
            reference="GB 50017-2017 受剪构件（Beta映射）",
        ),
        CheckResult(
            name="刚架柱压弯",
            demand=Quantity(value=interaction, unit="1"),
            capacity=Quantity(value=1, unit="1"),
            utilization=interaction,
            passed=interaction <= 1,
            reference="GB 50017-2017 压弯相互作用筛查",
        ),
        CheckResult(
            name="刚架梁竖向挠度",
            demand=Quantity(value=vertical_deflection, unit="mm"),
            capacity=Quantity(value=span_m * 1000 / 400, unit="mm"),
            utilization=vertical_deflection / (span_m * 1000 / 400),
            passed=vertical_deflection <= span_m * 1000 / 400,
            reference="GB 55001-2021 正常使用极限状态",
        ),
        CheckResult(
            name="柱顶侧移",
            demand=Quantity(value=top_drift, unit="mm"),
            capacity=Quantity(value=height_m * 1000 / 250, unit="mm"),
            utilization=top_drift / (height_m * 1000 / 250),
            passed=top_drift <= height_m * 1000 / 250,
            reference="GB 55001-2021 正常使用极限状态",
        ),
    ]
    beam_element = next(item for item in worst_solution.elements if item.element.name == "横梁")
    moment_x, moment_values, _, _ = _element_response(beam_element)
    moment_points = [
        DiagramPoint(
            x=Quantity(value=float(x / 1000), unit="m"),
            value=Quantity(value=float(moment / 1e6), unit="kN·m"),
        )
        for x, moment in zip(moment_x, moment_values, strict=True)
    ]
    deflection_points = [
        DiagramPoint(
            x=Quantity(value=float(x / 1000), unit="m"),
            value=Quantity(value=float(value), unit="mm"),
        )
        for x, value in zip(deflection_x, deflection_values, strict=True)
    ]
    service_solution = sls_entries[0][4]
    reactions = {
        "left_horizontal": Quantity(value=service_solution.reactions[0] / 1000, unit="kN"),
        "left_vertical": Quantity(value=service_solution.reactions[1] / 1000, unit="kN"),
        "left_moment": Quantity(value=service_solution.reactions[2] / 1e6, unit="kN·m"),
        "right_horizontal": Quantity(value=service_solution.reactions[3] / 1000, unit="kN"),
        "right_vertical": Quantity(value=service_solution.reactions[4] / 1000, unit="kN"),
        "right_moment": Quantity(value=service_solution.reactions[5] / 1e6, unit="kN·m"),
    }
    reaction_envelopes: list[ReactionEnvelope] = []
    combination_by_name = {item.name: item for item in combinations}
    for combination_name, limit_state, q, wind, solution in solved:
        combination_meta = combination_by_name[combination_name]
        if wind < 0:
            direction = LoadDirection.X_NEGATIVE
        elif wind > 0:
            direction = LoadDirection.X_POSITIVE
        elif q < 0:
            direction = LoadDirection.UPLIFT
        else:
            direction = LoadDirection.GRAVITY
        for side, offset in (("left_base", 0), ("right_base", 3)):
            reaction_envelopes.append(
                ReactionEnvelope(
                    name=side,
                    limit_state=limit_state,  # type: ignore[arg-type]
                    combination_id=combination_meta.combination_id,
                    combination_name=combination_name,
                    sls_type=combination_meta.sls_type,
                    leading_action=combination_meta.leading_action,
                    direction=direction,
                    components={
                        "N": Quantity(
                            value=solution.reactions[offset + 1] / 1000,
                            unit="kN",
                        ),
                        "Vx": Quantity(
                            value=solution.reactions[offset] / 1000,
                            unit="kN",
                        ),
                        "My": Quantity(
                            value=solution.reactions[offset + 2] / 1e6,
                            unit="kN·m",
                        ),
                    },
                )
            )
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
                "span": (span_m, "m"),
                "height": (height_m, "m"),
                "base_support": support,
                "beam_section": beam.description,
                "beam_governing_thickness": (beam_thickness, "mm"),
                "beam_design_strength": (beam_grade["fd"], "MPa"),
                "column_section": column.description,
                "column_governing_thickness": (column_thickness, "mm"),
                "column_design_strength": (column_grade["fd"], "MPa"),
                "wind_area": (wind_area, "m²"),
            }
        ),
        combinations=combinations,
        reactions=reactions,
        reaction_envelopes=reaction_envelopes,
        diagrams=[
            DiagramSeries(name=f"横梁弯矩（{worst_name}）", points=moment_points),
            DiagramSeries(name="横梁竖向位移（SLS）", points=deflection_points),
        ],
        steps=[
            CalculationStep(
                name="矩阵位移法",
                equation="KΔ = F",
                substitution=f"12 个整体自由度，支承={support}",
                result=Quantity(value=top_drift, unit="mm"),
                reference="二维平面杆系线弹性矩阵位移法",
            ),
            CalculationStep(
                name="柱压弯相互作用",
                equation="η = N/N_Rd + M/M_Rd",
                substitution=f"N={worst_column_n:.2f} kN, M={worst_column_m:.2f} kN·m",
                result=Quantity(value=interaction, unit="1"),
                reference="GB 50017-2017（Beta筛查）",
            ),
        ],
        checks=checks,
        governing_check=governing.name,
        warnings=[
            CalculationWarning(
                severity="warning",
                code="linear_frame_beta",
                message="刚架为二维线弹性一阶分析，不覆盖二阶效应、节点半刚性、空间作用与抗震。",
            ),
            CalculationWarning(
                severity="info",
                code="vertical_displacement",
                message=f"沿杆件计算的横梁最大竖向位移为 {vertical_deflection:.2f} mm。",
            ),
        ],
        assumptions=["单跨等高平面刚架。", "梁柱节点刚接，柱脚按所选固定或铰接。"],
        applicability=["单跨门式景观刚架", "静力竖向均布荷载与等效水平风荷载"],
        disclaimer=DISCLAIMER,
    )
