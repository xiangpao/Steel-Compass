from __future__ import annotations

from enum import Enum
from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import ENGINE_VERSION, SCHEMA_VERSION, STANDARD_PROFILE


class CalculationMode(str, Enum):
    QUICK = "quick"
    PROFESSIONAL = "professional"


class CalculationModule(str, Enum):
    STEEL_BEAM = "steel_beam"
    STEEL_COLUMN = "steel_column"
    PORTAL_FRAME = "portal_frame"
    CONCRETE_BEAM = "concrete_beam"
    CONCRETE_SLAB = "concrete_slab"
    CONCRETE_COLUMN = "concrete_column"
    SPREAD_FOOTING = "spread_footing"
    STRIP_FOOTING = "strip_footing"
    TIMBER_BEAM = "timber_beam"
    TIMBER_COLUMN = "timber_column"
    STEEL_BASEPLATE_ANCHOR = "steel_baseplate_anchor"
    TIMBER_DECK_PANEL = "timber_deck_panel"
    STEEL_CANTILEVER_POST = "steel_cantilever_post"
    MASONRY_WALL = "masonry_wall"
    RC_WALL = "rc_wall"
    RETAINING_WALL = "retaining_wall"
    CONTINUOUS_BEAM = "continuous_beam"
    PLANAR_FRAME = "planar_frame"
    PLANAR_TRUSS = "planar_truss"
    TWO_WAY_SLAB = "two_way_slab"
    TIMBER_CONNECTION = "timber_connection"
    WALL_ANCHOR = "wall_anchor"
    POOL_STRUCTURE = "pool_structure"
    PILE_GROUP_CAP = "pile_group_cap"
    BRIDGE_STEEL_TIMBER = "bridge_steel_timber"
    BRIDGE_RC = "bridge_rc"
    GRAVITY_RETAINING_WALL = "gravity_retaining_wall"
    SITE_RC_WALL = "site_rc_wall"
    STEEL_INFILL_WALL = "steel_infill_wall"
    PLAIN_MASONRY_WALL = "plain_masonry_wall"
    LOAD_COMBINATIONS = "load_combinations"
    WIND_SNOW_GUIDE = "wind_snow_guide"
    SOIL_WATER_ACTIONS = "soil_water_actions"


class LoadKind(str, Enum):
    SELF_WEIGHT = "self_weight"
    DEAD = "dead"
    LIVE = "live"
    WIND = "wind"
    SNOW = "snow"


class LoadDirection(str, Enum):
    GRAVITY = "gravity"
    UPLIFT = "uplift"
    X_POSITIVE = "x_positive"
    X_NEGATIVE = "x_negative"
    Y_POSITIVE = "y_positive"
    Y_NEGATIVE = "y_negative"


class Quantity(BaseModel):
    value: float
    unit: str


class TypedInputValue(BaseModel):
    """Schema 3.1 numeric input at the API boundary.

    Legacy calculations still consume ``inputs`` internally.  The adapter
    below converts these values while preserving their declared units for
    validation and reporting.
    """

    value: float
    unit: str = Field(min_length=1, max_length=24)

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("typed input value 必须是有限数值")
        return value

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("typed input unit 不能为空")
        return normalized


class TypedModuleInputs(BaseModel):
    """Compatibility adapter for existing Schema 3.2 calculation modules."""

    module: Literal[
        CalculationModule.STEEL_BEAM,
        CalculationModule.STEEL_COLUMN,
        CalculationModule.PORTAL_FRAME,
        CalculationModule.CONCRETE_BEAM,
        CalculationModule.CONCRETE_SLAB,
        CalculationModule.CONCRETE_COLUMN,
        CalculationModule.SPREAD_FOOTING,
        CalculationModule.STRIP_FOOTING,
        CalculationModule.TIMBER_BEAM,
        CalculationModule.TIMBER_COLUMN,
        CalculationModule.STEEL_BASEPLATE_ANCHOR,
        CalculationModule.TIMBER_DECK_PANEL,
        CalculationModule.STEEL_CANTILEVER_POST,
        CalculationModule.MASONRY_WALL,
        CalculationModule.RC_WALL,
        CalculationModule.RETAINING_WALL,
    ]
    values: dict[str, TypedInputValue | str | bool] = Field(default_factory=dict)


