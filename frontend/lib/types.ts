import type { ApiCalculationModule } from "./generated-api";

export type Mode = "quick" | "professional";

export type Module = ApiCalculationModule;

export interface LoadItem {
  kind: "self_weight" | "dead" | "live" | "wind" | "snow" | "seismic";
  value: number;
  unit: "kN/m" | "kN/m2" | "kN";
  source: string;
  direction?: "gravity" | "uplift" | "x_positive" | "x_negative" | "y_positive" | "y_negative";
  preset_id?: string;
  source_reference?: string;
  override_reason?: string;
}

export interface Scenario {
  id: string;
  title: string;
  description: string;
  module: Module;
  inputs: Record<string, unknown>;
  loads: LoadItem[];
  assumptions: string[];
}

export type SceneMaturity = "verified" | "beta" | "planned";
export type SceneAvailability = "public" | "development";
export type VerificationStatus = "unverified" | "independently_verified";
export type WorkflowStatus = "ready" | "stale" | "missing_inputs" | "capability_unavailable";

export interface SceneParameter {
  key: string;
  label: string;
  value_type: "number" | "choice" | "boolean" | "text";
  unit?: string;
  default?: unknown;
  options: string[];
  required: boolean;
  hidden_when_condition_driven?: boolean;
}

export type SceneConditionApplicability = "required" | "optional" | "not_applicable" | "not_supported";

export interface SceneConditionProfile {
  wind: SceneConditionApplicability;
  snow: SceneConditionApplicability;
  seismic: SceneConditionApplicability;
  wind_semantics: "roof" | "solid_panel" | "open_frame" | "bridge_side" | "not_applicable";
  snow_semantics: "roof" | "exposed_horizontal" | "not_applicable";
  height_parameter_keys: string[];
  roof_form_parameter_key?: string | null;
  geotechnical_mode: "generic" | "variant_owned";
}

export interface SceneVariant {
  id: string;
  title: string;
  description: string;
  material_systems: string[];
  parameters: SceneParameter[];
  availability?: SceneAvailability;
  support_system?: string;
  roof_form?: string;
  condition_profile?: SceneConditionProfile | null;
  graph_template?: SceneGraphTemplate;
  load_package?: SceneLoadPackage;
}

export interface SceneNode {
  id: string;
  label: string;
  role: string;
  calculation_module?: string;
  required: boolean;
  applicability?: "required" | "optional" | "not_applicable";
  verification_status?: VerificationStatus;
  quick_assumption?: string;
  maturity: SceneMaturity;
  description: string;
  input_bindings?: Record<string, string>;
}

export interface SceneGraphTemplate {
  id: string;
  version: string;
  nodes: SceneNode[];
  connections: SceneConnection[];
}

export interface SceneLoadCase {
  id: string;
  label: string;
  kind: LoadItem["kind"] | "soil" | "water" | "buoyancy" | "temperature" | "custom";
  value_type: "fixed" | "reference_range" | "calculated" | "project_defined";
  recommended_min?: number;
  recommended_default?: number;
  recommended_max?: number;
  adopted_value: number;
  unit: string;
  direction?: LoadItem["direction"];
  source_reference: string;
  override_reason?: string;
  applicable_when: string;
  distribution: "point" | "line" | "area" | "pressure";
  application_target: string;
  notes?: string;
  project_source?: string;
  project_reference?: string;
}

export interface SceneLoadPackage {
  id: string;
  version: string;
  title: string;
  description: string;
  items: SceneLoadCase[];
}

export interface SceneConnection {
  id: string;
  source_node_id: string;
  target_node_id: string;
  transfer: string;
  output_unit?: string;
  input_unit?: string;
  support: "base" | "left" | "right";
  description: string;
}

export interface SceneFamily {
  id: string;
  title: string;
  description: string;
  icon: string;
  maturity: SceneMaturity;
  variants: SceneVariant[];
  graph_template: SceneGraphTemplate;
  availability?: SceneAvailability;
  default_variant_id?: string;
  boundaries: string[];
}

export interface CalculationLibraryItem {
  id: string;
  title: string;
  task: string;
  task_title: string;
  material?: "steel" | "concrete" | "timber" | "masonry";
  module?: Module;
  maturity: SceneMaturity;
  description: string;
  presets: string[];
}

export interface CalculationLibrary {
  version: string;
  items: CalculationLibraryItem[];
}

