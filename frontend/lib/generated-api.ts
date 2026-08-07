/**
 * Generated snapshot of backend OpenAPI Schema 3.2 calculation contracts.
 * Source: CalculationRequest.model_json_schema(), engine 3.2.0-beta.1.
 * Do not add product-only fields here; regenerate when the backend contract changes.
 */

export type ApiCalculationModule =
  | "steel_beam"
  | "steel_column"
  | "portal_frame"
  | "concrete_beam"
  | "concrete_slab"
  | "concrete_column"
  | "spread_footing"
  | "strip_footing"
  | "timber_beam"
  | "timber_column"
  | "steel_baseplate_anchor"
  | "timber_deck_panel"
  | "steel_cantilever_post"
  | "masonry_wall"
  | "rc_wall"
  | "retaining_wall"
  | "continuous_beam"
  | "planar_frame"
  | "planar_truss"
  | "two_way_slab"
  | "timber_connection"
  | "wall_anchor"
  | "pool_structure"
  | "pile_group_cap"
  | "bridge_steel_timber"
  | "bridge_rc"
  | "gravity_retaining_wall"
  | "site_rc_wall"
  | "steel_infill_wall"
  | "plain_masonry_wall"
  | "load_combinations"
  | "wind_snow_guide"
  | "soil_water_actions";

export interface ApiTypedValue {
  value: number;
  unit: string;
}

export interface ApiAnalysisCombination {
  combination_id: string;
  combination_name: string;
  limit_state: "ULS" | "SLS";
}

export interface ApiConnectionEffect extends ApiAnalysisCombination {
  axial: ApiTypedValue;
  shear_x: ApiTypedValue;
  shear_y: ApiTypedValue;
  moment_x: ApiTypedValue;
  moment_y: ApiTypedValue;
  torsion: ApiTypedValue;
}

export interface ApiPosition {
  x: ApiTypedValue;
  y: ApiTypedValue;
}

export interface ApiContinuousBeamInputs extends ApiAnalysisCombination {
  module: "continuous_beam";
  nodes: string[];
  spans: Array<{
    id: string;
    start: string;
    end: string;
    length: ApiTypedValue;
    elastic_modulus: ApiTypedValue;
    inertia: ApiTypedValue;
    uniform_load_local_y: ApiTypedValue;
    moment_capacity: ApiTypedValue;
    shear_capacity: ApiTypedValue;
  }>;
  supports: Array<{ node: string; vertical: boolean; rotation: boolean }>;
  nodal_loads: Array<{
    node: string;
    force_y: ApiTypedValue;
    moment_z: ApiTypedValue;
  }>;
  deflection_limit: ApiTypedValue;
}

export interface ApiPlanarFrameInputs extends ApiAnalysisCombination {
  module: "planar_frame";
  nodes: Array<{ id: string; x: ApiTypedValue; y: ApiTypedValue }>;
  members: Array<{
    id: string;
    start: string;
    end: string;
    area: ApiTypedValue;
    inertia: ApiTypedValue;
    elastic_modulus: ApiTypedValue;
    axial_capacity: ApiTypedValue;
    shear_capacity: ApiTypedValue;
    moment_capacity: ApiTypedValue;
  }>;
  restraints: Array<{ node: string; ux: boolean; uy: boolean; rz: boolean }>;
  nodal_loads: Array<{
    node: string;
    force_x: ApiTypedValue;
    force_y: ApiTypedValue;
    moment_z: ApiTypedValue;
  }>;
  uniform_loads: Array<{ member: string; local_y: ApiTypedValue }>;
  displacement_limit: ApiTypedValue;
}

export interface ApiPlanarTrussInputs extends ApiAnalysisCombination {
  module: "planar_truss";
  nodes: Array<{ id: string; x: ApiTypedValue; y: ApiTypedValue }>;
  members: Array<{
    id: string;
    start: string;
    end: string;
    area: ApiTypedValue;
    elastic_modulus: ApiTypedValue;
    axial_capacity: ApiTypedValue;
  }>;
  restraints: Array<{ node: string; ux: boolean; uy: boolean }>;
  nodal_loads: Array<{
    node: string;
    force_x: ApiTypedValue;
    force_y: ApiTypedValue;
  }>;
  displacement_limit: ApiTypedValue;
}