class AnalysisCombinationInput(BaseModel):
    combination_id: str = Field(min_length=1, max_length=80)
    combination_name: str = Field(min_length=1, max_length=120)
    limit_state: Literal["ULS", "SLS"] = "ULS"


class BeamSpanInput(BaseModel):
    id: str
    start: str
    end: str
    length: TypedInputValue
    elastic_modulus: TypedInputValue
    inertia: TypedInputValue
    uniform_load_local_y: TypedInputValue
    moment_capacity: TypedInputValue
    shear_capacity: TypedInputValue


class BeamSupportInput(BaseModel):
    node: str
    vertical: bool = True
    rotation: bool = False


class BeamNodalLoadInput(BaseModel):
    node: str
    force_y: TypedInputValue
    moment_z: TypedInputValue


class ContinuousBeamInputs(AnalysisCombinationInput):
    module: Literal[CalculationModule.CONTINUOUS_BEAM]
    nodes: list[str] = Field(min_length=2)
    spans: list[BeamSpanInput] = Field(min_length=1)
    supports: list[BeamSupportInput] = Field(min_length=1)
    nodal_loads: list[BeamNodalLoadInput] = Field(default_factory=list)
    deflection_limit: TypedInputValue


class FrameNodeInput(BaseModel):
    id: str
    x: TypedInputValue
    y: TypedInputValue


class FrameMemberInput(BaseModel):
    id: str
    start: str
    end: str
    area: TypedInputValue
    inertia: TypedInputValue
    elastic_modulus: TypedInputValue
    axial_capacity: TypedInputValue
    shear_capacity: TypedInputValue
    moment_capacity: TypedInputValue


class FrameRestraintInput(BaseModel):
    node: str
    ux: bool = False
    uy: bool = False
    rz: bool = False


class FrameNodalLoadInput(BaseModel):
    node: str
    force_x: TypedInputValue
    force_y: TypedInputValue
    moment_z: TypedInputValue


class FrameUniformLoadInput(BaseModel):
    member: str
    local_y: TypedInputValue


class PlanarFrameInputs(AnalysisCombinationInput):
    module: Literal[CalculationModule.PLANAR_FRAME]
    nodes: list[FrameNodeInput] = Field(min_length=2)
    members: list[FrameMemberInput] = Field(min_length=1)
    restraints: list[FrameRestraintInput] = Field(min_length=1)
    nodal_loads: list[FrameNodalLoadInput] = Field(default_factory=list)
    uniform_loads: list[FrameUniformLoadInput] = Field(default_factory=list)
    displacement_limit: TypedInputValue


class TrussMemberInput(BaseModel):
    id: str
    start: str
    end: str
    area: TypedInputValue
    elastic_modulus: TypedInputValue
    axial_capacity: TypedInputValue


class TrussRestraintInput(BaseModel):
    node: str
    ux: bool = False
    uy: bool = False


class TrussNodalLoadInput(BaseModel):
    node: str
    force_x: TypedInputValue
    force_y: TypedInputValue


class PlanarTrussInputs(AnalysisCombinationInput):
    module: Literal[CalculationModule.PLANAR_TRUSS]
    nodes: list[FrameNodeInput] = Field(min_length=2)
    members: list[TrussMemberInput] = Field(min_length=1)
    restraints: list[TrussRestraintInput] = Field(min_length=1)
    nodal_loads: list[TrussNodalLoadInput] = Field(default_factory=list)
    displacement_limit: TypedInputValue


class TwoWaySlabInputs(AnalysisCombinationInput):
    module: Literal[CalculationModule.TWO_WAY_SLAB]
    short_span: TypedInputValue
    long_span: TypedInputValue
    thickness: TypedInputValue
    elastic_modulus: TypedInputValue
    uniform_load: TypedInputValue
    support_condition: Literal[
        "four_edges_simply_supported", "four_edges_fixed"
    ]
    poisson_ratio: float = Field(default=0.2, ge=0, lt=0.5)
    short_direction_moment_capacity: TypedInputValue
    long_direction_moment_capacity: TypedInputValue
    deflection_limit: TypedInputValue