export interface SceneInstance {
  id: number;
  project_id: number;
  family_id: string;
  variant_id: string;
  title: string;
  mode: Mode;
  template_version: string;
  draft_state: Record<string, unknown>;
  stale_node_ids: string[];
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface SceneNodeResult {
  node_id: string;
  label: string;
  status: "completed" | "passed" | "failed" | "incomplete" | "not_applicable";
  maturity: SceneMaturity;
  calculation_result?: CalculationResult;
  message?: string;
  stale: boolean;
  workflow_status?: WorkflowStatus;
  engineering_status?: "passed" | "failed" | "incomplete" | null;
  quick_outcome?: "screening_passed" | "screening_failed" | null;
  verification_status?: VerificationStatus;
  applicability?: "required" | "optional" | "not_applicable";
}

export interface SceneRevisionResult {
  scene_family_id: string;
  scene_variant_id: string;
  mode: Mode;
  status: "passed" | "failed" | "incomplete";
  workflow_status?: WorkflowStatus;
  engineering_status?: "passed" | "failed" | "incomplete" | null;
  quick_outcome?: "screening_passed" | "screening_failed" | null;
  result_class?: "quick_estimate" | "professional_check" | "scheme_estimate" | "project_check";
  requested_stage?: "scheme_estimate" | "project_check";
  verification_status?: VerificationStatus;
  completed_nodes: number;
  total_required_nodes: number;
  node_results: Record<string, SceneNodeResult>;
  missing_nodes: string[];
  stale_node_ids: string[];
  control_path: string[];
  warnings: string[];
  catalog_versions: Record<string, string>;
  load_cases?: SceneLoadCase[];
  site_profile?: ProjectSiteProfile | null;
  geotechnical_profile?: ProjectGeotechnicalProfile | null;
  structural_profile?: SceneStructuralProfile | null;
  space_frame_analysis?: {
    solver: string;
    verification_status: "unverified";
    node_count: number;
    member_count: number;
    roof_area_m2: number;
    maximum_translation_mm: number;
    load_balance_kn: [number, number, number];
    support_reactions: Record<
      string,
      {
        fx_kn: number;
        fy_kn: number;
        fz_kn: number;
        mx_kn_m: number;
        my_kn_m: number;
        mz_kn_m: number;
      }
    >;
    load_scope: string;
  } | null;
  seismic_action_package?: SeismicActionPackage | null;
  applied_conditions?: Array<"wind" | "snow" | "seismic">;
}

export interface SceneRevision {
  id: number;
  project_id: number;
  revision_number: number;
  snapshot_schema_version: string;
  scene_instance_id: number;
  scene_result: SceneRevisionResult;
  result_bundle: Record<string, CalculationResult>;
  catalog_versions: Record<string, string>;
  engine_version: string;
  report_number: string;
  created_at: string;
}

export interface Quantity {
  value: number;
  unit: string;
}

export interface CheckResult {
  name: string;
  demand: Quantity;
  capacity: Quantity;
  utilization: number;
  passed: boolean;
  reference: string;
  note?: string;
}

export interface LoadCombination {
  name: string;
  limit_state: "ULS" | "SLS";
  design_situation?: "persistent" | "seismic";
  factors: Record<string, number>;
  factored_by_kind: Record<string, Quantity>;
  total: Quantity;
}

export interface DiagramSeries {
  name: string;
  points: Array<{ x: Quantity; value: Quantity }>;
}

export interface CalculationResult {
  schema_version: string;
  engine_version: string;
  trace_id: string;
  project_name: string;
  module: Module;
  mode: Mode;
  status: "passed" | "failed" | "incomplete" | "not_applicable";
  workflow_status?: WorkflowStatus;
  engineering_status?: "passed" | "failed" | "incomplete" | null;
  quick_outcome?: "screening_passed" | "screening_failed" | null;
  result_class?: "quick_estimate" | "professional_check" | "scheme_estimate" | "project_check";
  verification_status?: VerificationStatus;
  standards: string[];
  input_summary: Record<string, Quantity | string | boolean>;
  combinations: LoadCombination[];
  reactions: Record<string, Quantity>;
  diagrams: DiagramSeries[];
  steps: Array<{
    name: string;
    equation: string;
    substitution: string;
    result: Quantity;
    reference: string;
  }>;
  checks: CheckResult[];
  provisional_checks?: CheckResult[];
  governing_check?: string;
  warnings: Array<{
    severity: "info" | "warning" | "critical";
    code: string;
    message: string;
  }>;
  assumptions: string[];
  applicability: string[];
  catalog_versions?: Record<string, string>;
  load_provenance?: LoadItem[];
}

export interface RebarMaterial {
  id: string;
  label: string;
  fy_mpa: number | null;
  fyv_mpa: number | null;
  status: "active" | "restricted" | "legacy" | "blocked";
  roles: string[];
  notes: string[];
  diameters: Array<{
    diameter_mm: number;
    area_mm2: number;
    mass_kg_m: number;
  }>;
}

export interface MaterialCatalog {
  version: string;
  standard_profile: string;
  source_references: string[];
  items: RebarMaterial[];
}

export interface LoadPreset {
  id: string;
  category: string;
  label: string;
  value: number;
  value_max?: number;
  unit: string;
  kind: LoadItem["kind"];
  scenes: string[];
  source_reference: string;
  notes: string;
}

export interface LoadCatalog {
  version: string;
  items: LoadPreset[];
}

export interface ClimateLocation {
  id: string;
  province: string;
  city: string;
  station: string;
  elevation_m: number;
  wind_kpa: Record<"10" | "50" | "100", number | null>;
  snow_kpa: Record<"10" | "50" | "100", number | null>;
  snow_zone: string | null;
}

export interface ClimateCatalog {
  version: string;
  coverage: string;
  professional_use_requires_confirmation: boolean;
  items: ClimateLocation[];
}

export type ClimateRegionId = "zhejiang_coastal" | "zhejiang_inland" | "zhejiang_mountain" | "manual";

export type SeismicLevel = "6_005g" | "7_010g" | "7_015g" | "8_020g" | "8_030g" | "9_040g";

export interface ClimateRegionPreset {
  id: ClimateRegionId;
  label: string;
  station_scope: string[];
  wind_kpa: Record<"10" | "50" | "100", number>;
  snow_kpa: Record<"10" | "50" | "100", number>;
  source_reference: string;
  catalog_version: string;
  verification_status: "unverified";
}

export interface ClimateRegionCatalog {
  version: string;
  verification_status: "unverified";
  items: ClimateRegionPreset[];
}

export interface SeismicDesignProfile {
  level: SeismicLevel;
  intensity: 6 | 7 | 8 | 9;
  design_acceleration_g: number;
  alpha_max: number;
  catalog_version: string;
  formula_reference: string;
  source_reference: string;
}

export interface SeismicDesignCatalog {
  version: string;
  items: SeismicDesignProfile[];
}

export interface ProjectSiteProfile {
  profile_version?: "1.0" | "1.1";
  completed_conditions?: Array<"wind" | "snow" | "seismic">;
  region_preset?: ClimateRegionId | null;
  recurrence_period_years: 10 | 50 | 100;
  basic_wind_pressure_kpa?: number | null;
  basic_snow_pressure_kpa?: number | null;
  climate_source_reference?: string | null;
  terrain_category: "A" | "B" | "C" | "D";
  structure_shape: "open_frame" | "solid_panel" | "roof";
  roof_form: "flat" | "single_slope" | "double_slope" | "other";
  height_factor_override?: number | null;
  wind_shape_factor_override?: number | null;
  snow_shape_factor_override?: number | null;
  override_reason?: string | null;
  seismic_level?: SeismicLevel | null;
  catalog_versions: Record<string, string>;
}

export interface GroundwaterDesignProfile {
  condition: "no_influence" | "known_levels" | "unknown";
  construction_level_m?: number | null;
  service_level_m?: number | null;
  antifloat_level_m?: number | null;
  source: string;
  observation_date?: string | null;
}

export interface ProjectGeotechnicalProfile {
  profile_version: "1.0" | "1.1";
  stage: "scheme_estimate" | "project_check";
  regional_hint_id?: string | null;
  confirmed_soil_class: string;
  bearing_capacity_kpa: number;
  bearing_capacity_source: string;
  deformation_modulus_mpa?: number | null;
  compression_modulus_mpa?: number | null;
  settlement_layers?: Array<{
    id: string;
    name: string;
    thickness_m: number;
    compression_modulus_mpa: number;
    unit_weight_kn_m3: number;
    source: string;
  }>;
  settlement_correction_factor?: number | null;
  settlement_limit_mm?: number | null;
  groundwater: GroundwaterDesignProfile;
  report_name?: string | null;
  report_date?: string | null;
  catalog_versions: Record<string, string>;
}

export interface SectionCatalogEntry {
  id: string;
  family: "SHS" | "RHS" | "CHS" | "H" | "I" | "C" | "L" | "2L";
  designation: string;
  dimensions: Record<string, number>;
  area_mm2: number;
  self_weight_kn_m: number;
  material_grades: string[];
  source_reference: string;
}

export interface CustomSectionDefinition {
  id: string;
  name: string;
  family: "SHS" | "RHS" | "CHS" | "H" | "I";
  dimensions: Record<string, number>;
  area_mm2: number;
  iy_mm4: number;
  iz_mm4: number;
  torsion_mm4: number;
  self_weight_kn_m: number;
  theoretical_mass_kg_m?: number | null;
  radius_y_mm?: number | null;
  radius_z_mm?: number | null;
  corner_radius_mm?: number | null;
  revision?: number;
  source_type?: "catalog" | "manufacturer" | "user_geometry";
  property_trace?: string[];
  assumptions?: string[];
  source_reference: string;
}

export interface MemberSpecification {
  node_id: string;
  member_role: string;
  material_grade: string;
  section_catalog_id: string;
  section_type: SectionCatalogEntry["family"];
  section_name: string;
  orientation: "strong_axis" | "weak_axis";
  effective_length_m: number;
  unbraced_length_m: number;
  selection_source: "recommended" | "user_locked";
  override_reason?: string | null;
}

export interface FoundationDesignSpecification {
  node_id: string;
  foundation_system_id: string;
  selection_source: "recommended" | "user_locked";
  length_m: number;
  width_m: number;
  thickness_mm: number;
  embedment_m: number;
  concrete_grade: string;
  rebar_grade: string;
  bar_diameter_mm: number;
  bar_spacing_mm: number;
  plan_shape?: "rectangular";
  section_shape?: "prismatic" | "stepped" | "tapered";
  left_projection_m?: number | null;
  right_projection_m?: number | null;
  front_projection_m?: number | null;
  back_projection_m?: number | null;
  steps?: Array<{ length_m: number; width_m: number; height_mm: number }>;
  tapered_top_length_m?: number | null;
  tapered_top_width_m?: number | null;
  pedestal?: {
    enabled: boolean;
    length_mm?: number | null;
    width_mm?: number | null;
    height_mm?: number | null;
    longitudinal_bar_count?: number | null;
    longitudinal_bar_diameter_mm?: number | null;
    stirrup_diameter_mm?: number | null;
    stirrup_spacing_mm?: number | null;
  } | null;
  reinforcement?: {
    bottom_x_diameter_mm: number;
    bottom_x_spacing_mm: number;
    bottom_y_diameter_mm: number;
    bottom_y_spacing_mm: number;
    top_local_diameter_mm?: number | null;
    top_local_spacing_mm?: number | null;
  } | null;
  override_reason?: string | null;
}

export interface SceneStructuralProfile {
  profile_version: "1.0" | "2.0" | "3.0";
  stage: "scheme_estimate" | "project_check";
  exposure?: {
    vertical_enclosure: "none" | "open_members" | "perforated_panel" | "solid_panel";
    top_cover: "none" | "louver_grid" | "permeable_cover" | "solid_roof";
    vertical_open_ratio?: number | null;
    top_open_ratio?: number | null;
    roof_form?: "flat" | "single_slope" | "double_slope" | "other" | null;
    roof_slope_deg?: number | null;
    source: string;
  } | null;
  members: MemberSpecification[];
  member_groups?: Array<{
    group_id: string;
    role: string;
    material_grade: string;
    section_catalog_id?: string | null;
    custom_section_id?: string | null;
    strong_axis_unbraced_length_m: number;
    weak_axis_unbraced_length_m: number;
    effective_length_factor_y: number;
    effective_length_factor_z: number;
  }>;
  member_overrides?: Array<{
    member_id: string;
    material_grade: string;
    section_id: string;
    orientation: "strong_axis" | "weak_axis";
    source: string;
  }>;
  foundations: FoundationDesignSpecification[];
  geometry?: SceneGeometryProfile | null;
  roof_assembly?: RoofAssembly | null;
  catalog_versions: Record<string, string>;
}

export interface RoofAssembly {
  id: string;
  title: string;
  cover_type: "none" | "louver" | "glass" | "aluminum" | "steel" | "polycarbonate" | "timber" | "custom";
  layers: Array<{
    name: string;
    thickness_mm?: number | null;
    unit_weight_kn_m3?: number | null;
    surface_weight_kn_m2: number;
  }>;
  total_dead_load_kn_m2: number;
  reference_range_kn_m2: [number, number];
  source_reference: string;
  verification_status: "unverified" | "independently_verified";
}

export interface ModelObjectMark {
  object_id: string;
  object_kind: "node" | "member" | "support" | "foundation" | "roof_surface";
  mark: string;
  label: string;
}

export interface MemberTypeDefinition {
  id: string;
  mark_prefix: string;
  title: string;
  role: "column" | "beam" | "purlin" | "truss_chord" | "truss_web" | "brace";
  material_grade: string;
  section_id: string;
  orientation: "strong_axis" | "weak_axis";
  end_release: "rigid" | "pinned";
}

export interface MemberInstanceAssignment {
  member_id: string;
  member_type_id: string;
  mark: string;
  override_section_id?: string | null;
  source: "type" | "instance_override";
}

export interface FoundationTypeDefinition {
  id: string;
  mark: string;
  title: string;
  form_id: string;
  length_m: number;
  width_m: number;
  thickness_mm: number;
  embedment_m: number;
  concrete_grade: string;
  rebar_grade: string;
  bottom_x: string;
  bottom_y: string;
  top_x?: string | null;
  top_y?: string | null;
  cover_mm?: number | null;
  steps?: Array<{ length_m: number; width_m: number; height_mm: number }>;
  tapered_top_length_m?: number | null;
  tapered_top_width_m?: number | null;
  tapered_height_mm?: number | null;
  pedestal?: PedestalProfile | null;
}

export interface PedestalProfile {
  enabled: boolean;
  auto_enabled: boolean;
  override_reason?: string | null;
  length_mm?: number | null;
  width_mm?: number | null;
  clear_height_mm?: number | null;
  top_elevation_m?: number | null;
  bottom_elevation_m?: number | null;
  concrete_grade?: string | null;
  cover_mm?: number | null;
  longitudinal_bar_count_x?: number | null;
  longitudinal_bar_count_y?: number | null;
  longitudinal_bar_diameter_mm?: number | null;
  stirrup_diameter_mm?: number | null;
  stirrup_spacing_mm?: number | null;
  confinement_spacing_mm?: number | null;
  dowel_anchorage_mm?: number | null;
  splice_type: "none" | "lap" | "mechanical" | "welded";
  top_local_reinforcement: boolean;
}

export interface ConnectionTypeDefinition {
  id: string;
  mark: string;
  title: string;
  family: "beam_column" | "secondary_beam" | "beam_splice" | "brace" | "column_base";
  behavior: "rigid" | "pinned" | "semi_rigid";
  supported_section_families: string[];
  parameters: Record<string, number | string | boolean>;
  verification_status: "unverified" | "independently_verified";
}

export interface ConnectionInstanceAssignment {
  id: string;
  mark: string;
  connection_type_id: string;
  node_id: string;
  member_ids: string[];
  status: "defined" | "unsupported" | "incomplete";
  message?: string | null;
}

export interface ColumnBaseAssembly {
  id: string;
  column_member_id: string;
  support_id: string;
  connection_instance_id?: string | null;
  base_plate_length_mm: number;
  base_plate_width_mm: number;
  base_plate_thickness_mm: number;
  anchor_grade: string;
  anchor_diameter_mm: number;
  anchor_count: number;
  anchor_embedment_mm: number;
  anchor_spacing_mm?: number | null;
  anchor_edge_mm?: number | null;
  anchor_head_diameter_mm?: number | null;
  anchor_supplementary_reinforcement_area_mm2?: number | null;
  anchor_cracked_concrete?: boolean;
  contact_stiffness_kn_m3?: number | null;
  contact_model_source?: string | null;
  anchor_springs?: Array<{ x_m: number; y_m: number; stiffness_kn_m: number }>;
  continuous_perimeter_weld?: boolean | null;
  weld_throat_mm?: number | null;
  concrete_bearing_capacity_mpa?: number | null;
  grout_thickness_mm: number;
}

export interface FoundationInstanceAssignment {
  id: string;
  support_id: string;
  foundation_type_id: string;
  mark: string;
  column_member_id?: string | null;
}

export interface WorkPlaneDefinition {
  id: string;
  kind: "plan" | "x_elevation" | "y_elevation";
  elevation_m?: number | null;
}

export interface DoubleSlopeRoofRule {
  ridge_direction_deg: number;
  ridge_offset_ratio: number;
  left_slope_deg: number;
  right_slope_deg: number;
}

export interface SceneGeometryProfile {
  profile_version: "1.0" | "2.0" | "2.1" | "2.2" | "2.3";
  layout_mode: "preset" | "custom_grid" | "free_plan";
  axes: Array<{ id: string; direction: "x" | "y"; positions_m: number[] }>;
  nodes: Array<{
    id: string;
    x_m: number;
    y_m: number;
    z_m: number;
    support: "none" | "pinned" | "fixed";
    column_top: boolean;
  }>;
  members: Array<{
    id: string;
    start_node_id: string;
    end_node_id: string;
    role: "column" | "beam" | "purlin" | "truss_chord" | "truss_web" | "brace";
    group_id: string;
    behavior: "frame" | "truss";
    end_release: "rigid" | "pinned";
    start_release?: MemberEndRelease | null;
    end_release_dofs?: MemberEndRelease | null;
    rigid_offset?: { start_m: number; end_m: number } | null;
    design_parameters?: MemberDesignParameters | null;
  }>;
  roof_surfaces: Array<{
    id: string;
    node_ids: string[];
    form: "flat" | "single_slope" | "double_slope" | "faceted";
    load_path_group_ids: string[];
    load_direction_deg?: number | null;
    opening_ids?: string[];
  }>;
  supports?: Array<{
    id: string;
    node_id: string;
    restraint: "pinned" | "fixed" | "spring";
    foundation_id?: string | null;
    restrained_dofs?: Array<"ux" | "uy" | "uz" | "rx" | "ry" | "rz">;
    spring_stiffness?: Record<string, number>;
  }>;
  plan_boundary?: {
    outer_points: Array<{ id: string; x_m: number; y_m: number }>;
    outer_segments: Array<{
      id: string;
      start_point_id: string;
      end_point_id: string;
      kind: "line" | "arc";
      arc_mid_x_m?: number | null;
      arc_mid_y_m?: number | null;
    }>;
    source: string;
  } | null;
  roof_elevation?: {
    kind: "flat" | "single_slope" | "double_slope" | "node_elevations";
    datum_height_m: number;
    slope_deg?: number | null;
    direction_deg?: number | null;
    ridge_start?: [number, number] | null;
    ridge_end?: [number, number] | null;
    opposite_slope_deg?: number | null;
  } | null;
  object_marks?: ModelObjectMark[];
  member_types?: MemberTypeDefinition[];
  member_instances?: MemberInstanceAssignment[];
  foundation_types?: FoundationTypeDefinition[];
  foundation_instances?: FoundationInstanceAssignment[];
  work_planes?: WorkPlaneDefinition[];
  double_slope_rule?: DoubleSlopeRoofRule | null;
  connection_types?: ConnectionTypeDefinition[];
  connection_instances?: ConnectionInstanceAssignment[];
  column_bases?: ColumnBaseAssembly[];
  roof_openings?: Array<{ id: string; surface_id: string; node_ids: string[] }>;
  roof_load_zones?: Array<{
    id: string;
    surface_id: string;
    boundary_node_ids: string[];
    roof_assembly_id: string;
    load_path_group_ids: string[];
    load_direction_deg?: number | null;
  }>;
  source: string;
}

export interface MemberEndRelease {
  ux: boolean;
  uy: boolean;
  uz: boolean;
  rx: boolean;
  ry: boolean;
  rz: boolean;
}

export interface MemberDesignParameters {
  local_axis_rotation_deg: number;
  effective_length_factor_y: number;
  effective_length_factor_z: number;
  unbraced_length_y_m?: number | null;
  unbraced_length_z_m?: number | null;
  deflection_limit_ratio: number;
  utilization_limit: number;
}

export interface SeismicActionPackage {
  profile: SeismicDesignProfile;
  gravity_representative_value_kn: number;
  gravity_factors: Record<string, number>;
  alpha1: number;
  f_ek_kn: number;
  actions: Array<{
    id: string;
    direction: "x_positive" | "x_negative" | "y_positive" | "y_negative";
    force_kn: number;
    signed_force_kn: number;
    combination_factor: 1;
    design_situation: "seismic";
  }>;
  base_reactions_kn: Record<"x_positive" | "x_negative" | "y_positive" | "y_negative", number>;
  formula: string;
  source_reference: string;
  catalog_version: string;
  verification_status: "unverified";
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  must_change_password: boolean;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  version_count: number;
  site_profile?: ProjectSiteProfile | null;
  geotechnical_profile?: ProjectGeotechnicalProfile | null;
}

export interface ProjectVersion {
  id: number;
  project_id: number;
  version_number: number;
  calculation_input: Record<string, unknown>;
  calculation_result: CalculationResult;
  engine_version: string;
  report_number: string;
  created_at: string;
}