export interface ApiTwoWaySlabInputs extends ApiAnalysisCombination {
  module: "two_way_slab";
  short_span: ApiTypedValue;
  long_span: ApiTypedValue;
  thickness: ApiTypedValue;
  elastic_modulus: ApiTypedValue;
  uniform_load: ApiTypedValue;
  support_condition: "four_edges_simply_supported" | "four_edges_fixed";
  poisson_ratio: number;
  short_direction_moment_capacity: ApiTypedValue;
  long_direction_moment_capacity: ApiTypedValue;
  deflection_limit: ApiTypedValue;
}

export interface ApiTimberConnectionInputs {
  module: "timber_connection";
  post_width: ApiTypedValue;
  post_depth: ApiTypedValue;
  plate_width: ApiTypedValue;
  plate_depth: ApiTypedValue;
  fastener_diameter: ApiTypedValue;
  fastener_positions: ApiPosition[];
  connector_standoff: ApiTypedValue;
  effects: ApiConnectionEffect[];
  bearing_design_capacity?: ApiTypedValue;
  fastener_tension_design_capacity?: ApiTypedValue;
  fastener_shear_design_capacity?: ApiTypedValue;
  connector_bending_design_capacity?: ApiTypedValue;
  minimum_spacing?: ApiTypedValue;
  minimum_edge_distance?: ApiTypedValue;
}

export interface ApiWallAnchorInputs {
  module: "wall_anchor";
  base_material: "reinforced_concrete" | "solid_masonry" | "unknown";
  plate_width: ApiTypedValue;
  plate_depth: ApiTypedValue;
  anchor_diameter: ApiTypedValue;
  anchor_positions: ApiPosition[];
  effects: ApiConnectionEffect[];
  anchor_tension_design_capacity?: ApiTypedValue;
  anchor_shear_design_capacity?: ApiTypedValue;
  minimum_spacing?: ApiTypedValue;
  minimum_edge_distance?: ApiTypedValue;
  concrete_capacity_method: "provided" | "simplified";
  concrete_cone_design_capacity?: ApiTypedValue;
  concrete_pullout_design_capacity?: ApiTypedValue;
  concrete_splitting_design_capacity?: ApiTypedValue;
  masonry_evaluated_tension_capacity?: ApiTypedValue;
  masonry_evaluated_shear_capacity?: ApiTypedValue;
  masonry_capacity_source?: string;
}

export interface ApiPoolStructureInputs {
  module: "pool_structure";
  geometry: {
    inside_length: ApiTypedValue;
    inside_width: ApiTypedValue;
    wall_height: ApiTypedValue;
    wall_thickness: ApiTypedValue;
    base_thickness: ApiTypedValue;
    base_projection: ApiTypedValue;
    retained_soil_height: ApiTypedValue;
    wall_horizontal_span?: ApiTypedValue;
  };
  materials: {
    concrete_unit_weight: ApiTypedValue;
    water_unit_weight: ApiTypedValue;
    soil_unit_weight: ApiTypedValue;
    soil_friction_angle: ApiTypedValue;
    surcharge: ApiTypedValue;
    allowable_bearing: ApiTypedValue;
    concrete_fc: ApiTypedValue;
    concrete_ft: ApiTypedValue;
    rebar_fy: ApiTypedValue;
    rebar_es: ApiTypedValue;
  };
  reinforcement: {
    wall_vertical_as: ApiTypedValue;
    wall_horizontal_as: ApiTypedValue;
    base_x_as: ApiTypedValue;
    base_y_as: ApiTypedValue;
    wall_bar_diameter: ApiTypedValue;
    base_bar_diameter: ApiTypedValue;
    wall_cover: ApiTypedValue;
    base_cover: ApiTypedValue;
    minimum_reinforcement_ratio: ApiTypedValue;
    crack_width_limit: ApiTypedValue;
  };
  water_levels: {
    full_internal_depth: ApiTypedValue;
    empty_external_head: ApiTypedValue;
    full_external_head?: ApiTypedValue;
  };
  additional_ballast: ApiTypedValue;
  antifloat_factor: ApiTypedValue;
}

