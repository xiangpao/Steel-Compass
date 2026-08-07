from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Literal

from .errors import CalculationInputError
from .parametric_frame import (
    FrameMember,
    FrameNode,
    NodeRestraint,
    ParametricFrameModel,
    UniformMemberLoad,
    solve_parametric_frame,
)


LimitState = Literal["SLS", "ULS"]
FoundationType = Literal["shallow", "pile"]


@dataclass(frozen=True)
class BridgeGeometry:
    span_count: int
    span_length_m: float
    deck_width_m: float
    crossbeam_spacing_m: float
    longitudinal_girder_count: int = 2


@dataclass(frozen=True)
class BridgeActions:
    crowd_load_kpa: float
    additional_dead_load_kpa: float = 0.5
    railing_dead_load_kn_m_per_side: float = 0.5
    wind_line_load_kn_m: float = 0.0
    span_live_load_factors: tuple[float, ...] | None = None


@dataclass(frozen=True)
class TimberDeck:
    thickness_mm: float
    elastic_modulus_mpa: float
    bending_strength_mpa: float
    shear_strength_mpa: float
    unit_weight_kn_m3: float = 6.0
    deflection_limit_ratio: float = 300.0


@dataclass(frozen=True)
class SteelBeamSection:
    area_mm2: float
    inertia_mm4: float
    section_modulus_mm3: float
    shear_area_mm2: float
    yield_strength_mpa: float = 305.0
    elastic_modulus_mpa: float = 206_000.0
    unit_weight_kn_m3: float = 78.5

    @property
    def self_weight_kn_m(self) -> float:
        return self.area_mm2 / 1.0e6 * self.unit_weight_kn_m3


@dataclass(frozen=True)
class BridgeComfortSettings:
    damping_ratio: float = 0.02
    walking_frequency_hz: float = 2.0
    pedestrian_dynamic_force_n: float = 280.0
    acceleration_limit_m_s2: float = 0.50


@dataclass(frozen=True)
class SteelTimberBridgeInput:
    geometry: BridgeGeometry
    actions: BridgeActions
    timber_deck: TimberDeck
    crossbeam_section: SteelBeamSection
    longitudinal_section: SteelBeamSection
    comfort: BridgeComfortSettings = BridgeComfortSettings()
    foundation_types: tuple[FoundationType, ...] | None = None


@dataclass(frozen=True)
class BridgeLayerResponse:
    moment_abs_max_kn_m: float
    shear_abs_max_kn: float
    deflection_abs_max_mm: float
    controlling_member: str


@dataclass(frozen=True)
class BridgeSupportReaction:
    support_id: str
    role: Literal["left_abutment", "pier", "right_abutment"]
    foundation_type: FoundationType
    combination_id: str
    n_vertical_kn: float
    vx_kn: float
    vy_kn: float = 0.0
    mx_kn_m: float = 0.0
    my_kn_m: float = 0.0
    torsion_kn_m: float = 0.0

    @property
    def components_6dof(self) -> dict[str, float]:
        return {
            "N": self.n_vertical_kn,
            "Vx": self.vx_kn,
            "Vy": self.vy_kn,
            "Mx": self.mx_kn_m,
            "My": self.my_kn_m,
            "T": self.torsion_kn_m,
        }


@dataclass(frozen=True)
class BridgeCombinationResult:
    combination_id: str
    limit_state: LimitState
    wind_direction: Literal["none", "positive", "negative"]
    factors: dict[str, float]
    deck: BridgeLayerResponse
    crossbeam: BridgeLayerResponse
    longitudinal_girder: BridgeLayerResponse
    support_reactions: tuple[BridgeSupportReaction, ...]
    total_vertical_load_kn: float
    total_wind_load_kn: float
    vertical_balance_error_kn: float
    lateral_balance_error_kn: float


@dataclass(frozen=True)
class BridgeComfortResult:
    basic_frequency_hz: float
    simplified_peak_acceleration_m_s2: float
    acceleration_limit_m_s2: float
    walking_frequency_hz: float
    resonance_factor: float
    method: str


