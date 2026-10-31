import type { FoundationTypeDefinition, MemberTypeDefinition, ProjectSiteProfile, RoofAssembly } from "@/lib/types";

// Reference data and initial values of the pergola workbench. All entries are
// scheme references (verification_status "unverified"), not verified data.

export type SoilPreset = {
  id: string;
  title: string;
  range: [number, number];
  adopted: number;
  /** Lower bound of GB 50007-2011 table 6.7.5-2 for the soil class. */
  friction: number;
  description: string;
  risk: string;
};
export type SectionDraft = {
  family: "RHS" | "SHS" | "H";
  h: number;
  b: number;
  tw: number;
  tf: number;
};

export type AnalysisResult = {
  workflow_status: "ready" | "incomplete" | "failed";
  snapshot_id?: number | null;
  structural_analysis: {
    status: string;
    reactions: unknown[];
    balance_checks: Array<{
      case?: string;
      residual_kn?: number[];
      balanced?: boolean;
    }>;
  };
  member_checks?: {
    status: string;
    items: Array<{
      member_id?: string;
      status?: string;
      utilization?: number | null;
      reason?: string;
      controlling_case?: string;
      formula_source?: string;
    }>;
  };
  connection_checks: {
    status: string;
    items: Array<{
      connection_id?: string;
      mark?: string;
      node_id?: string;
      status?: string;
      issue_code?: string;
      failed_checks?: string[];
    }>;
  };
  foundation_checks: {
    status: string;
    items: Array<{
      foundation_id?: string;
      mark?: string;
      status?: string;
      failed_checks?: string[];
      pending_checks?: string[];
    }>;
  };
  buckling_analysis?: { status: string; factors: number[] };
  trace: {
    unsupported_capabilities: string[];
    formulas?: Array<{ topic?: string; source?: string }>;
  };
};

export const SOIL_PRESETS: SoilPreset[] = [
  {
    id: "fill",
    title: "填土",
    range: [60, 100],
    adopted: 60,
    friction: 0.20,
    description: "经压实并确认均匀性的人工填土方案参考。",
    risk: "均匀性和压实质量不确定，沉降风险较高。",
  },
  {
    id: "soft-clay",
    title: "软塑黏土",
    range: [60, 100],
    adopted: 60,
    friction: 0.20,
    description: "含水量较高、手捏易变形的黏性土。",
    risk: "通常由沉降控制，必须谨慎采用。",
  },
  {
    id: "plastic-clay",
    title: "可塑黏土",
    range: [100, 180],
    adopted: 100,
    friction: 0.25,
    description: "一般黏性土方案参考档。",
    risk: "需核对含水状态和压缩性。",
  },
  {
    id: "silt",
    title: "粉土",
    range: [100, 180],
    adopted: 100,
    friction: 0.30,
    description: "粉粒含量较高的土层。",
    risk: "地下水与振动可能显著影响承载表现。",
  },
  {
    id: "loose-sand",
    title: "松散砂土",
    range: [80, 140],
    adopted: 80,
    friction: 0.30,
    description: "颗粒松散、密实度较低的砂土。",
    risk: "需核对液化和地下水条件。",
  },
  {
    id: "medium-sand",
    title: "中密砂土",
    range: [160, 260],
    adopted: 160,
    friction: 0.40,
    description: "密实度中等的砂土方案参考档。",
    risk: "需由勘察确认密实度和液化判别。",
  },
  {
    id: "dense-sand",
    title: "密实砂土",
    range: [240, 400],
    adopted: 240,
    friction: 0.40,
    description: "密实度较高的砂土方案参考档。",
    risk: "实际采用值仍以勘察报告为准。",
  },
  {
    id: "strong-rock",
    title: "强风化岩",
    range: [300, 800],
    adopted: 300,
    friction: 0.40,
    description: "风化明显但仍保留岩体结构的持力层。",
    risk: "应确认风化差异和持力层连续性。",
  },
  {
    id: "medium-rock",
    title: "中风化岩",
    range: [800, 3000],
    adopted: 800,
    friction: 0.40,
    description: "岩体较完整的方案参考档。",
    risk: "需核对岩体完整性和局部破碎带。",
  },
];

export const INITIAL_REPORT = {
  name: "",
  date: "",
  bearing: 120,
  modulus: 8,
  layerThickness: 6,
  unitWeight: 18,
  settlementFactor: 1.0,
  settlementLimit: 30,
  construction: -1.2,
  service: -0.8,
  antifloat: -0.5,
  friction: 0.25,
};