export interface ApiPileGroupCapInputs extends ApiAnalysisCombination {
  module: "pile_group_cap";
  piles: Array<{
    id: string;
    x: ApiTypedValue;
    y: ApiTypedValue;
    diameter_or_side: ApiTypedValue;
    pile_type: "bored" | "precast_pipe" | "precast_square";
  }>;
  capacities: {
    compression: ApiTypedValue;
    uplift: ApiTypedValue;
    horizontal: ApiTypedValue;
    source: string;
  };
  cap: {
    length_x: ApiTypedValue;
    width_y: ApiTypedValue;
    thickness: ApiTypedValue;
    column_x: ApiTypedValue;
    column_y: ApiTypedValue;
    cover: ApiTypedValue;
    bar_diameter: ApiTypedValue;
  };
  material: {
    concrete_ft: ApiTypedValue;
    rebar_fy: ApiTypedValue;
    provided_rebar_x: ApiTypedValue;
    provided_rebar_y: ApiTypedValue;
    minimum_reinforcement_ratio: ApiTypedValue;
  };
  effects: {
    axial: ApiTypedValue;
    shear_x: ApiTypedValue;
    shear_y: ApiTypedValue;
    moment_x: ApiTypedValue;
    moment_y: ApiTypedValue;
    torsion: ApiTypedValue;
  };
}

export interface ApiBridgeGeometryInputs {
  span_count: ApiTypedValue;
  span_length: ApiTypedValue;
  deck_width: ApiTypedValue;
  crossbeam_spacing: ApiTypedValue;
  longitudinal_girder_count: ApiTypedValue;
}

export interface ApiSteelBridgeSectionInputs {
  area: ApiTypedValue;
  inertia: ApiTypedValue;
  section_modulus: ApiTypedValue;
  shear_area: ApiTypedValue;
  yield_strength: ApiTypedValue;
  elastic_modulus: ApiTypedValue;
  unit_weight: ApiTypedValue;
}

export interface ApiBridgeSteelTimberInputs {
  module: "bridge_steel_timber";
  geometry: ApiBridgeGeometryInputs;
  actions: {
    crowd_load: ApiTypedValue;
    additional_dead_load: ApiTypedValue;
    railing_dead_load_per_side: ApiTypedValue;
    wind_line_load: ApiTypedValue;
    span_live_load_factors?: ApiTypedValue[];
  };
  timber_deck: {
    thickness: ApiTypedValue;
    elastic_modulus: ApiTypedValue;
    bending_strength: ApiTypedValue;
    shear_strength: ApiTypedValue;
    unit_weight: ApiTypedValue;
    deflection_limit_ratio: ApiTypedValue;
  };
  crossbeam_section: ApiSteelBridgeSectionInputs;
  longitudinal_section: ApiSteelBridgeSectionInputs;
  comfort: {
    damping_ratio: ApiTypedValue;
    walking_frequency: ApiTypedValue;
    pedestrian_dynamic_force: ApiTypedValue;
    acceleration_limit: ApiTypedValue;
  };
  foundation_types?: Array<"shallow" | "pile">;
}