@dataclass(frozen=True)
class BridgeCheck:
    name: str
    demand: float
    capacity: float
    unit: str
    utilization: float
    passed: bool
    controlling_combination_id: str
    basis: str


@dataclass(frozen=True)
class BridgeResult:
    superstructure_system: Literal["steel_timber"]
    combinations: tuple[BridgeCombinationResult, ...]
    checks: tuple[BridgeCheck, ...]
    comfort: BridgeComfortResult
    governing_check: str
    governing_utilization: float
    equivalent_crossbeam_count: float
    verification_status: Literal["unverified"]
    assumptions: tuple[str, ...]
    applicability: tuple[str, ...]


def _positive(value: float, field: str, *, allow_zero: bool = False) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError(
            "invalid_bridge_input", f"{field} 必须是有限数值。", field=field
        ) from exc
    if not isfinite(numeric) or numeric < 0 or (numeric == 0 and not allow_zero):
        relation = "不得小于零" if allow_zero else "必须大于零"
        raise CalculationInputError(
            "invalid_bridge_input", f"{field} {relation}。", field=field
        )
    return numeric


def _validate_section(section: SteelBeamSection, field: str) -> None:
    for value, name in (
        (section.area_mm2, "area_mm2"),
        (section.inertia_mm4, "inertia_mm4"),
        (section.section_modulus_mm3, "section_modulus_mm3"),
        (section.shear_area_mm2, "shear_area_mm2"),
        (section.yield_strength_mpa, "yield_strength_mpa"),
        (section.elastic_modulus_mpa, "elastic_modulus_mpa"),
        (section.unit_weight_kn_m3, "unit_weight_kn_m3"),
    ):
        _positive(value, f"{field}.{name}")


def _validate(bridge: SteelTimberBridgeInput) -> tuple[float, ...]:
    geometry = bridge.geometry
    actions = bridge.actions
    timber = bridge.timber_deck
    comfort = bridge.comfort
    if isinstance(geometry.span_count, bool) or not isinstance(geometry.span_count, int):
        raise CalculationInputError(
            "invalid_span_count", "span_count 必须是整数。", field="geometry.span_count"
        )
    if not 1 <= geometry.span_count <= 10:
        raise CalculationInputError(
            "span_count_out_of_scope",
            "参数化直线人行桥仅支持 1 至 10 个等跨。",
            field="geometry.span_count",
        )
    if (
        isinstance(geometry.longitudinal_girder_count, bool)
        or not isinstance(geometry.longitudinal_girder_count, int)
        or not 2 <= geometry.longitudinal_girder_count <= 8
    ):
        raise CalculationInputError(
            "girder_count_out_of_scope",
            "纵梁数量必须是 2 至 8 的整数。",
            field="geometry.longitudinal_girder_count",
        )
    for value, field in (
        (geometry.span_length_m, "geometry.span_length_m"),
        (geometry.deck_width_m, "geometry.deck_width_m"),
        (geometry.crossbeam_spacing_m, "geometry.crossbeam_spacing_m"),
        (actions.crowd_load_kpa, "actions.crowd_load_kpa"),
        (timber.thickness_mm, "timber_deck.thickness_mm"),
        (timber.elastic_modulus_mpa, "timber_deck.elastic_modulus_mpa"),
        (timber.bending_strength_mpa, "timber_deck.bending_strength_mpa"),
        (timber.shear_strength_mpa, "timber_deck.shear_strength_mpa"),
        (timber.unit_weight_kn_m3, "timber_deck.unit_weight_kn_m3"),
        (timber.deflection_limit_ratio, "timber_deck.deflection_limit_ratio"),
        (comfort.damping_ratio, "comfort.damping_ratio"),
        (comfort.walking_frequency_hz, "comfort.walking_frequency_hz"),
        (comfort.pedestrian_dynamic_force_n, "comfort.pedestrian_dynamic_force_n"),
        (comfort.acceleration_limit_m_s2, "comfort.acceleration_limit_m_s2"),
    ):
        _positive(value, field)
    for value, field in (
        (actions.additional_dead_load_kpa, "actions.additional_dead_load_kpa"),
        (actions.railing_dead_load_kn_m_per_side, "actions.railing_dead_load_kn_m_per_side"),
        (actions.wind_line_load_kn_m, "actions.wind_line_load_kn_m"),
    ):
        _positive(value, field, allow_zero=True)
    if geometry.span_length_m > 30.0 or geometry.deck_width_m > 12.0:
        raise CalculationInputError(
            "bridge_geometry_out_of_scope",
            "首期景观人行梁桥限单跨长度 30 m、桥面宽度 12 m。",
            field="geometry",
        )
    if geometry.crossbeam_spacing_m > geometry.span_length_m:
        raise CalculationInputError(
            "crossbeam_spacing_out_of_scope",
            "横梁间距不得大于单跨长度。",
            field="geometry.crossbeam_spacing_m",
        )
    factors = actions.span_live_load_factors or (1.0,) * geometry.span_count
    if len(factors) != geometry.span_count:
        raise CalculationInputError(
            "invalid_span_load_factors",
            "逐跨人群荷载系数数量必须等于 span_count。",
            field="actions.span_live_load_factors",
        )
    for index, factor in enumerate(factors):
        _positive(factor, f"actions.span_live_load_factors[{index}]", allow_zero=True)
    if max(factors) <= 0.0:
        raise CalculationInputError(
            "missing_live_load_pattern",
            "至少一个桥跨的人群荷载系数必须大于零。",
            field="actions.span_live_load_factors",
        )
    foundations = bridge.foundation_types
    if foundations is not None:
        if len(foundations) != geometry.span_count + 1:
            raise CalculationInputError(
                "invalid_foundation_count",
                "基础策略数量必须等于桥台与桥墩支点总数。",
                field="foundation_types",
            )
        if any(item not in {"shallow", "pile"} for item in foundations):
            raise CalculationInputError(
                "invalid_foundation_type",
                "基础策略仅允许 shallow 或 pile。",
                field="foundation_types",
            )
    _validate_section(bridge.crossbeam_section, "crossbeam_section")
    _validate_section(bridge.longitudinal_section, "longitudinal_section")
    return tuple(float(value) for value in factors)