class ConnectionEffectInput(AnalysisCombinationInput):
    axial: TypedInputValue
    shear_x: TypedInputValue
    shear_y: TypedInputValue
    moment_x: TypedInputValue
    moment_y: TypedInputValue
    torsion: TypedInputValue


class ConnectionPositionInput(BaseModel):
    x: TypedInputValue
    y: TypedInputValue


class TimberConnectionInputs(BaseModel):
    module: Literal[CalculationModule.TIMBER_CONNECTION]
    post_width: TypedInputValue
    post_depth: TypedInputValue
    plate_width: TypedInputValue
    plate_depth: TypedInputValue
    fastener_diameter: TypedInputValue
    fastener_positions: list[ConnectionPositionInput] = Field(min_length=2)
    connector_standoff: TypedInputValue
    effects: list[ConnectionEffectInput] = Field(min_length=1)
    bearing_design_capacity: TypedInputValue | None = None
    fastener_tension_design_capacity: TypedInputValue | None = None
    fastener_shear_design_capacity: TypedInputValue | None = None
    connector_bending_design_capacity: TypedInputValue | None = None
    timber_compression_design_strength: TypedInputValue | None = None
    timber_withdrawal_design_strength: TypedInputValue | None = None
    timber_shear_design_strength: TypedInputValue | None = None
    embedment_length: TypedInputValue | None = None
    fastener_fu: TypedInputValue | None = None
    connector_bending_strength: TypedInputValue | None = None
    connector_section_modulus: TypedInputValue | None = None
    minimum_spacing: TypedInputValue | None = None
    minimum_edge_distance: TypedInputValue | None = None


class WallAnchorInputs(BaseModel):
    module: Literal[CalculationModule.WALL_ANCHOR]
    plate_width: TypedInputValue
    plate_height: TypedInputValue
    plate_thickness: TypedInputValue
    rebar_count: TypedInputValue
    rebar_rows: TypedInputValue
    rebar_diameter: TypedInputValue
    rebar_fy: TypedInputValue
    rebar_length: TypedInputValue
    bent_rebar_count: TypedInputValue | None = None
    bent_rebar_diameter: TypedInputValue | None = None
    bent_rebar_angle: TypedInputValue | None = None
    concrete_fc: TypedInputValue
    concrete_ft: TypedInputValue
    edge_distance_x: TypedInputValue
    edge_distance_y: TypedInputValue
    n_design: TypedInputValue
    m_design: TypedInputValue
    v_design: TypedInputValue


class PoolGeometryInputs(BaseModel):
    inside_length: TypedInputValue
    inside_width: TypedInputValue
    wall_height: TypedInputValue
    wall_thickness: TypedInputValue
    base_thickness: TypedInputValue
    base_projection: TypedInputValue
    retained_soil_height: TypedInputValue
    wall_horizontal_span: TypedInputValue | None = None


class PoolMaterialInputs(BaseModel):
    concrete_unit_weight: TypedInputValue
    water_unit_weight: TypedInputValue
    soil_unit_weight: TypedInputValue
    soil_friction_angle: TypedInputValue
    surcharge: TypedInputValue
    allowable_bearing: TypedInputValue
    concrete_fc: TypedInputValue
    concrete_ft: TypedInputValue
    rebar_fy: TypedInputValue
    rebar_es: TypedInputValue


class PoolReinforcementInputs(BaseModel):
    wall_vertical_as: TypedInputValue
    wall_horizontal_as: TypedInputValue
    base_x_as: TypedInputValue
    base_y_as: TypedInputValue
    wall_bar_diameter: TypedInputValue
    base_bar_diameter: TypedInputValue
    wall_cover: TypedInputValue
    base_cover: TypedInputValue
    minimum_reinforcement_ratio: TypedInputValue
    crack_width_limit: TypedInputValue


class PoolWaterLevelInputs(BaseModel):
    full_internal_depth: TypedInputValue
    empty_external_head: TypedInputValue
    full_external_head: TypedInputValue | None = None


class PoolStructureInputs(BaseModel):
    module: Literal[CalculationModule.POOL_STRUCTURE]
    geometry: PoolGeometryInputs
    materials: PoolMaterialInputs
    reinforcement: PoolReinforcementInputs
    water_levels: PoolWaterLevelInputs
    additional_ballast: TypedInputValue
    antifloat_factor: TypedInputValue