export interface ApiBridgeRCInputs {
  module: "bridge_rc";
  geometry: {
    span_count: ApiTypedValue;
    span_length: ApiTypedValue;
    deck_width: ApiTypedValue;
    deck_elevation: ApiTypedValue;
    slab_thickness: ApiTypedValue;
    girder_count: ApiTypedValue;
    girder_width: ApiTypedValue;
    girder_height: ApiTypedValue;
  };
  material: {
    concrete_elastic_modulus: ApiTypedValue;
    concrete_compressive_strength: ApiTypedValue;
    concrete_tensile_strength: ApiTypedValue;
    rebar_yield_strength: ApiTypedValue;
    concrete_density: ApiTypedValue;
    minimum_reinforcement_ratio: ApiTypedValue;
    maximum_reinforcement_ratio: ApiTypedValue;
  };
  reinforcement: {
    cover: ApiTypedValue;
    slab_bar_diameter: ApiTypedValue;
    slab_bar_spacing: ApiTypedValue;
    girder_bottom_area: ApiTypedValue;
    girder_top_area: ApiTypedValue;
    girder_stirrup_area: ApiTypedValue;
    girder_stirrup_spacing: ApiTypedValue;
  };
  loads: {
    spans: Array<{ additional_dead: ApiTypedValue; crowd: ApiTypedValue }>;
    railing_left: ApiTypedValue;
    railing_right: ApiTypedValue;
    wind_pressure: ApiTypedValue;
    wind_exposed_height: ApiTypedValue;
  };
  supports: Array<{
    id: string;
    node_index: ApiTypedValue;
    foundation_type: "shallow" | "pile";
  }>;
  service_limits: {
    crack_width_limit: ApiTypedValue;
    minimum_vertical_frequency: ApiTypedValue;
    slab_deflection_ratio: ApiTypedValue;
    girder_deflection_ratio: ApiTypedValue;
    cracked_stiffness_factor: ApiTypedValue;
  };
}

export interface ApiGravityRetainingWallInputs extends ApiAnalysisCombination {
  module: "gravity_retaining_wall";
  retained_height: ApiTypedValue;
  base_width: ApiTypedValue;
  base_slab_thickness: ApiTypedValue;
  wall_bottom_thickness: ApiTypedValue;
  wall_top_thickness: ApiTypedValue;
  toe_projection: ApiTypedValue;
  wall_unit_weight: ApiTypedValue;
  soil_unit_weight: ApiTypedValue;
  soil_friction_angle: ApiTypedValue;
  surcharge: ApiTypedValue;
  base_friction_coefficient: ApiTypedValue;
  soil_bearing_capacity: ApiTypedValue;
  material_compressive_design: ApiTypedValue;
  water_depth_behind: ApiTypedValue;
  water_unit_weight: ApiTypedValue;
  uplift_head_toe: ApiTypedValue;
  uplift_head_heel: ApiTypedValue;
  sliding_safety_factor: ApiTypedValue;
  overturning_safety_factor: ApiTypedValue;
}

export interface ApiSiteWallLoadCaseInputs extends ApiAnalysisCombination {
  wind_pressure: ApiTypedValue;
  additional_dead_load: ApiTypedValue;
}

export interface ApiSiteRCWallInputs {
  module: "site_rc_wall";
  height: ApiTypedValue;
  length: ApiTypedValue;
  thickness: ApiTypedValue;
  support_spacing: ApiTypedValue;
  opening_ratio: ApiTypedValue;
  concrete_unit_weight: ApiTypedValue;
  concrete_fc: ApiTypedValue;
  concrete_ft: ApiTypedValue;
  rebar_fy: ApiTypedValue;
  vertical_rebar: ApiTypedValue;
  horizontal_rebar: ApiTypedValue;
  cover: ApiTypedValue;
  bar_diameter: ApiTypedValue;
  minimum_reinforcement_ratio: ApiTypedValue;
  slenderness_limit: ApiTypedValue;
  load_cases: ApiSiteWallLoadCaseInputs[];
}

export interface ApiSteelInfillWallInputs {
  module: "steel_infill_wall";
  height: ApiTypedValue;
  length: ApiTypedValue;
  support_spacing: ApiTypedValue;
  opening_ratio: ApiTypedValue;
  infill_dead_load: ApiTypedValue;
  post_self_weight: ApiTypedValue;
  post_area: ApiTypedValue;
  post_inertia: ApiTypedValue;
  post_section_modulus: ApiTypedValue;
  steel_elastic_modulus: ApiTypedValue;
  steel_yield_strength: ApiTypedValue;
  effective_length_factor: ApiTypedValue;
  slenderness_limit: ApiTypedValue;
  maximum_post_spacing: ApiTypedValue;
  load_cases: ApiSiteWallLoadCaseInputs[];
}