def _beam_response(
    *,
    member_prefix: str,
    lengths_m: tuple[float, ...],
    section: SteelBeamSection,
    line_loads_kn_m: tuple[float, ...],
    samples_per_member: int = 101,
):
    nodes = tuple(
        FrameNode(f"{member_prefix}-support-{index}", sum(lengths_m[:index]), 0.0, "m")
        for index in range(len(lengths_m) + 1)
    )
    members = tuple(
        FrameMember(
            f"{member_prefix}-span-{index + 1}",
            nodes[index].id,
            nodes[index + 1].id,
            section.area_mm2,
            section.inertia_mm4,
            section.elastic_modulus_mpa,
        )
        for index in range(len(lengths_m))
    )
    restraints = tuple(
        NodeRestraint(node.id, ux=index == 0, uy=True)
        for index, node in enumerate(nodes)
    )
    loads = tuple(
        UniformMemberLoad(member.id, -line_loads_kn_m[index], "kN/m")
        for index, member in enumerate(members)
    )
    return solve_parametric_frame(
        ParametricFrameModel(
            nodes=nodes,
            members=members,
            restraints=restraints,
            uniform_loads=loads,
        ),
        samples_per_member=samples_per_member,
    )


def _layer_response(solution) -> BridgeLayerResponse:
    controlling = max(
        solution.members.values(), key=lambda item: item.extrema.moment_abs_max_nmm
    )
    return BridgeLayerResponse(
        moment_abs_max_kn_m=max(
            item.extrema.moment_abs_max_nmm for item in solution.members.values()
        )
        / 1.0e6,
        shear_abs_max_kn=max(
            item.extrema.shear_abs_max_n for item in solution.members.values()
        )
        / 1_000.0,
        deflection_abs_max_mm=max(
            item.extrema.local_transverse_abs_max_mm
            for item in solution.members.values()
        ),
        controlling_member=controlling.member,
    )


