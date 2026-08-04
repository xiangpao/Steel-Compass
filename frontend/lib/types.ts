export type Mode = "quick" | "professional";

export type Module =
  | "steel_beam"
  | "steel_column"
  | "portal_frame"
  | "steel_baseplate_anchor"
  | "concrete_beam"
  | "concrete_slab"
  | "concrete_column"
  | "spread_footing"
  | "strip_footing"
  | "timber_beam"
  | "timber_column"
  | "timber_deck_panel"
  | "steel_cantilever_post"
  | "masonry_wall"
  | "rc_wall"
  | "retaining_wall";

export interface LoadItem {
  kind: "self_weight" | "dead" | "live" | "wind" | "snow";
  value: number;
  unit: "kN/m" | "kN/m2" | "kN";
  source: string;
  direction?:
    | "gravity"
    | "uplift"
    | "x_positive"
    | "x_negative"
    | "y_positive"
    | "y_negative";
  preset_id?: string;
  source_reference?: string;
  override_reason?: string;
  confirmed?: boolean;
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
export type WorkflowStatus =
  | "ready"
  | "stale"
  | "missing_inputs"
  | "capability_unavailable";

export interface SceneParameter {
  key: string;
  label: string;
  value_type: "number" | "choice" | "boolean" | "text";
  unit?: string;
  default?: unknown;
  options: string[];
  required: boolean;
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
  kind:
    | LoadItem["kind"]
    | "soil"
    | "water"
    | "buoyancy"
    | "temperature"
    | "custom";
  value_type: "fixed" | "reference_range" | "calculated" | "project_defined";
  recommended_min?: number;
  recommended_default?: number;
  recommended_max?: number;
  adopted_value: number;
  unit: string;
  direction?: LoadItem["direction"];
  source_reference: string;
  confirmed: boolean;
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
  material?: "steel" | "concrete" | "timber";
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
  status:
    | "completed"
    | "passed"
    | "failed"
    | "incomplete"
    | "not_applicable";
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
  result_class?: "quick_estimate" | "professional_check";
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
  result_class?: "quick_estimate" | "professional_check";
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
  disclaimer: string;
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
  confirmation_required: boolean;
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