export interface ApiPlainMasonryWallInputs {
  module: "plain_masonry_wall";
  height: ApiTypedValue;
  length: ApiTypedValue;
  thickness: ApiTypedValue;
  support_spacing: ApiTypedValue;
  opening_ratio: ApiTypedValue;
  masonry_unit_weight: ApiTypedValue;
  masonry_bending_strength: ApiTypedValue;
  masonry_shear_strength: ApiTypedValue;
  masonry_compression_strength: ApiTypedValue;
  slenderness_limit: ApiTypedValue;
  minimum_thickness: ApiTypedValue;
  maximum_height: ApiTypedValue;
  load_cases: ApiSiteWallLoadCaseInputs[];
}

export interface ApiLoadCombinationCaseInputs {
  id: string;
  label: string;
  category: "permanent" | "live" | "wind" | "snow" | "soil" | "water" | "buoyancy";
  characteristic: ApiTypedValue;
  direction: "gravity" | "uplift" | "x_positive" | "x_negative" | "y_positive" | "y_negative";
  distribution: "point" | "line" | "area" | "pressure";
  target: string;
  source_reference: string;
  exclusive_group?: string;
  permanent_role?: "auto" | "favorable" | "unfavorable";
  psi0?: ApiTypedValue;
  psi1?: ApiTypedValue;
  psi2?: ApiTypedValue;
}

export interface ApiLoadCombinationsInputs {
  module: "load_combinations";
  cases: ApiLoadCombinationCaseInputs[];
}

export interface ApiWindSnowGuideInputs {
  module: "wind_snow_guide";
  basic_wind_pressure: ApiTypedValue;
  wind_source_reference: string;
  recurrence_period: ApiTypedValue;
  recurrence_factor: ApiTypedValue;
  terrain_roughness: "A" | "B" | "C" | "D";
  terrain_height_factor: ApiTypedValue;
  shape_coefficient_positive: ApiTypedValue;
  shape_coefficient_negative: ApiTypedValue;
  wind_area: ApiTypedValue;
  snow_applicability: "applicable" | "not_applicable";
  basic_snow_pressure?: ApiTypedValue;
  snow_source_reference?: string;
  roof_snow_coefficient?: ApiTypedValue;
  snow_area?: ApiTypedValue;
  no_snow_basis?: string;
  target: string;
}

export interface ApiSoilWaterActionsInputs {
  module: "soil_water_actions";
  wall_height: ApiTypedValue;
  earth_pressure_state: "active" | "at_rest";
  soil_unit_weight_dry: ApiTypedValue;
  soil_unit_weight_saturated: ApiTypedValue;
  soil_friction_angle: ApiTypedValue;
  surcharge: ApiTypedValue;
  groundwater_depth_below_top: ApiTypedValue;
  water_unit_weight: ApiTypedValue;
  internal_water_depth: ApiTypedValue;
  external_water_depth?: ApiTypedValue;
  base_area: ApiTypedValue;
  at_rest_coefficient?: ApiTypedValue;
  source_reference: string;
  target: string;
}

export type ApiNextgenTypedInputs =
  | ApiContinuousBeamInputs
  | ApiPlanarFrameInputs
  | ApiPlanarTrussInputs
  | ApiTwoWaySlabInputs
  | ApiTimberConnectionInputs
  | ApiWallAnchorInputs
  | ApiPoolStructureInputs
  | ApiPileGroupCapInputs
  | ApiBridgeSteelTimberInputs
  | ApiBridgeRCInputs
  | ApiGravityRetainingWallInputs
  | ApiSiteRCWallInputs
  | ApiSteelInfillWallInputs
  | ApiPlainMasonryWallInputs
  | ApiLoadCombinationsInputs
  | ApiWindSnowGuideInputs
  | ApiSoilWaterActionsInputs;