def _deck_response(
    bridge: SteelTimberBridgeInput,
    *,
    permanent_factor: float,
    live_factor: float,
    span_live_factor: float,
) -> BridgeLayerResponse:
    timber = bridge.timber_deck
    span_m = bridge.geometry.crossbeam_spacing_m
    self_weight = timber.thickness_mm / 1_000.0 * timber.unit_weight_kn_m3
    line_load = (
        (self_weight + bridge.actions.additional_dead_load_kpa) * permanent_factor
        + bridge.actions.crowd_load_kpa * live_factor * span_live_factor
    )
    length_mm = span_m * 1_000.0
    inertia = 1_000.0 * timber.thickness_mm**3 / 12.0
    return BridgeLayerResponse(
        moment_abs_max_kn_m=abs(line_load) * span_m**2 / 8.0,
        shear_abs_max_kn=abs(line_load) * span_m / 2.0,
        deflection_abs_max_mm=(
            5.0
            * abs(line_load)
            * length_mm**4
            / (384.0 * timber.elastic_modulus_mpa * inertia)
        ),
        controlling_member="timber-deck-1m-strip",
    )


def _support_role(index: int, support_count: int) -> Literal["left_abutment", "pier", "right_abutment"]:
    if index == 0:
        return "left_abutment"
    if index == support_count - 1:
        return "right_abutment"
    return "pier"