export const INITIAL_SITE_PROFILE: ProjectSiteProfile = {
  profile_version: "1.1",
  completed_conditions: [],
  region_preset: null,
  recurrence_period_years: 50,
  basic_wind_pressure_kpa: null,
  basic_snow_pressure_kpa: null,
  terrain_category: "B",
  structure_shape: "roof",
  roof_form: "double_slope",
  seismic_level: null,
  catalog_versions: {
    climate_regions: "zhejiang-regions-2026.1-unverified",
    seismic: "seismic-cn-2026.1-unverified",
  },
};

export const MEMBER_TYPES: MemberTypeDefinition[] = [
  {
    id: "x-main",
    mark_prefix: "X-M",
    title: "X向主梁",
    role: "beam",
    material_grade: "Q355B",
    section_id: "RHS-250x150x8",
    orientation: "strong_axis",
    end_release: "rigid",
  },
  {
    id: "y-main",
    mark_prefix: "Y-M",
    title: "Y向主梁",
    role: "beam",
    material_grade: "Q355B",
    section_id: "RHS-250x150x8",
    orientation: "strong_axis",
    end_release: "rigid",
  },
  {
    id: "secondary",
    mark_prefix: "S",
    title: "次梁",
    role: "beam",
    material_grade: "Q355B",
    section_id: "RHS-180x100x6",
    orientation: "strong_axis",
    end_release: "rigid",
  },
  {
    id: "purlin",
    mark_prefix: "P",
    title: "檩条",
    role: "purlin",
    material_grade: "Q355B",
    section_id: "RHS-120x60x4",
    orientation: "strong_axis",
    end_release: "pinned",
  },
  {
    id: "joist",
    mark_prefix: "J",
    title: "龙骨",
    role: "purlin",
    material_grade: "Q235B",
    section_id: "RHS-80x40x3",
    orientation: "strong_axis",
    end_release: "pinned",
  },
  {
    id: "column",
    mark_prefix: "C",
    title: "柱",
    role: "column",
    material_grade: "Q355B",
    section_id: "SHS-200x8",
    orientation: "strong_axis",
    end_release: "rigid",
  },
  {
    id: "brace",
    mark_prefix: "BR",
    title: "支撑",
    role: "brace",
    material_grade: "Q235B",
    section_id: "SHS-80x4",
    orientation: "strong_axis",
    end_release: "pinned",
  },
];

export const FOUNDATION_TYPES: FoundationTypeDefinition[] = [
  {
    id: "foundation-a",
    mark: "F-A",
    title: "一般柱下阶形基础",
    form_id: "spread-stepped",
    length_m: 1.8,
    width_m: 1.5,
    thickness_mm: 450,
    embedment_m: 1.1,
    concrete_grade: "C30",
    rebar_grade: "HRB400",
    bottom_x: "Φ14@150",
    bottom_y: "Φ12@150",
    pedestal: {
      enabled: true,
      auto_enabled: true,
      length_mm: 500,
      width_mm: 500,
      clear_height_mm: 650,
      top_elevation_m: 0,
      bottom_elevation_m: -0.65,
      concrete_grade: "C30",
      cover_mm: 40,
      longitudinal_bar_count_x: 2,
      longitudinal_bar_count_y: 2,
      longitudinal_bar_diameter_mm: 16,
      stirrup_diameter_mm: 8,
      stirrup_spacing_mm: 150,
      confinement_spacing_mm: 90,
      dowel_anchorage_mm: 700,
      splice_type: "lap",
      top_local_reinforcement: true,
    },
  },
  {
    id: "foundation-b",
    mark: "F-B",
    title: "端柱锥形基础",
    form_id: "spread-tapered",
    length_m: 2.1,
    width_m: 1.6,
    thickness_mm: 500,
    embedment_m: 1.2,
    concrete_grade: "C30",
    rebar_grade: "HRB400",
    bottom_x: "Φ16@150",
    bottom_y: "Φ14@150",
    pedestal: {
      enabled: true,
      auto_enabled: true,
      length_mm: 550,
      width_mm: 500,
      clear_height_mm: 700,
      top_elevation_m: 0,
      bottom_elevation_m: -0.7,
      concrete_grade: "C30",
      cover_mm: 40,
      longitudinal_bar_count_x: 3,
      longitudinal_bar_count_y: 2,
      longitudinal_bar_diameter_mm: 16,
      stirrup_diameter_mm: 8,
      stirrup_spacing_mm: 150,
      confinement_spacing_mm: 90,
      dowel_anchorage_mm: 700,
      splice_type: "lap",
      top_local_reinforcement: true,
    },
  },
];

