"""Bounded calculation cores for three parameterized landscape-wall systems.

The module deliberately stays independent of the scene/API registry.  It
calculates straight, constant-height representative bays and preserves every
signed wind branch as a complete six-component base reaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Literal

from .errors import CalculationInputError
from .schemas import LoadDirection, Quantity, ReactionEnvelope


LimitState = Literal["ULS", "SLS"]
WallSystem = Literal["cast_in_place_rc", "steel_post_infill", "low_masonry"]


@dataclass(frozen=True)
class WallLoadCase:
    combination_id: str
    combination_name: str
    limit_state: LimitState
    wind_pressure_kpa: float
    additional_dead_load_kpa: float = 0.0


@dataclass(frozen=True)
class CastInPlaceRCWallInput:
    height_m: float
    length_m: float
    thickness_mm: float
    support_spacing_m: float
    opening_ratio: float
    concrete_unit_weight_kn_m3: float
    concrete_fc_mpa: float
    concrete_ft_mpa: float
    rebar_fy_mpa: float
    vertical_rebar_mm2_per_m: float
    horizontal_rebar_mm2_per_m: float
    cover_mm: float
    bar_diameter_mm: float
    load_cases: tuple[WallLoadCase, ...]
    minimum_reinforcement_ratio: float = 0.0015
    slenderness_limit: float = 25.0


@dataclass(frozen=True)
class SteelPostInfillWallInput:
    height_m: float
    length_m: float
    support_spacing_m: float
    opening_ratio: float
    infill_dead_load_kpa: float
    post_self_weight_kn_m: float
    post_area_mm2: float
    post_inertia_mm4: float
    post_section_modulus_mm3: float
    steel_elastic_modulus_mpa: float
    steel_yield_strength_mpa: float
    load_cases: tuple[WallLoadCase, ...]
    effective_length_factor: float = 2.0
    slenderness_limit: float = 150.0
    maximum_post_spacing_m: float = 3.0


@dataclass(frozen=True)
class LowMasonryWallInput:
    height_m: float
    length_m: float
    thickness_mm: float
    support_spacing_m: float
    opening_ratio: float
    masonry_unit_weight_kn_m3: float
    masonry_bending_strength_mpa: float
    masonry_shear_strength_mpa: float
    masonry_compression_strength_mpa: float
    load_cases: tuple[WallLoadCase, ...]
    slenderness_limit: float = 15.0
    minimum_thickness_mm: float = 120.0
    maximum_height_m: float = 1.5


@dataclass(frozen=True)
class SiteWallCheck:
    key: str
    demand: float
    capacity: float
    unit: str
    utilization: float
    passed: bool
    combination_id: str | None
    reference_basis: str


@dataclass(frozen=True)
class WallCombinationDemand:
    combination_id: str
    limit_state: LimitState
    signed_wind_pressure_kpa: float
    axial_kn: float
    shear_kn: float
    moment_kn_m: float
    member_shear_kn: float
    member_moment_kn_m: float
    foundation_line_load_kn_m: float
    reaction: ReactionEnvelope


@dataclass(frozen=True)
class SiteWallResult:
    system: WallSystem
    status: Literal["passed", "failed"]
    verification_status: Literal["unverified"]
    combinations: tuple[WallCombinationDemand, ...]
    checks: tuple[SiteWallCheck, ...]
    governing_check: str
    governing_utilization: float
    foundation_line_load_kn_m: float
    assumptions: tuple[str, ...]
    applicability: tuple[str, ...]
    missing_capabilities: tuple[str, ...]


def _number(value: float, field: str, *, positive: bool = False, non_negative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CalculationInputError("invalid_site_wall_input", f"{field} must be numeric.", field=field) from exc
    if not isfinite(result):
        raise CalculationInputError("invalid_site_wall_input", f"{field} must be finite.", field=field)
    if positive and result <= 0.0:
        raise CalculationInputError("invalid_site_wall_input", f"{field} must be greater than zero.", field=field)
    if non_negative and result < 0.0:
        raise CalculationInputError("invalid_site_wall_input", f"{field} must not be negative.", field=field)
    return result


def _validate_common(
    *, height_m: float, length_m: float, support_spacing_m: float,
    opening_ratio: float, load_cases: tuple[WallLoadCase, ...],
) -> None:
    _number(height_m, "height_m", positive=True)
    _number(length_m, "length_m", positive=True)
    _number(support_spacing_m, "support_spacing_m", positive=True)
    if support_spacing_m > length_m + 1e-12:
        raise CalculationInputError(
            "support_spacing_exceeds_length",
            "support_spacing_m must not exceed the modeled wall length.",
            field="support_spacing_m",
        )
    ratio = _number(opening_ratio, "opening_ratio", non_negative=True)
    if ratio > 0.15:
        raise CalculationInputError(
            "opening_ratio_out_of_scope",
            "Only regular small openings with total ratio not exceeding 0.15 are supported.",
            field="opening_ratio",
            details={"maximum": 0.15},
        )
    if not load_cases:
        raise CalculationInputError("missing_load_cases", "At least one load case is required.", field="load_cases")
    ids: set[str] = set()
    for index, case in enumerate(load_cases):
        if not case.combination_id.strip() or not case.combination_name.strip():
            raise CalculationInputError("missing_combination_identity", "Every load case requires an id and name.", field=f"load_cases.{index}")
        if case.combination_id in ids:
            raise CalculationInputError("duplicate_combination_id", "Load case ids must be unique.", field=f"load_cases.{index}.combination_id")
        ids.add(case.combination_id)
        _number(case.wind_pressure_kpa, f"load_cases.{index}.wind_pressure_kpa")
        _number(case.additional_dead_load_kpa, f"load_cases.{index}.additional_dead_load_kpa", non_negative=True)


def _check(
    key: str, demand: float, capacity: float, unit: str,
    combination_id: str | None, reference_basis: str,
) -> SiteWallCheck:
    if demand < 0.0 or capacity <= 0.0:
        raise CalculationInputError(
            "invalid_site_wall_check", "Check demand must be non-negative and capacity positive.",
            details={"key": key, "demand": demand, "capacity": capacity},
        )
    utilization = demand / capacity
    return SiteWallCheck(
        key=key,
        demand=demand,
        capacity=capacity,
        unit=unit,
        utilization=utilization,
        passed=demand <= capacity * (1.0 + 1e-12),
        combination_id=combination_id,
        reference_basis=reference_basis,
    )


def _direction(pressure: float) -> LoadDirection:
    return LoadDirection.X_NEGATIVE if pressure < 0.0 else LoadDirection.X_POSITIVE


def _reaction(
    *, name: str, case: WallLoadCase, axial_kn: float, shear_kn: float,
    moment_kn_m: float,
) -> ReactionEnvelope:
    return ReactionEnvelope(
        name=name,
        limit_state=case.limit_state,
        combination_id=case.combination_id,
        combination_name=case.combination_name,
        direction=_direction(case.wind_pressure_kpa),
        components={
            "N": Quantity(value=axial_kn, unit="kN"),
            "Vx": Quantity(value=shear_kn, unit="kN"),
            "Vy": Quantity(value=0.0, unit="kN"),
            "Mx": Quantity(value=0.0, unit="kN*m"),
            "My": Quantity(value=moment_kn_m, unit="kN*m"),
            "T": Quantity(value=0.0, unit="kN*m"),
        },
    )


def _finish(
    *, system: WallSystem, combinations: list[WallCombinationDemand],
    checks: list[SiteWallCheck], assumptions: tuple[str, ...],
    applicability: tuple[str, ...], missing: tuple[str, ...],
) -> SiteWallResult:
    governing = max(checks, key=lambda item: item.utilization)
    return SiteWallResult(
        system=system,
        status="passed" if all(item.passed for item in checks) else "failed",
        verification_status="unverified",
        combinations=tuple(combinations),
        checks=tuple(checks),
        governing_check=governing.key,
        governing_utilization=governing.utilization,
        foundation_line_load_kn_m=max(item.foundation_line_load_kn_m for item in combinations),
        assumptions=assumptions,
        applicability=applicability,
        missing_capabilities=missing,
    )


def calculate_cast_in_place_rc_wall(data: CastInPlaceRCWallInput) -> SiteWallResult:
    _validate_common(
        height_m=data.height_m, length_m=data.length_m,
        support_spacing_m=data.support_spacing_m, opening_ratio=data.opening_ratio,
        load_cases=data.load_cases,
    )
    for field in (
        "thickness_mm", "concrete_unit_weight_kn_m3", "concrete_fc_mpa",
        "concrete_ft_mpa", "rebar_fy_mpa", "vertical_rebar_mm2_per_m",
        "horizontal_rebar_mm2_per_m", "cover_mm", "bar_diameter_mm",
        "minimum_reinforcement_ratio", "slenderness_limit",
    ):
        _number(getattr(data, field), field, positive=True)
    depth = data.thickness_mm - data.cover_mm - data.bar_diameter_mm / 2.0
    if depth <= 0.0:
        raise CalculationInputError("invalid_effective_depth", "RC wall effective depth must be positive.", field="thickness_mm")
    solid = 1.0 - data.opening_ratio
    self_line = data.concrete_unit_weight_kn_m3 * data.thickness_mm / 1000.0 * data.height_m * solid
    combinations: list[WallCombinationDemand] = []
    for case in data.load_cases:
        foundation_line = self_line + case.additional_dead_load_kpa * data.height_m * solid
        wind_line = case.wind_pressure_kpa * data.height_m * solid
        wind_moment_per_m = case.wind_pressure_kpa * data.height_m**2 / 2.0 * solid
        axial = foundation_line * data.support_spacing_m
        shear = wind_line * data.support_spacing_m
        moment = wind_moment_per_m * data.support_spacing_m
        combinations.append(
            WallCombinationDemand(
                case.combination_id, case.limit_state, case.wind_pressure_kpa,
                axial, shear, moment, wind_line, wind_moment_per_m, foundation_line,
                _reaction(name="rc_wall_base", case=case, axial_kn=axial, shear_kn=shear, moment_kn_m=moment),
            )
        )
    uls = [item for item in combinations if item.limit_state == "ULS"] or combinations
    governing_m = max(uls, key=lambda item: abs(item.member_moment_kn_m))
    governing_v = max(uls, key=lambda item: abs(item.member_shear_kn))
    x = data.rebar_fy_mpa * data.vertical_rebar_mm2_per_m / (data.concrete_fc_mpa * 1000.0)
    flexural_capacity = data.rebar_fy_mpa * data.vertical_rebar_mm2_per_m * (depth - min(x, 0.45 * depth) / 2.0) / 1.0e6
    shear_capacity = 0.7 * data.concrete_ft_mpa * 1000.0 * depth / 1000.0
    minimum_area = data.minimum_reinforcement_ratio * 1000.0 * data.thickness_mm
    slenderness = data.height_m * 1000.0 / data.thickness_mm
    checks = [
        _check("rc_wall_flexure", abs(governing_m.member_moment_kn_m), flexural_capacity, "kN*m/m", governing_m.combination_id, "cantilever strip; candidate GB/T 50010 mapping"),
        _check("rc_wall_shear", abs(governing_v.member_shear_kn), shear_capacity, "kN/m", governing_v.combination_id, "one-metre RC strip shear screening"),
        _check("rc_vertical_minimum_reinforcement", minimum_area, data.vertical_rebar_mm2_per_m, "mm2/m", None, "project minimum ratio pending exact clause review"),
        _check("rc_horizontal_minimum_reinforcement", minimum_area, data.horizontal_rebar_mm2_per_m, "mm2/m", None, "project minimum ratio pending exact clause review"),
        _check("rc_wall_slenderness", slenderness, data.slenderness_limit, "1", None, "bounded landscape-wall applicability"),
    ]
    return _finish(
        system="cast_in_place_rc", combinations=combinations, checks=checks,
        assumptions=("one-metre vertical cantilever strips", "regular openings reduce tributary action area only", "wall and finish self-weight enter each combination once"),
        applicability=("straight constant-height cast-in-place RC landscape walls", "opening ratio <= 0.15", "static positive and negative wind"),
        missing=("crack width and long-term deformation", "base anchorage and foundation resistance", "seismic and temperature actions", "irregular opening stress concentration"),
    )


def calculate_steel_post_infill_wall(data: SteelPostInfillWallInput) -> SiteWallResult:
    _validate_common(
        height_m=data.height_m, length_m=data.length_m,
        support_spacing_m=data.support_spacing_m, opening_ratio=data.opening_ratio,
        load_cases=data.load_cases,
    )
    for field in (
        "infill_dead_load_kpa", "post_self_weight_kn_m", "post_area_mm2",
        "post_inertia_mm4", "post_section_modulus_mm3", "steel_elastic_modulus_mpa",
        "steel_yield_strength_mpa", "effective_length_factor", "slenderness_limit",
        "maximum_post_spacing_m",
    ):
        _number(getattr(data, field), field, positive=True)
    solid = 1.0 - data.opening_ratio
    combinations: list[WallCombinationDemand] = []
    for case in data.load_cases:
        infill_line = (data.infill_dead_load_kpa + case.additional_dead_load_kpa) * data.height_m * solid
        foundation_line = infill_line + data.post_self_weight_kn_m * data.height_m / data.support_spacing_m
        axial = infill_line * data.support_spacing_m + data.post_self_weight_kn_m * data.height_m
        post_line_wind = case.wind_pressure_kpa * data.support_spacing_m * solid
        shear = post_line_wind * data.height_m
        moment = post_line_wind * data.height_m**2 / 2.0
        combinations.append(
            WallCombinationDemand(
                case.combination_id, case.limit_state, case.wind_pressure_kpa,
                axial, shear, moment, shear, moment, foundation_line,
                _reaction(name="steel_post_base", case=case, axial_kn=axial, shear_kn=shear, moment_kn_m=moment),
            )
        )
    uls = [item for item in combinations if item.limit_state == "ULS"] or combinations
    governing_m = max(uls, key=lambda item: abs(item.member_moment_kn_m))
    governing_v = max(uls, key=lambda item: abs(item.member_shear_kn))
    governing_n = max(uls, key=lambda item: item.axial_kn)
    radius = sqrt(data.post_inertia_mm4 / data.post_area_mm2)
    slenderness = data.effective_length_factor * data.height_m * 1000.0 / radius
    euler = pi**2 * data.steel_elastic_modulus_mpa * data.post_inertia_mm4 / (data.effective_length_factor * data.height_m * 1000.0) ** 2 / 1000.0
    squash = data.steel_yield_strength_mpa * data.post_area_mm2 / 1000.0
    checks = [
        _check("steel_post_flexure", abs(governing_m.member_moment_kn_m), data.steel_yield_strength_mpa * data.post_section_modulus_mm3 / 1.0e6, "kN*m", governing_m.combination_id, "elastic section screening"),
        _check("steel_post_shear", abs(governing_v.member_shear_kn), 0.6 * data.steel_yield_strength_mpa * data.post_area_mm2 / 1000.0, "kN", governing_v.combination_id, "gross-area shear screening"),
        _check("steel_post_axial_stability", governing_n.axial_kn, min(euler, squash), "kN", governing_n.combination_id, "Euler/yield upper-bound screening"),
        _check("steel_post_slenderness", slenderness, data.slenderness_limit, "1", None, "bounded post slenderness"),
        _check("steel_post_spacing", data.support_spacing_m, data.maximum_post_spacing_m, "m", None, "declared infill support-spacing limit"),
    ]
    return _finish(
        system="steel_post_infill", combinations=combinations, checks=checks,
        assumptions=("each post receives one support-spacing tributary width", "infill is non-loadbearing and transfers wind to posts", "post base is fixed for member demand"),
        applicability=("straight constant-height steel-post light-infill walls", "opening ratio <= 0.15", "static positive and negative wind"),
        missing=("infill panel local resistance", "post-base plate, anchors and foundation", "combined axial-bending stability curve", "connections, fatigue, corrosion and seismic actions"),
    )


def calculate_low_masonry_wall(data: LowMasonryWallInput) -> SiteWallResult:
    _validate_common(
        height_m=data.height_m, length_m=data.length_m,
        support_spacing_m=data.support_spacing_m, opening_ratio=data.opening_ratio,
        load_cases=data.load_cases,
    )
    for field in (
        "thickness_mm", "masonry_unit_weight_kn_m3", "masonry_bending_strength_mpa",
        "masonry_shear_strength_mpa", "masonry_compression_strength_mpa",
        "slenderness_limit", "minimum_thickness_mm", "maximum_height_m",
    ):
        _number(getattr(data, field), field, positive=True)
    solid = 1.0 - data.opening_ratio
    self_line = data.masonry_unit_weight_kn_m3 * data.thickness_mm / 1000.0 * data.height_m * solid
    combinations: list[WallCombinationDemand] = []
    for case in data.load_cases:
        foundation_line = self_line + case.additional_dead_load_kpa * data.height_m * solid
        wind_line = case.wind_pressure_kpa * data.height_m * solid
        wind_moment = case.wind_pressure_kpa * data.height_m**2 / 2.0 * solid
        axial = foundation_line * data.support_spacing_m
        shear = wind_line * data.support_spacing_m
        moment = wind_moment * data.support_spacing_m
        combinations.append(
            WallCombinationDemand(
                case.combination_id, case.limit_state, case.wind_pressure_kpa,
                axial, shear, moment, wind_line, wind_moment, foundation_line,
                _reaction(name="masonry_wall_base", case=case, axial_kn=axial, shear_kn=shear, moment_kn_m=moment),
            )
        )
    uls = [item for item in combinations if item.limit_state == "ULS"] or combinations
    governing_m = max(uls, key=lambda item: abs(item.member_moment_kn_m))
    governing_v = max(uls, key=lambda item: abs(item.member_shear_kn))
    governing_n = max(uls, key=lambda item: item.axial_kn)
    section_modulus = 1000.0 * data.thickness_mm**2 / 6.0
    gross_area = 1000.0 * data.thickness_mm
    slenderness = max(data.height_m, data.support_spacing_m) * 1000.0 / data.thickness_mm
    checks = [
        _check("masonry_wall_flexure", abs(governing_m.member_moment_kn_m), data.masonry_bending_strength_mpa * section_modulus / 1.0e6, "kN*m/m", governing_m.combination_id, "vertical cantilever strip screening"),
        _check("masonry_wall_shear", abs(governing_v.member_shear_kn), data.masonry_shear_strength_mpa * gross_area / 1000.0, "kN/m", governing_v.combination_id, "gross-section shear screening"),
        _check("masonry_wall_compression", governing_n.foundation_line_load_kn_m, data.masonry_compression_strength_mpa * data.thickness_mm, "kN/m", governing_n.combination_id, "uniform base compression per metre"),
        _check("masonry_wall_slenderness", slenderness, data.slenderness_limit, "1", None, "bounded low-wall applicability"),
        _check("masonry_minimum_thickness", data.minimum_thickness_mm, data.thickness_mm, "mm", None, "declared minimum construction thickness"),
        _check("masonry_maximum_height", data.height_m, data.maximum_height_m, "m", None, "declared unsupported low-wall height limit"),
    ]
    return _finish(
        system="low_masonry", combinations=combinations, checks=checks,
        assumptions=("one-metre vertical cantilever strips", "regular small openings reduce tributary action area", "no passive resistance or hidden RC confinement is credited"),
        applicability=("straight constant-height low unreinforced masonry landscape walls", "opening ratio <= 0.15", "static positive and negative wind"),
        missing=("seismic and accidental action", "local opening lintel/jamb checks", "foundation and differential settlement", "moisture, durability and material-specific detailing"),
    )