def _combination(
    bridge: SteelTimberBridgeInput,
    live_pattern: tuple[float, ...],
    *,
    combination_id: str,
    limit_state: LimitState,
    wind_direction: Literal["none", "positive", "negative"],
    factors: dict[str, float],
) -> BridgeCombinationResult:
    geometry = bridge.geometry
    girder_count = geometry.longitudinal_girder_count
    girder_spacing = geometry.deck_width_m / (girder_count - 1)
    span_lengths = (geometry.span_length_m,) * geometry.span_count
    crossbeam_responses = []
    crossbeam_reactions_by_span: list[list[float]] = []
    deck_responses = []
    for span_index, pattern_factor in enumerate(live_pattern):
        deck_response = _deck_response(
            bridge,
            permanent_factor=factors["permanent"],
            live_factor=factors["crowd"],
            span_live_factor=pattern_factor,
        )
        deck_responses.append(deck_response)
        deck_self_weight = (
            bridge.timber_deck.thickness_mm
            / 1_000.0
            * bridge.timber_deck.unit_weight_kn_m3
        )
        surface_load = (
            (deck_self_weight + bridge.actions.additional_dead_load_kpa)
            * factors["permanent"]
            + bridge.actions.crowd_load_kpa
            * factors["crowd"]
            * pattern_factor
        )
        crossbeam_line_load = (
            surface_load * geometry.crossbeam_spacing_m
            + bridge.crossbeam_section.self_weight_kn_m * factors["permanent"]
        )
        crossbeam_solution = _beam_response(
            member_prefix=f"crossbeam-span-{span_index + 1}",
            lengths_m=(girder_spacing,) * (girder_count - 1),
            section=bridge.crossbeam_section,
            line_loads_kn_m=(crossbeam_line_load,) * (girder_count - 1),
        )
        crossbeam_responses.append(_layer_response(crossbeam_solution))
        crossbeam_reactions_by_span.append(
            [
                crossbeam_solution.reactions[
                    f"crossbeam-span-{span_index + 1}-support-{girder_index}"
                ].fy_n
                / 1_000.0
                for girder_index in range(girder_count)
            ]
        )

    longitudinal_solutions = []
    applied_vertical = 0.0
    for girder_index in range(girder_count):
        rail_line = (
            bridge.actions.railing_dead_load_kn_m_per_side * factors["permanent"]
            if girder_index in {0, girder_count - 1}
            else 0.0
        )
        line_loads = tuple(
            crossbeam_reactions_by_span[span_index][girder_index]
            / geometry.crossbeam_spacing_m
            + rail_line
            + bridge.longitudinal_section.self_weight_kn_m * factors["permanent"]
            for span_index in range(geometry.span_count)
        )
        applied_vertical += sum(
            line_load * geometry.span_length_m for line_load in line_loads
        )
        longitudinal_solutions.append(
            _beam_response(
                member_prefix=f"longitudinal-{girder_index + 1}",
                lengths_m=span_lengths,
                section=bridge.longitudinal_section,
                line_loads_kn_m=line_loads,
            )
        )

    support_count = geometry.span_count + 1
    vertical_by_support = [0.0] * support_count
    for girder_index, solution in enumerate(longitudinal_solutions):
        for support_index in range(support_count):
            vertical_by_support[support_index] += solution.reactions[
                f"longitudinal-{girder_index + 1}-support-{support_index}"
            ].fy_n / 1_000.0
    wind_sign = -1.0 if wind_direction == "negative" else 1.0
    total_wind = (
        wind_sign
        * bridge.actions.wind_line_load_kn_m
        * factors["wind"]
        * geometry.span_count
        * geometry.span_length_m
        if wind_direction != "none"
        else 0.0
    )
    tributary_lengths = [geometry.span_length_m / 2.0] + [
        geometry.span_length_m
    ] * (support_count - 2) + [geometry.span_length_m / 2.0]
    total_tributary = sum(tributary_lengths)
    foundations = bridge.foundation_types or ("shallow",) * support_count
    reactions = tuple(
        BridgeSupportReaction(
            support_id=f"support-{index}",
            role=_support_role(index, support_count),
            foundation_type=foundations[index],
            combination_id=combination_id,
            n_vertical_kn=vertical_by_support[index],
            vx_kn=total_wind * tributary_lengths[index] / total_tributary,
        )
        for index in range(support_count)
    )
    deck = max(deck_responses, key=lambda item: item.moment_abs_max_kn_m)
    crossbeam = max(crossbeam_responses, key=lambda item: item.moment_abs_max_kn_m)
    longitudinal = max(
        (_layer_response(item) for item in longitudinal_solutions),
        key=lambda item: item.moment_abs_max_kn_m,
    )
    return BridgeCombinationResult(
        combination_id=combination_id,
        limit_state=limit_state,
        wind_direction=wind_direction,
        factors=dict(factors),
        deck=deck,
        crossbeam=crossbeam,
        longitudinal_girder=longitudinal,
        support_reactions=reactions,
        total_vertical_load_kn=applied_vertical,
        total_wind_load_kn=total_wind,
        vertical_balance_error_kn=sum(item.n_vertical_kn for item in reactions)
        - applied_vertical,
        lateral_balance_error_kn=sum(item.vx_kn for item in reactions) - total_wind,
    )


def _check(
    name: str,
    demand: float,
    capacity: float,
    unit: str,
    combination_id: str,
    basis: str,
) -> BridgeCheck:
    utilization = demand / max(capacity, 1.0e-12)
    return BridgeCheck(
        name=name,
        demand=demand,
        capacity=capacity,
        unit=unit,
        utilization=utilization,
        passed=demand <= capacity,
        controlling_combination_id=combination_id,
        basis=basis,
    )


