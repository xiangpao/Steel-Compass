from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Literal

from .errors import CalculationInputError
from .structural_solvers import (
    ContinuousBeamModel,
    ContinuousBeamNode,
    ContinuousBeamSpan,
    ContinuousBeamSupport,
    solve_continuous_beam,
)


FoundationType = Literal["shallow", "pile"]


def _finite(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError("invalid_number", f"{name} 必须为有限数值。", field=name) from exc
    if not isfinite(result):
        raise CalculationInputError("invalid_number", f"{name} 必须为有限数值。", field=name)
    return result


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise CalculationInputError("non_positive_value", f"{name} 必须大于零。", field=name)
    return result


@dataclass(frozen=True)
class RCBridgeGeometry:
    span_count: int
    span_length_m: float
    deck_width_m: float
    deck_elevation_m: float
    slab_thickness_mm: float
    girder_count: int
    girder_width_mm: float
    girder_height_mm: float


@dataclass(frozen=True)
class RCBridgeMaterial:
    concrete_elastic_modulus_mpa: float
    concrete_compressive_strength_mpa: float
    concrete_tensile_strength_mpa: float
    rebar_yield_strength_mpa: float
    concrete_density_kn_m3: float = 25.0
    minimum_reinforcement_ratio: float = 0.0015
    maximum_reinforcement_ratio: float = 0.04


@dataclass(frozen=True)
class RCBridgeReinforcement:
    cover_mm: float
    slab_bar_diameter_mm: float
    slab_bar_spacing_mm: float
    girder_bottom_area_mm2: float
    girder_top_area_mm2: float
    girder_stirrup_area_mm2: float
    girder_stirrup_spacing_mm: float


@dataclass(frozen=True)
class RCBridgeSpanLoad:
    additional_dead_kpa: float
    crowd_kpa: float


@dataclass(frozen=True)
class RCBridgeLoads:
    spans: tuple[RCBridgeSpanLoad, ...]
    railing_left_kn_m: float = 0.0
    railing_right_kn_m: float = 0.0
    wind_pressure_kpa: float = 0.0
    wind_exposed_height_m: float = 1.2


@dataclass(frozen=True)
class RCBridgeSupport:
    id: str
    node_index: int
    foundation_type: FoundationType


@dataclass(frozen=True)
class RCBridgeServiceLimits:
    crack_width_limit_mm: float = 0.3
    minimum_vertical_frequency_hz: float = 3.0
    slab_deflection_ratio: float = 250.0
    girder_deflection_ratio: float = 400.0
    cracked_stiffness_factor: float = 0.35


@dataclass(frozen=True)
class RCBridgeModel:
    geometry: RCBridgeGeometry
    material: RCBridgeMaterial
    reinforcement: RCBridgeReinforcement
    loads: RCBridgeLoads
    supports: tuple[RCBridgeSupport, ...]
    service_limits: RCBridgeServiceLimits = RCBridgeServiceLimits()


@dataclass(frozen=True)
class RCBridgeCheck:
    name: str
    demand: float
    capacity: float
    unit: str
    utilization: float
    passed: bool


@dataclass(frozen=True)
class RCBridgeCombination:
    id: str
    limit_state: Literal["ULS", "SLS"]
    permanent_factor: float
    crowd_factor: float
    wind_factor: float
    applied_vertical_kn: float
    applied_wind_kn: float
    applied_wind_moment_kn_m: float
    applied_railing_torsion_kn_m: float


@dataclass(frozen=True)
class RCBridgeReactionEnvelope:
    support: str
    foundation_type: FoundationType
    combination_id: str
    limit_state: Literal["ULS", "SLS"]
    n_kn: float
    vx_kn: float
    vy_kn: float
    mx_kn_m: float
    my_kn_m: float
    torsion_kn_m: float

    @property
    def components_6dof(self) -> dict[str, float]:
        return {
            "N": self.n_kn,
            "Vx": self.vx_kn,
            "Vy": self.vy_kn,
            "Mx": self.mx_kn_m,
            "My": self.my_kn_m,
            "T": self.torsion_kn_m,
        }


@dataclass(frozen=True)
class RCBridgeResult:
    combinations: tuple[RCBridgeCombination, ...]
    reactions: tuple[RCBridgeReactionEnvelope, ...]
    slab_checks: tuple[RCBridgeCheck, ...]
    girder_checks: tuple[RCBridgeCheck, ...]
    maximum_girder_positive_moment_kn_m: float
    maximum_girder_negative_moment_kn_m: float
    maximum_girder_shear_kn: float
    maximum_girder_deflection_mm: float
    estimated_vertical_frequency_hz: float
    screening_passed: bool
    verification_status: str
    applicability: tuple[str, ...]
    exclusions: tuple[str, ...]


def _check(name: str, demand: float, capacity: float, unit: str) -> RCBridgeCheck:
    demand_value, capacity_value = float(demand), float(capacity)
    utilization = demand_value / capacity_value
    return RCBridgeCheck(
        name,
        demand_value,
        capacity_value,
        unit,
        utilization,
        bool(demand_value <= capacity_value * (1 + 1e-12)),
    )


def _validate(model: RCBridgeModel) -> None:
    geometry = model.geometry
    if not isinstance(geometry.span_count, int) or geometry.span_count < 1:
        raise CalculationInputError("invalid_span_count", "跨数必须为正整数。", field="geometry.span_count")
    if not isinstance(geometry.girder_count, int) or geometry.girder_count < 2:
        raise CalculationInputError("invalid_girder_count", "至少需要两片纵梁。", field="geometry.girder_count")
    for name in (
        "span_length_m",
        "deck_width_m",
        "deck_elevation_m",
        "slab_thickness_mm",
        "girder_width_mm",
        "girder_height_mm",
    ):
        _positive(getattr(geometry, name), f"geometry.{name}")
    if len(model.loads.spans) != geometry.span_count:
        raise CalculationInputError(
            "span_load_count_mismatch", "逐跨荷载数量必须与跨数相同。", field="loads.spans"
        )
    for index, load in enumerate(model.loads.spans):
        if _finite(load.additional_dead_kpa, f"loads.spans.{index}.additional_dead_kpa") < 0 or _finite(
            load.crowd_kpa, f"loads.spans.{index}.crowd_kpa"
        ) < 0:
            raise CalculationInputError("invalid_load", "恒载和人群荷载不得小于零。", field="loads.spans")
    for name in ("railing_left_kn_m", "railing_right_kn_m", "wind_pressure_kpa"):
        if _finite(getattr(model.loads, name), f"loads.{name}") < 0:
            raise CalculationInputError("invalid_load", f"loads.{name} 不得小于零。", field=f"loads.{name}")
    _positive(model.loads.wind_exposed_height_m, "loads.wind_exposed_height_m")

    expected_indices = set(range(geometry.span_count + 1))
    support_indices: set[int] = set()
    support_ids: set[str] = set()
    for support in model.supports:
        if not support.id or support.id in support_ids:
            raise CalculationInputError("invalid_support", "支点编号不得为空或重复。", field="supports")
        if support.foundation_type not in {"shallow", "pile"}:
            raise CalculationInputError("invalid_foundation_type", "基础类型仅支持 shallow 或 pile。", field="supports")
        support_ids.add(support.id)
        support_indices.add(support.node_index)
    if support_indices != expected_indices or len(model.supports) != len(expected_indices):
        raise CalculationInputError("invalid_support_layout", "每个跨端节点必须且只能设置一个支点。", field="supports")

    material = model.material
    for name in (
        "concrete_elastic_modulus_mpa",
        "concrete_compressive_strength_mpa",
        "concrete_tensile_strength_mpa",
        "rebar_yield_strength_mpa",
        "concrete_density_kn_m3",
        "minimum_reinforcement_ratio",
        "maximum_reinforcement_ratio",
    ):
        _positive(getattr(material, name), f"material.{name}")
    if material.minimum_reinforcement_ratio >= material.maximum_reinforcement_ratio:
        raise CalculationInputError("invalid_reinforcement_ratio", "最小配筋率必须小于最大配筋率。", field="material")
    reinforcement = model.reinforcement
    for name in (
        "cover_mm",
        "slab_bar_diameter_mm",
        "slab_bar_spacing_mm",
        "girder_bottom_area_mm2",
        "girder_top_area_mm2",
        "girder_stirrup_area_mm2",
        "girder_stirrup_spacing_mm",
    ):
        _positive(getattr(reinforcement, name), f"reinforcement.{name}")
    if reinforcement.cover_mm + reinforcement.slab_bar_diameter_mm / 2 >= geometry.slab_thickness_mm:
        raise CalculationInputError("invalid_effective_depth", "桥面板有效高度必须大于零。", field="reinforcement.cover_mm")
    if reinforcement.cover_mm >= geometry.girder_height_mm:
        raise CalculationInputError("invalid_effective_depth", "纵梁有效高度必须大于零。", field="reinforcement.cover_mm")
    limits = model.service_limits
    for name in (
        "crack_width_limit_mm",
        "minimum_vertical_frequency_hz",
        "slab_deflection_ratio",
        "girder_deflection_ratio",
        "cracked_stiffness_factor",
    ):
        _positive(getattr(limits, name), f"service_limits.{name}")
    if limits.cracked_stiffness_factor > 1:
        raise CalculationInputError("invalid_stiffness_factor", "开裂刚度系数不得大于1。", field="service_limits.cracked_stiffness_factor")


def _beam_analysis(
    span_count: int,
    span_length_mm: float,
    elastic_modulus_mpa: float,
    inertia_mm4: float,
    q_by_span_n_per_mm: tuple[float, ...],
):
    nodes = tuple(ContinuousBeamNode(index) for index in range(span_count + 1))
    spans = tuple(
        ContinuousBeamSpan(
            f"span-{index + 1}",
            index,
            index + 1,
            span_length_mm,
            elastic_modulus_mpa,
            inertia_mm4,
            -q_by_span_n_per_mm[index],
        )
        for index in range(span_count)
    )
    supports = tuple(ContinuousBeamSupport(index) for index in range(span_count + 1))
    return solve_continuous_beam(ContinuousBeamModel(nodes, spans, supports))


def _moment_capacity(as_mm2: float, fy: float, fc: float, width: float, depth: float) -> float:
    compression_depth = as_mm2 * fy / (fc * width)
    lever_arm = max(depth - compression_depth / 2, 0.05 * depth)
    return as_mm2 * fy * lever_arm / 1_000_000


def analyze_rc_pedestrian_bridge(model: RCBridgeModel) -> RCBridgeResult:
    """Analyze a straight, equal-span RC slab-and-girder pedestrian bridge.

    This is an unverified linear screening core. It intentionally does not
    publish a professional design conclusion.
    """

    _validate(model)
    g, m, r, loads, limits = (
        model.geometry,
        model.material,
        model.reinforcement,
        model.loads,
        model.service_limits,
    )
    span_m = g.span_length_m
    span_mm = span_m * 1000
    total_length_m = g.span_count * span_m
    slab_dead_kpa = m.concrete_density_kn_m3 * g.slab_thickness_mm / 1000
    girder_dead_kn_m = (
        g.girder_count
        * g.girder_width_mm
        / 1000
        * g.girder_height_mm
        / 1000
        * m.concrete_density_kn_m3
    )
    railing_total_kn_m = loads.railing_left_kn_m + loads.railing_right_kn_m
    permanent_line_by_span = tuple(
        (slab_dead_kpa + item.additional_dead_kpa) * g.deck_width_m
        + girder_dead_kn_m
        + railing_total_kn_m
        for item in loads.spans
    )
    crowd_line_by_span = tuple(item.crowd_kpa * g.deck_width_m for item in loads.spans)
    wind_line_kn_m = loads.wind_pressure_kpa * loads.wind_exposed_height_m
    wind_lever_m = g.deck_elevation_m + loads.wind_exposed_height_m / 2
    railing_torsion_line_kn_m_per_m = (
        loads.railing_right_kn_m - loads.railing_left_kn_m
    ) * g.deck_width_m / 2

    combination_factors = (
        ("ULS-crowd", "ULS", 1.3, 1.5, 0.9),
        ("ULS-wind", "ULS", 1.3, 1.05, 1.5),
        ("SLS-standard", "SLS", 1.0, 1.0, 1.0),
    )
    supports_by_index = {item.node_index: item for item in model.supports}
    combinations: list[RCBridgeCombination] = []
    reactions: list[RCBridgeReactionEnvelope] = []
    analysis_by_combination: dict[str, object] = {}
    unit_distribution = _beam_analysis(
        g.span_count,
        span_mm,
        m.concrete_elastic_modulus_mpa,
        1.0,
        tuple(1.0 for _ in range(g.span_count)),
    )
    unit_total = sum(item.vertical_n for item in unit_distribution.reactions.values())
    unit_weights = {
        index: unit_distribution.reactions[index].vertical_n / unit_total
        for index in range(g.span_count + 1)
    }
    for combination_id, limit_state, permanent_factor, crowd_factor, wind_factor in combination_factors:
        vertical_line = tuple(
            permanent_factor * permanent_line_by_span[index]
            + crowd_factor * crowd_line_by_span[index]
            for index in range(g.span_count)
        )
        girder_analysis = _beam_analysis(
            g.span_count,
            span_mm,
            m.concrete_elastic_modulus_mpa,
            g.girder_width_mm * g.girder_height_mm**3 / 12,
            tuple(value / g.girder_count for value in vertical_line),
        )
        wind_analysis = _beam_analysis(
            g.span_count,
            span_mm,
            m.concrete_elastic_modulus_mpa,
            1.0,
            tuple(wind_factor * wind_line_kn_m for _ in range(g.span_count)),
        )
        applied_vertical = sum(vertical_line) * span_m
        applied_wind = wind_factor * wind_line_kn_m * total_length_m
        applied_wind_moment = applied_wind * wind_lever_m
        applied_torsion = permanent_factor * railing_torsion_line_kn_m_per_m * total_length_m
        combinations.append(
            RCBridgeCombination(
                combination_id,
                limit_state,  # type: ignore[arg-type]
                permanent_factor,
                crowd_factor,
                wind_factor,
                applied_vertical,
                applied_wind,
                applied_wind_moment,
                applied_torsion,
            )
        )
        analysis_by_combination[combination_id] = girder_analysis
        for index in range(g.span_count + 1):
            support = supports_by_index[index]
            vertical_kn = girder_analysis.reactions[index].vertical_n / 1000 * g.girder_count
            wind_kn = wind_analysis.reactions[index].vertical_n / 1000
            reactions.append(
                RCBridgeReactionEnvelope(
                    support=support.id,
                    foundation_type=support.foundation_type,
                    combination_id=combination_id,
                    limit_state=limit_state,  # type: ignore[arg-type]
                    n_kn=vertical_kn,
                    vx_kn=wind_kn,
                    vy_kn=0.0,
                    mx_kn_m=0.0,
                    my_kn_m=wind_kn * wind_lever_m,
                    torsion_kn_m=applied_torsion * unit_weights[index],
                )
            )

    uls_analysis = analysis_by_combination["ULS-crowd"]
    sls_analysis = analysis_by_combination["SLS-standard"]
    max_positive = max(
        response.extrema.moment_max_nmm.value / 1_000_000
        for response in uls_analysis.spans.values()
    )
    max_negative = max(
        0.0,
        max(
            -response.extrema.moment_min_nmm.value / 1_000_000
            for response in uls_analysis.spans.values()
        ),
    )
    max_shear = max(
        max(abs(response.extrema.shear_min_n.value), abs(response.extrema.shear_max_n.value)) / 1000
        for response in uls_analysis.spans.values()
    )
    max_deflection = max(
        response.extrema.deflection_abs_max_mm for response in sls_analysis.spans.values()
    ) / limits.cracked_stiffness_factor

    slab_span_m = g.deck_width_m / (g.girder_count - 1)
    slab_depth = g.slab_thickness_mm - r.cover_mm - r.slab_bar_diameter_mm / 2
    slab_as = pi * r.slab_bar_diameter_mm**2 / 4 * 1000 / r.slab_bar_spacing_mm
    worst_dead_area = slab_dead_kpa + max(item.additional_dead_kpa for item in loads.spans) + railing_total_kn_m / g.deck_width_m
    worst_crowd_area = max(item.crowd_kpa for item in loads.spans)
    slab_uls_q = 1.3 * worst_dead_area + 1.5 * worst_crowd_area
    slab_sls_q = worst_dead_area + worst_crowd_area
    slab_moment = slab_uls_q * slab_span_m**2 / 8
    slab_shear = slab_uls_q * slab_span_m / 2
    slab_moment_capacity = _moment_capacity(
        slab_as, m.rebar_yield_strength_mpa, m.concrete_compressive_strength_mpa, 1000, slab_depth
    )
    slab_shear_capacity = 0.7 * m.concrete_tensile_strength_mpa * 1000 * slab_depth / 1000
    slab_min_as = m.minimum_reinforcement_ratio * 1000 * g.slab_thickness_mm
    slab_max_as = m.maximum_reinforcement_ratio * 1000 * g.slab_thickness_mm
    slab_service_moment = slab_sls_q * slab_span_m**2 / 8
    slab_steel_stress = slab_service_moment * 1_000_000 / (0.87 * slab_as * slab_depth)
    slab_crack = (
        0.2
        * slab_steel_stress
        / 200
        * r.slab_bar_spacing_mm
        / 150
        * r.cover_mm
        / 30
    )
    slab_inertia = 1000 * g.slab_thickness_mm**3 / 12 * limits.cracked_stiffness_factor
    slab_deflection = (
        5
        * slab_sls_q
        * (slab_span_m * 1000) ** 4
        / (384 * m.concrete_elastic_modulus_mpa * slab_inertia)
    )
    slab_checks = (
        _check("桥面板受弯", slab_moment, slab_moment_capacity, "kN*m/m"),
        _check("桥面板受剪", slab_shear, slab_shear_capacity, "kN/m"),
        _check("桥面板最小配筋", slab_min_as, slab_as, "mm2/m"),
        _check("桥面板最大配筋", slab_as, slab_max_as, "mm2/m"),
        _check("桥面板裂缝宽度", slab_crack, limits.crack_width_limit_mm, "mm"),
        _check("桥面板挠度", slab_deflection, slab_span_m * 1000 / limits.slab_deflection_ratio, "mm"),
    )

    girder_depth = g.girder_height_mm - r.cover_mm
    positive_capacity = _moment_capacity(
        r.girder_bottom_area_mm2,
        m.rebar_yield_strength_mpa,
        m.concrete_compressive_strength_mpa,
        g.girder_width_mm,
        girder_depth,
    )
    negative_capacity = _moment_capacity(
        r.girder_top_area_mm2,
        m.rebar_yield_strength_mpa,
        m.concrete_compressive_strength_mpa,
        g.girder_width_mm,
        girder_depth,
    )
    girder_shear_capacity = (
        0.7 * m.concrete_tensile_strength_mpa * g.girder_width_mm * girder_depth
        + r.girder_stirrup_area_mm2
        / r.girder_stirrup_spacing_mm
        * m.rebar_yield_strength_mpa
        * girder_depth
    ) / 1000
    girder_min_as = m.minimum_reinforcement_ratio * g.girder_width_mm * g.girder_height_mm
    girder_max_as = m.maximum_reinforcement_ratio * g.girder_width_mm * g.girder_height_mm
    sls_max_moment = max(
        max(
            abs(response.extrema.moment_min_nmm.value),
            abs(response.extrema.moment_max_nmm.value),
        )
        / 1_000_000
        for response in sls_analysis.spans.values()
    )
    governing_as = min(r.girder_bottom_area_mm2, r.girder_top_area_mm2)
    girder_steel_stress = sls_max_moment * 1_000_000 / (0.87 * governing_as * girder_depth)
    girder_crack = 0.2 * girder_steel_stress / 200 * r.cover_mm / 30
    dead_line_average = sum(permanent_line_by_span) / g.span_count
    line_mass_kg_m = dead_line_average * 1000 / 9.81
    total_girder_inertia_m4 = (
        g.girder_count * g.girder_width_mm * g.girder_height_mm**3 / 12 * 1e-12
    )
    elastic_modulus_pa = m.concrete_elastic_modulus_mpa * 1e6
    frequency = pi / 2 * sqrt(
        elastic_modulus_pa
        * total_girder_inertia_m4
        * limits.cracked_stiffness_factor
        / (line_mass_kg_m * span_m**4)
    )
    girder_checks = (
        _check("RC纵梁正弯矩", max_positive, positive_capacity, "kN*m"),
        _check("RC纵梁负弯矩", max_negative, negative_capacity, "kN*m"),
        _check("RC纵梁受剪", max_shear, girder_shear_capacity, "kN"),
        _check("RC纵梁底筋最小配筋", girder_min_as, r.girder_bottom_area_mm2, "mm2"),
        _check("RC纵梁顶筋最小配筋", girder_min_as, r.girder_top_area_mm2, "mm2"),
        _check("RC纵梁底筋最大配筋", r.girder_bottom_area_mm2, girder_max_as, "mm2"),
        _check("RC纵梁顶筋最大配筋", r.girder_top_area_mm2, girder_max_as, "mm2"),
        _check("RC纵梁裂缝宽度", girder_crack, limits.crack_width_limit_mm, "mm"),
        _check("RC纵梁挠度", max_deflection, span_mm / limits.girder_deflection_ratio, "mm"),
        _check("简化竖向基本频率", limits.minimum_vertical_frequency_hz, frequency, "Hz"),
    )
    screening_passed = all(item.passed for item in slab_checks + girder_checks)
    return RCBridgeResult(
        combinations=tuple(combinations),
        reactions=tuple(reactions),
        slab_checks=slab_checks,
        girder_checks=girder_checks,
        maximum_girder_positive_moment_kn_m=max_positive,
        maximum_girder_negative_moment_kn_m=max_negative,
        maximum_girder_shear_kn=max_shear,
        maximum_girder_deflection_mm=max_deflection,
        estimated_vertical_frequency_hz=frequency,
        screening_passed=screening_passed,
        verification_status="unverified",
        applicability=(
            "直线、单跨或等跨多跨RC板梁人行桥",
            "等截面纵梁、全节点竖向支承、逐跨均布荷载",
            "浅基础或桩基下游六分量反力接口",
        ),
        exclusions=(
            "不覆盖车行、曲线、斜交、预应力、支座非线性和任意桥型",
            "裂缝、开裂刚度和竖向频率均为简化筛查，未完成规范独立验证",
            "基础承载力、墩台构造、抗震、疲劳和水文不在本底座计算",
        ),
    )