class PileDefinitionInput(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    x: TypedInputValue
    y: TypedInputValue
    diameter_or_side: TypedInputValue
    pile_type: Literal["bored", "precast_pipe", "precast_square"]


class InvestigatedPileCapacityInputs(BaseModel):
    compression: TypedInputValue
    uplift: TypedInputValue
    horizontal: TypedInputValue
    source: str = Field(min_length=1, max_length=240)


class PileCapGeometryInputs(BaseModel):
    length_x: TypedInputValue
    width_y: TypedInputValue
    thickness: TypedInputValue
    column_x: TypedInputValue
    column_y: TypedInputValue
    cover: TypedInputValue
    bar_diameter: TypedInputValue


class PileCapMaterialInputs(BaseModel):
    concrete_ft: TypedInputValue
    rebar_fy: TypedInputValue
    provided_rebar_x: TypedInputValue
    provided_rebar_y: TypedInputValue
    minimum_reinforcement_ratio: TypedInputValue


class SixComponentEffectInputs(BaseModel):
    axial: TypedInputValue
    shear_x: TypedInputValue
    shear_y: TypedInputValue
    moment_x: TypedInputValue
    moment_y: TypedInputValue
    torsion: TypedInputValue


class PileGroupCapInputs(AnalysisCombinationInput):
    module: Literal[CalculationModule.PILE_GROUP_CAP]
    piles: list[PileDefinitionInput] = Field(min_length=3)
    capacities: InvestigatedPileCapacityInputs
    cap: PileCapGeometryInputs
    material: PileCapMaterialInputs
    effects: SixComponentEffectInputs


class BridgeGeometryInputs(BaseModel):
    span_count: TypedInputValue
    span_length: TypedInputValue
    deck_width: TypedInputValue
    crossbeam_spacing: TypedInputValue
    longitudinal_girder_count: TypedInputValue


class BridgeActionInputs(BaseModel):
    crowd_load: TypedInputValue
    additional_dead_load: TypedInputValue
    railing_dead_load_per_side: TypedInputValue
    wind_line_load: TypedInputValue
    span_live_load_factors: list[TypedInputValue] | None = None


class TimberDeckInputs(BaseModel):
    thickness: TypedInputValue
    elastic_modulus: TypedInputValue
    bending_strength: TypedInputValue
    shear_strength: TypedInputValue
    unit_weight: TypedInputValue
    deflection_limit_ratio: TypedInputValue


class SteelBridgeSectionInputs(BaseModel):
    area: TypedInputValue
    inertia: TypedInputValue
    section_modulus: TypedInputValue
    shear_area: TypedInputValue
    yield_strength: TypedInputValue
    elastic_modulus: TypedInputValue
    unit_weight: TypedInputValue


class BridgeComfortInputs(BaseModel):
    damping_ratio: TypedInputValue
    walking_frequency: TypedInputValue
    pedestrian_dynamic_force: TypedInputValue
    acceleration_limit: TypedInputValue


class BridgeSteelTimberInputs(BaseModel):
    module: Literal[CalculationModule.BRIDGE_STEEL_TIMBER]
    geometry: BridgeGeometryInputs
    actions: BridgeActionInputs
    timber_deck: TimberDeckInputs
    crossbeam_section: SteelBridgeSectionInputs
    longitudinal_section: SteelBridgeSectionInputs
    comfort: BridgeComfortInputs
    foundation_types: list[Literal["shallow", "pile"]] | None = None


class RCBridgeGeometryInputs(BaseModel):
    span_count: TypedInputValue
    span_length: TypedInputValue
    deck_width: TypedInputValue
    deck_elevation: TypedInputValue
    slab_thickness: TypedInputValue
    girder_count: TypedInputValue
    girder_width: TypedInputValue
    girder_height: TypedInputValue


class RCBridgeMaterialInputs(BaseModel):
    concrete_elastic_modulus: TypedInputValue
    concrete_compressive_strength: TypedInputValue
    concrete_tensile_strength: TypedInputValue
    rebar_yield_strength: TypedInputValue
    concrete_density: TypedInputValue
    minimum_reinforcement_ratio: TypedInputValue
    maximum_reinforcement_ratio: TypedInputValue


class RCBridgeReinforcementInputs(BaseModel):
    cover: TypedInputValue
    slab_bar_diameter: TypedInputValue
    slab_bar_spacing: TypedInputValue
    girder_bottom_area: TypedInputValue
    girder_top_area: TypedInputValue
    girder_stirrup_area: TypedInputValue
    girder_stirrup_spacing: TypedInputValue


class RCBridgeSpanLoadInputs(BaseModel):
    additional_dead: TypedInputValue
    crowd: TypedInputValue


class RCBridgeLoadInputs(BaseModel):
    spans: list[RCBridgeSpanLoadInputs] = Field(min_length=1)
    railing_left: TypedInputValue
    railing_right: TypedInputValue
    wind_pressure: TypedInputValue
    wind_exposed_height: TypedInputValue


class RCBridgeSupportInputs(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    node_index: TypedInputValue
    foundation_type: Literal["shallow", "pile"]


class RCBridgeServiceLimitInputs(BaseModel):
    crack_width_limit: TypedInputValue
    minimum_vertical_frequency: TypedInputValue
    slab_deflection_ratio: TypedInputValue
    girder_deflection_ratio: TypedInputValue
    cracked_stiffness_factor: TypedInputValue


class BridgeRCInputs(BaseModel):
    module: Literal[CalculationModule.BRIDGE_RC]
    geometry: RCBridgeGeometryInputs
    material: RCBridgeMaterialInputs
    reinforcement: RCBridgeReinforcementInputs
    loads: RCBridgeLoadInputs
    supports: list[RCBridgeSupportInputs] = Field(min_length=2)
    service_limits: RCBridgeServiceLimitInputs


class GravityRetainingWallInputs(AnalysisCombinationInput):
    module: Literal[CalculationModule.GRAVITY_RETAINING_WALL]
    retained_height: TypedInputValue
    base_width: TypedInputValue
    base_slab_thickness: TypedInputValue
    wall_bottom_thickness: TypedInputValue
    wall_top_thickness: TypedInputValue
    toe_projection: TypedInputValue
    wall_unit_weight: TypedInputValue
    soil_unit_weight: TypedInputValue
    soil_friction_angle: TypedInputValue
    surcharge: TypedInputValue
    base_friction_coefficient: TypedInputValue
    soil_bearing_capacity: TypedInputValue
    material_compressive_design: TypedInputValue
    water_depth_behind: TypedInputValue
    water_unit_weight: TypedInputValue
    uplift_head_toe: TypedInputValue
    uplift_head_heel: TypedInputValue
    sliding_safety_factor: TypedInputValue
    overturning_safety_factor: TypedInputValue


class SiteWallLoadCaseInputs(AnalysisCombinationInput):
    wind_pressure: TypedInputValue
    additional_dead_load: TypedInputValue


class SiteRCWallInputs(BaseModel):
    module: Literal[CalculationModule.SITE_RC_WALL]
    height: TypedInputValue
    length: TypedInputValue
    thickness: TypedInputValue
    support_spacing: TypedInputValue
    opening_ratio: TypedInputValue
    concrete_unit_weight: TypedInputValue
    concrete_fc: TypedInputValue
    concrete_ft: TypedInputValue
    rebar_fy: TypedInputValue
    vertical_rebar: TypedInputValue
    horizontal_rebar: TypedInputValue
    cover: TypedInputValue
    bar_diameter: TypedInputValue
    minimum_reinforcement_ratio: TypedInputValue
    slenderness_limit: TypedInputValue
    load_cases: list[SiteWallLoadCaseInputs] = Field(min_length=1)


class SteelInfillWallInputs(BaseModel):
    module: Literal[CalculationModule.STEEL_INFILL_WALL]
    height: TypedInputValue
    length: TypedInputValue
    support_spacing: TypedInputValue
    opening_ratio: TypedInputValue
    infill_dead_load: TypedInputValue
    post_self_weight: TypedInputValue
    post_area: TypedInputValue
    post_inertia: TypedInputValue
    post_section_modulus: TypedInputValue
    steel_elastic_modulus: TypedInputValue
    steel_yield_strength: TypedInputValue
    effective_length_factor: TypedInputValue
    slenderness_limit: TypedInputValue
    maximum_post_spacing: TypedInputValue
    load_cases: list[SiteWallLoadCaseInputs] = Field(min_length=1)


class PlainMasonryWallInputs(BaseModel):
    module: Literal[CalculationModule.PLAIN_MASONRY_WALL]
    height: TypedInputValue
    length: TypedInputValue
    thickness: TypedInputValue
    support_spacing: TypedInputValue
    opening_ratio: TypedInputValue
    masonry_unit_weight: TypedInputValue
    masonry_bending_strength: TypedInputValue
    masonry_shear_strength: TypedInputValue
    masonry_compression_strength: TypedInputValue
    slenderness_limit: TypedInputValue
    minimum_thickness: TypedInputValue
    maximum_height: TypedInputValue
    load_cases: list[SiteWallLoadCaseInputs] = Field(min_length=1)


class LoadCombinationCaseInputs(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    category: Literal[
        "permanent", "live", "wind", "snow", "soil", "water", "buoyancy"
    ]
    characteristic: TypedInputValue
    direction: Literal[
        "gravity",
        "uplift",
        "x_positive",
        "x_negative",
        "y_positive",
        "y_negative",
    ]
    distribution: Literal["point", "line", "area", "pressure"]
    target: str = Field(min_length=1, max_length=120)
    source_reference: str = Field(min_length=1, max_length=240)
    exclusive_group: str | None = None
    permanent_role: Literal["auto", "favorable", "unfavorable"] = "auto"
    psi0: TypedInputValue | None = None
    psi1: TypedInputValue | None = None
    psi2: TypedInputValue | None = None


class LoadCombinationsInputs(BaseModel):
    module: Literal[CalculationModule.LOAD_COMBINATIONS]
    cases: list[LoadCombinationCaseInputs] = Field(min_length=1)


class WindSnowGuideInputs(BaseModel):
    module: Literal[CalculationModule.WIND_SNOW_GUIDE]
    basic_wind_pressure: TypedInputValue
    wind_source_reference: str = Field(min_length=1, max_length=240)
    recurrence_period: TypedInputValue
    recurrence_factor: TypedInputValue
    terrain_roughness: Literal["A", "B", "C", "D"]
    terrain_height_factor: TypedInputValue
    shape_coefficient_positive: TypedInputValue
    shape_coefficient_negative: TypedInputValue
    wind_area: TypedInputValue
    snow_applicability: Literal["applicable", "not_applicable"]
    basic_snow_pressure: TypedInputValue | None = None
    snow_source_reference: str | None = None
    roof_snow_coefficient: TypedInputValue | None = None
    snow_area: TypedInputValue | None = None
    no_snow_basis: str | None = None
    target: str = Field(min_length=1, max_length=120)


class SoilWaterActionsInputs(BaseModel):
    module: Literal[CalculationModule.SOIL_WATER_ACTIONS]
    wall_height: TypedInputValue
    earth_pressure_state: Literal["active", "at_rest"]
    soil_unit_weight_dry: TypedInputValue
    soil_unit_weight_saturated: TypedInputValue
    soil_friction_angle: TypedInputValue
    surcharge: TypedInputValue
    groundwater_depth_below_top: TypedInputValue
    water_unit_weight: TypedInputValue
    internal_water_depth: TypedInputValue
    external_water_depth: TypedInputValue | None = None
    base_area: TypedInputValue
    at_rest_coefficient: TypedInputValue | None = None
    source_reference: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=120)


DiscriminatedTypedInputs = Annotated[
    TypedModuleInputs
    | ContinuousBeamInputs
    | PlanarFrameInputs
    | PlanarTrussInputs
    | TwoWaySlabInputs
    | TimberConnectionInputs
    | WallAnchorInputs
    | PoolStructureInputs
    | PileGroupCapInputs
    | BridgeSteelTimberInputs
    | BridgeRCInputs
    | GravityRetainingWallInputs
    | SiteRCWallInputs
    | SteelInfillWallInputs
    | PlainMasonryWallInputs
    | LoadCombinationsInputs
    | WindSnowGuideInputs
    | SoilWaterActionsInputs,
    Field(discriminator="module"),
]


def _canonical_unit(unit: str) -> str:
    return (
        unit.strip()
        .replace("²", "2")
        .replace("³", "3")
        .replace("·", ".")
        .replace("，", ".")
        .lower()
    )


def _expected_unit_for_input(key: str) -> set[str] | None:
    """Infer only unambiguous units from public 3.1 input key suffixes."""

    suffix_units = (
        ("_kn_m_per_m", {"kn.m/m", "kn/m*m"}),
        ("_kn_m2", {"kn/m2"}),
        ("_kn_m3", {"kn/m3"}),
        ("_mm4", {"mm4"}),
        ("_m2", {"m2"}),
        ("_m3", {"m3"}),
        ("_kpa", {"kpa"}),
        ("_mpa", {"mpa"}),
        ("_kn_m", {"kn.m"}),
        ("_kn", {"kn"}),
        ("_mm", {"mm"}),
        ("_m", {"m"}),
        ("_deg", {"deg", "°"}),
    )
    for suffix, units in suffix_units:
        if key.lower().endswith(suffix):
            return units
    return None


class LoadItem(BaseModel):
    kind: LoadKind
    value: float = Field(ge=0)
    unit: Literal["kN/m", "kN/m2", "kN"]
    source: str = Field(min_length=1, max_length=240)
    direction: LoadDirection = LoadDirection.GRAVITY
    preset_id: str | None = None
    source_reference: str | None = None
    override_reason: str | None = None


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    mode: CalculationMode
    module: CalculationModule
    project_name: str = Field(default="未命名项目", min_length=1, max_length=120)
    # CN-2024 remains accepted only so saved requests can be parsed without
    # rewriting their original standard basis. New requests default to the
    # versioned, officially reviewed CN-2026.1 profile.
    standard_profile: Literal["CN-2026.1", "CN-2024"] = STANDARD_PROFILE
    # Read compatibility for 3.1 and earlier saved requests. Schema 3.2 clients
    # do not send this field and calculation readiness no longer depends on it.
    confirmed_assumptions: bool | None = Field(default=None, exclude=True)
    typed_inputs: DiscriminatedTypedInputs | None = None
    # Compatibility read path for schema 3.0 and earlier snapshots. New
    # clients should send typed_inputs; the engine normalizes both forms.
    inputs: dict[str, Any] = Field(default_factory=dict)
    loads: list[LoadItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "CalculationRequest":
        if isinstance(self.typed_inputs, TypedModuleInputs):
            if self.typed_inputs.module is not self.module:
                raise ValueError("typed_inputs.module 必须与 module 一致")
            normalized: dict[str, Any] = {}
            for key, value in self.typed_inputs.values.items():
                if isinstance(value, TypedInputValue):
                    expected_units = _expected_unit_for_input(key)
                    if expected_units and _canonical_unit(value.unit) not in expected_units:
                        raise ValueError(
                            f"typed input {key} expects unit {sorted(expected_units)}, got {value.unit}"
                        )
                normalized[key] = value.value if isinstance(value, TypedInputValue) else value
            self.inputs = {**self.inputs, **normalized}
        if self.mode is CalculationMode.PROFESSIONAL:
            has_upstream_effects = bool(
                isinstance(self.inputs.get("upstream_reaction_envelopes"), list)
                and self.inputs.get("upstream_reaction_envelopes")
            )
            has_typed_analysis = self.typed_inputs is not None and not isinstance(
                self.typed_inputs, TypedModuleInputs
            )
            if not self.loads and not has_upstream_effects and not has_typed_analysis:
                raise ValueError("专业模式必须明确提供荷载及来源")
            if any(item.source.strip().lower() in {"", "default", "默认"} for item in self.loads):
                raise ValueError("专业模式荷载必须填写可复核来源")
        return self


class CalculationStep(BaseModel):
    name: str
    equation: str
    substitution: str
    result: Quantity
    reference: str


class CheckResult(BaseModel):
    name: str
    demand: Quantity
    capacity: Quantity
    utilization: float = Field(ge=0)
    passed: bool
    reference: str
    note: str | None = None
    governing_combination: str | None = None


class LoadCombinationResult(BaseModel):
    name: str
    limit_state: Literal["ULS", "SLS"]
    combination_id: str | None = None
    sls_type: Literal["standard", "frequent", "quasi_permanent"] | None = None
    leading_action: str | None = None
    factors: dict[str, float]
    factored_by_kind: dict[str, Quantity]
    directions_by_kind: dict[str, list[LoadDirection]] = Field(default_factory=dict)
    total: Quantity
    effect_components: dict[
        Literal["N", "Vx", "Vy", "Mx", "My", "T"], Quantity
    ] = Field(default_factory=dict)


class DiagramPoint(BaseModel):
    x: Quantity
    value: Quantity


class DiagramSeries(BaseModel):
    name: str
    points: list[DiagramPoint]


class CalculationWarning(BaseModel):
    severity: Literal["info", "warning", "critical"]
    code: str
    message: str


class CalculationResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    engine_version: str = ENGINE_VERSION
    trace_id: str
    project_name: str
    module: CalculationModule
    mode: CalculationMode
    status: Literal["passed", "failed", "incomplete", "not_applicable"]
    workflow_status: Literal[
        "ready", "stale", "missing_inputs", "capability_unavailable"
    ] | None = None
    engineering_status: Literal["passed", "failed", "incomplete"] | None = None
    quick_outcome: Literal["screening_passed", "screening_failed"] | None = None
    result_class: Literal["quick_estimate", "professional_check"] | None = None
    verification_status: Literal[
        "unverified", "independently_verified"
    ] = "unverified"
    standards: list[str]
    input_summary: dict[str, Quantity | str | bool]
    combinations: list[LoadCombinationResult]
    reactions: dict[str, Quantity] = Field(default_factory=dict)
    reaction_envelopes: list["ReactionEnvelope"] = Field(default_factory=list)
    diagrams: list[DiagramSeries] = Field(default_factory=list)
    steps: list[CalculationStep] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    provisional_checks: list[CheckResult] = Field(default_factory=list)
    governing_check: str | None = None
    warnings: list[CalculationWarning] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    applicability: list[str] = Field(default_factory=list)
    catalog_versions: dict[str, str] = Field(default_factory=dict)
    load_provenance: list[LoadItem] = Field(default_factory=list)
    # Kept only in memory while reading historical 3.1-and-earlier results.
    # It is excluded from every Schema 3.2 response and stored result object.
    disclaimer: str | None = Field(default=None, exclude=True)


class ReactionEnvelope(BaseModel):
    name: str
    limit_state: Literal["ULS", "SLS"]
    combination_id: str | None = None
    combination_name: str | None = None
    sls_type: Literal["standard", "frequent", "quasi_permanent"] | None = None
    leading_action: str | None = None
    direction: LoadDirection | None = None
    components: dict[Literal["N", "Vx", "Vy", "Mx", "My", "T"], Quantity]

    @model_validator(mode="after")
    def complete_six_component_contract(self) -> "ReactionEnvelope":
        """Normalize legacy 2.x partial envelopes to the six-component contract."""

        force_unit = next(
            (
                value.unit
                for key, value in self.components.items()
                if key in {"N", "Vx", "Vy"}
            ),
            "kN",
        )
        moment_unit = next(
            (
                value.unit
                for key, value in self.components.items()
                if key in {"Mx", "My", "T"}
            ),
            "kN·m",
        )
        completed = dict(self.components)
        for key in ("N", "Vx", "Vy"):
            completed.setdefault(key, Quantity(value=0, unit=force_unit))
        for key in ("Mx", "My", "T"):
            completed.setdefault(key, Quantity(value=0, unit=moment_unit))
        self.components = completed  # type: ignore[assignment]
        return self


class ScenarioTemplate(BaseModel):
    id: str
    title: str
    description: str
    module: CalculationModule
    inputs: dict[str, Any]
    loads: list[LoadItem]
    assumptions: list[str]


def require_current_request_schema(request: CalculationRequest) -> None:
    """Reject recalculation of immutable legacy snapshots at write endpoints."""

    if request.schema_version == SCHEMA_VERSION:
        return
    from .errors import CalculationInputError

    raise CalculationInputError(
        "legacy_schema_read_only",
        f"schema {request.schema_version} 仅支持读取；新计算必须使用 {SCHEMA_VERSION}",
        field="schema_version",
        details={
            "received": request.schema_version,
            "required": SCHEMA_VERSION,
        },
    )