def _comfort(bridge: SteelTimberBridgeInput) -> BridgeComfortResult:
    geometry = bridge.geometry
    section = bridge.longitudinal_section
    timber_dead = (
        bridge.timber_deck.thickness_mm
        / 1_000.0
        * bridge.timber_deck.unit_weight_kn_m3
    )
    dead_line_per_girder = (
        (timber_dead + bridge.actions.additional_dead_load_kpa)
        * geometry.deck_width_m
        / geometry.longitudinal_girder_count
        + bridge.crossbeam_section.self_weight_kn_m
        * geometry.deck_width_m
        / geometry.crossbeam_spacing_m
        / geometry.longitudinal_girder_count
        + section.self_weight_kn_m
        + 2.0
        * bridge.actions.railing_dead_load_kn_m_per_side
        / geometry.longitudinal_girder_count
    )
    mass_kg_m = dead_line_per_girder * 1_000.0 / 9.81
    e_pa = section.elastic_modulus_mpa * 1.0e6
    inertia_m4 = section.inertia_mm4 * 1.0e-12
    length_m = geometry.span_length_m
    frequency = pi / (2.0 * length_m**2) * sqrt(e_pa * inertia_m4 / mass_kg_m)
    frequency_gap = abs(frequency - bridge.comfort.walking_frequency_hz)
    resonance_factor = max(0.20, 1.0 - frequency_gap / 1.5)
    modal_mass = 0.5 * mass_kg_m * length_m
    acceleration = (
        bridge.comfort.pedestrian_dynamic_force_n
        * resonance_factor
        / (2.0 * bridge.comfort.damping_ratio * modal_mass)
    )
    return BridgeComfortResult(
        basic_frequency_hz=frequency,
        simplified_peak_acceleration_m_s2=acceleration,
        acceleration_limit_m_s2=bridge.comfort.acceleration_limit_m_s2,
        walking_frequency_hz=bridge.comfort.walking_frequency_hz,
        resonance_factor=resonance_factor,
        method="single-mode equivalent pedestrian force; not a time-history analysis",
    )