export const ROOF_ASSEMBLIES: RoofAssembly[] = [
  {
    id: "none",
    title: "无顶部覆盖",
    cover_type: "none",
    layers: [],
    total_dead_load_kn_m2: 0,
    reference_range_kn_m2: [0, 0],
    source_reference: "无覆盖时不生成屋面恒载、检修荷载和屋面雪荷载",
    verification_status: "unverified",
  },
  {
    id: "louver",
    title: "百叶 / 格栅",
    cover_type: "louver",
    layers: [{ name: "金属百叶及连接", surface_weight_kn_m2: 0.15 }],
    total_dead_load_kn_m2: 0.15,
    reference_range_kn_m2: [0.1, 0.3],
    source_reference: "方案参考，按厂家资料复核",
    verification_status: "unverified",
  },
  {
    id: "glass",
    title: "夹胶玻璃",
    cover_type: "glass",
    layers: [{ name: "玻璃与连接", surface_weight_kn_m2: 0.4 }],
    total_dead_load_kn_m2: 0.4,
    reference_range_kn_m2: [0.35, 0.75],
    source_reference: "方案参考，按玻璃构造复核",
    verification_status: "unverified",
  },
  {
    id: "aluminum",
    title: "铝板",
    cover_type: "aluminum",
    layers: [{ name: "铝板与龙骨", surface_weight_kn_m2: 0.25 }],
    total_dead_load_kn_m2: 0.25,
    reference_range_kn_m2: [0.2, 0.45],
    source_reference: "方案参考，按深化构造复核",
    verification_status: "unverified",
  },
  {
    id: "steel",
    title: "压型钢板",
    cover_type: "steel",
    layers: [{ name: "钢板与连接", surface_weight_kn_m2: 0.18 }],
    total_dead_load_kn_m2: 0.18,
    reference_range_kn_m2: [0.12, 0.35],
    source_reference: "方案参考，按板型复核",
    verification_status: "unverified",
  },
  {
    id: "polycarbonate",
    title: "阳光板",
    cover_type: "polycarbonate",
    layers: [{ name: "阳光板与龙骨", surface_weight_kn_m2: 0.16 }],
    total_dead_load_kn_m2: 0.16,
    reference_range_kn_m2: [0.1, 0.3],
    source_reference: "方案参考，按厂家资料复核",
    verification_status: "unverified",
  },
  {
    id: "timber",
    title: "木构覆盖",
    cover_type: "timber",
    layers: [{ name: "木面层与连接", surface_weight_kn_m2: 0.35 }],
    total_dead_load_kn_m2: 0.35,
    reference_range_kn_m2: [0.25, 0.7],
    source_reference: "方案参考，按树种和厚度复核",
    verification_status: "unverified",
  },
];

export const SITE_PRESETS = {
  zhejiang_coastal: { title: "浙江沿海", wind: 0.85, snow: 0.45 },
  zhejiang_inland: { title: "浙江内陆", wind: 0.55, snow: 0.5 },
  zhejiang_mountain: { title: "浙江山区", wind: 0.6, snow: 0.65 },
  manual: { title: "其他地区手动输入", wind: 0, snow: 0 },
} as const;

export const DEFAULT_SECTIONS: Record<string, SectionDraft> = {
  "x-main": { family: "RHS", h: 250, b: 150, tw: 8, tf: 8 },
  "y-main": { family: "RHS", h: 250, b: 150, tw: 8, tf: 8 },
  secondary: { family: "RHS", h: 180, b: 100, tw: 6, tf: 6 },
  purlin: { family: "RHS", h: 120, b: 60, tw: 4, tf: 4 },
  joist: { family: "RHS", h: 80, b: 40, tw: 3, tf: 3 },
  column: { family: "SHS", h: 200, b: 200, tw: 8, tf: 8 },
  brace: { family: "SHS", h: 80, b: 80, tw: 4, tf: 4 },
};

/** Workbench roof choice -> backend roof assembly catalog id. */
export const ROOF_ASSEMBLY_CATALOG_IDS: Record<string, string> = {
  none: "none",
  louver: "louver-light",
  glass: "glass-canopy",
  aluminum: "aluminum-panel",
  steel: "steel-panel",
  polycarbonate: "polycarbonate",
  timber: "timber-cover",
};

export function roofAssemblyCatalogId(uiId: string): string {
  return ROOF_ASSEMBLY_CATALOG_IDS[uiId] ?? "steel-panel";
}

export function roofAssemblyUiId(catalogId: string | undefined): string | undefined {
  return Object.entries(ROOF_ASSEMBLY_CATALOG_IDS).find(([, value]) => value === catalogId)?.[0];
}