def calculate_steel_timber_bridge(bridge: SteelTimberBridgeInput) -> BridgeResult:
    live_pattern = _validate(bridge)
    factor_sets = (
        (
            "sls-service",
            "SLS",
            "none",
            {"permanent": 1.0, "crowd": 1.0, "wind": 0.0},
        ),
        (
            "sls-wind-positive",
            "SLS",
            "positive",
            {"permanent": 1.0, "crowd": 0.7, "wind": 1.0},
        ),
        (
            "sls-wind-negative",
            "SLS",
            "negative",
            {"permanent": 1.0, "crowd": 0.7, "wind": 1.0},
        ),
        (
            "uls-crowd",
            "ULS",
            "none",
            {"permanent": 1.3, "crowd": 1.5, "wind": 0.0},
        ),
        (
            "uls-wind-positive",
            "ULS",
            "positive",
            {"permanent": 1.3, "crowd": 1.05, "wind": 1.5},
        ),
        (
            "uls-wind-negative",
            "ULS",
            "negative",
            {"permanent": 1.3, "crowd": 1.05, "wind": 1.5},
        ),
    )
    combinations = tuple(
        _combination(
            bridge,
            live_pattern,
            combination_id=combination_id,
            limit_state=limit_state,  # type: ignore[arg-type]
            wind_direction=wind_direction,  # type: ignore[arg-type]
            factors=factors,
        )
        for combination_id, limit_state, wind_direction, factors in factor_sets
    )
    uls = [item for item in combinations if item.limit_state == "ULS"]
    sls = [item for item in combinations if item.limit_state == "SLS"]
    deck_strength = max(uls, key=lambda item: item.deck.moment_abs_max_kn_m)
    deck_service = max(sls, key=lambda item: item.deck.deflection_abs_max_mm)
    cross_strength = max(uls, key=lambda item: item.crossbeam.moment_abs_max_kn_m)
    cross_service = max(sls, key=lambda item: item.crossbeam.deflection_abs_max_mm)
    longitudinal_strength = max(
        uls, key=lambda item: item.longitudinal_girder.moment_abs_max_kn_m
    )
    longitudinal_service = max(
        sls, key=lambda item: item.longitudinal_girder.deflection_abs_max_mm
    )
    timber = bridge.timber_deck
    timber_section_modulus = 1_000.0 * timber.thickness_mm**2 / 6.0
    timber_shear_area = 2.0 / 3.0 * 1_000.0 * timber.thickness_mm
    cross = bridge.crossbeam_section
    longitudinal = bridge.longitudinal_section
    comfort = _comfort(bridge)
    checks = (
        _check("木桥面板抗弯", deck_strength.deck.moment_abs_max_kn_m, timber.bending_strength_mpa * timber_section_modulus / 1.0e6, "kN*m", deck_strength.combination_id, "1 m 宽简支木板条带"),
        _check("木桥面板抗剪", deck_strength.deck.shear_abs_max_kn, timber.shear_strength_mpa * timber_shear_area / 1_000.0, "kN", deck_strength.combination_id, "矩形木板条带有效剪切面积"),
        _check("木桥面板挠度", deck_service.deck.deflection_abs_max_mm, bridge.geometry.crossbeam_spacing_m * 1_000.0 / timber.deflection_limit_ratio, "mm", deck_service.combination_id, "均布荷载简支板条带"),
        _check("钢横梁抗弯", cross_strength.crossbeam.moment_abs_max_kn_m, cross.yield_strength_mpa * cross.section_modulus_mm3 / 1.0e6, "kN*m", cross_strength.combination_id, "连续横梁弹性弯曲筛查"),
        _check("钢横梁抗剪", cross_strength.crossbeam.shear_abs_max_kn, 0.58 * cross.yield_strength_mpa * cross.shear_area_mm2 / 1_000.0, "kN", cross_strength.combination_id, "钢梁有效剪切面积"),
        _check("钢横梁挠度", cross_service.crossbeam.deflection_abs_max_mm, bridge.geometry.deck_width_m / (bridge.geometry.longitudinal_girder_count - 1) * 1_000.0 / 400.0, "mm", cross_service.combination_id, "连续横梁相邻纵梁间 SLS 挠度筛查"),
        _check("钢纵梁抗弯", longitudinal_strength.longitudinal_girder.moment_abs_max_kn_m, longitudinal.yield_strength_mpa * longitudinal.section_modulus_mm3 / 1.0e6, "kN*m", longitudinal_strength.combination_id, "等跨连续钢纵梁弹性弯曲筛查"),
        _check("钢纵梁抗剪", longitudinal_strength.longitudinal_girder.shear_abs_max_kn, 0.58 * longitudinal.yield_strength_mpa * longitudinal.shear_area_mm2 / 1_000.0, "kN", longitudinal_strength.combination_id, "钢梁有效剪切面积"),
        _check("钢纵梁挠度", longitudinal_service.longitudinal_girder.deflection_abs_max_mm, bridge.geometry.span_length_m * 1_000.0 / 400.0, "mm", longitudinal_service.combination_id, "连续纵梁 SLS 挠度筛查"),
        _check("竖向人行舒适度", comfort.simplified_peak_acceleration_m_s2, comfort.acceleration_limit_m_s2, "m/s2", "sls-service", "单模态等效行人力简化；非时程分析"),
    )
    governing = max(checks, key=lambda item: item.utilization)
    return BridgeResult(
        superstructure_system="steel_timber",
        combinations=combinations,
        checks=checks,
        comfort=comfort,
        governing_check=governing.name,
        governing_utilization=governing.utilization,
        equivalent_crossbeam_count=(
            bridge.geometry.span_count
            * bridge.geometry.span_length_m
            / bridge.geometry.crossbeam_spacing_m
        ),
        verification_status="unverified",
        assumptions=(
            "直线、等跨人行梁桥；桥面木板按 1 m 条带跨横梁计算。",
            "横梁在纵梁处连续支承，纵梁在桥台和桥墩处竖向支承；不考虑支座沉降。",
            "横向风由桥面横隔体系按支点纵向分担长度传至下部结构。",
            "舒适度采用一阶单模态等效行人力，不是人群随机振动或时程分析。",
        ),
        applicability=(
            "单跨或 2 至 10 个等跨直线景观人行桥",
            "木桥面板、钢横梁和钢纵梁体系",
            "静力人群荷载、栏杆恒载和正负横向风",
        ),
    )


__all__ = [
    "BridgeActions",
    "BridgeCheck",
    "BridgeComfortResult",
    "BridgeComfortSettings",
    "BridgeGeometry",
    "BridgeResult",
    "BridgeSupportReaction",
    "SteelBeamSection",
    "SteelTimberBridgeInput",
    "TimberDeck",
    "calculate_steel_timber_bridge",
]
