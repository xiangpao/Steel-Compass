"use client";

import dynamic from "next/dynamic";
import { BarChart3, Box, Building2, ChevronRight, ClipboardCheck, CloudSnow, GitBranch, Grid2X2, MapPin, MousePointer2, PanelLeftClose, RefreshCw, Ruler, Save, Settings2, Split, Trees, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { PergolaPlanEditorV2, type OrthographicView, type WorkbenchSelection } from "@/components/pergola-plan-editor-v2";
import { api, errorMessage } from "@/lib/api";
import { ColumnBaseContactFields } from "@/components/column-base-contact-fields";
import type { CustomSectionDefinition, FoundationDesignSpecification, FoundationTypeDefinition, MemberTypeDefinition, Project, ProjectGeotechnicalProfile, ProjectSiteProfile, RoofAssembly, SceneGeometryProfile } from "@/lib/types";

const SceneModelPreview = dynamic(() => import("@/components/scene-model-preview").then((module) => module.SceneModelPreview), { ssr: false });

type Area = "library" | "conditions" | "model" | "loads" | "foundation" | "results";
function statusLabel(value?: string) {
  return ({ ready: "已完成计算", complete: "已完成计算", incomplete: "尚未完成", failed: "不通过",
    pass: "筛查通过", passed: "筛查通过", not_calculated: "未计算", capability_unavailable: "超出当前能力" } as Record<string, string>)[value ?? ""] ?? value ?? "未计算";
}
type SoilPreset = {
  id: string;
  title: string;
  range: [number, number];
  adopted: number;
  /** Lower bound of GB 50007-2011 table 6.7.5-2 for the soil class. */
  friction: number;
  description: string;
  risk: string;
};
type SectionDraft = {
  family: "RHS" | "SHS" | "H";
  h: number;
  b: number;
  tw: number;
  tf: number;
};
type WorkbenchMode = "qa" | "project";
type PergolaWorkbenchProps = {
  mode?: WorkbenchMode;
  projects?: Project[];
  onProjectsChange?: (projects: Project[]) => void;
};
type AnalysisResult = {
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

const SOIL_PRESETS: SoilPreset[] = [
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

const INITIAL_REPORT = {
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

const INITIAL_SITE_PROFILE: ProjectSiteProfile = {
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

const MEMBER_TYPES: MemberTypeDefinition[] = [
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

const FOUNDATION_TYPES: FoundationTypeDefinition[] = [
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

const ROOF_ASSEMBLIES: RoofAssembly[] = [
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

const SITE_PRESETS = {
  zhejiang_coastal: { title: "浙江沿海", wind: 0.85, snow: 0.45 },
  zhejiang_inland: { title: "浙江内陆", wind: 0.55, snow: 0.5 },
  zhejiang_mountain: { title: "浙江山区", wind: 0.6, snow: 0.65 },
  manual: { title: "其他地区手动输入", wind: 0, snow: 0 },
} as const;

const DEFAULT_SECTIONS: Record<string, SectionDraft> = {
  "x-main": { family: "RHS", h: 250, b: 150, tw: 8, tf: 8 },
  "y-main": { family: "RHS", h: 250, b: 150, tw: 8, tf: 8 },
  secondary: { family: "RHS", h: 180, b: 100, tw: 6, tf: 6 },
  purlin: { family: "RHS", h: 120, b: 60, tw: 4, tf: 4 },
  joist: { family: "RHS", h: 80, b: 40, tw: 3, tf: 3 },
  column: { family: "SHS", h: 200, b: 200, tw: 8, tf: 8 },
  brace: { family: "SHS", h: 80, b: 80, tw: 4, tf: 4 },
};

function roofHeight(x: number, y: number, xs: number[], ys: number[], directionDeg: number, ratio: number, leftSlope: number, rightSlope: number, base = 3) {
  const direction = (directionDeg * Math.PI) / 180;
  const normal = { x: -Math.sin(direction), y: Math.cos(direction) };
  const projections = xs.flatMap((px) => ys.map((py) => px * normal.x + py * normal.y));
  const min = Math.min(...projections);
  const max = Math.max(...projections);
  const ridge = min + (max - min) * ratio;
  const value = x * normal.x + y * normal.y;
  return value <= ridge ? base + Math.tan((leftSlope * Math.PI) / 180) * (value - min) : base + Math.tan((rightSlope * Math.PI) / 180) * (max - value);
}

function initialGeometry(): SceneGeometryProfile {
  const xs = [0, 4, 8];
  const ys = [0, 3, 6];
  const nodes: SceneGeometryProfile["nodes"] = [];
  xs.forEach((x, xi) =>
    ys.forEach((y, yi) => {
      nodes.push({
        id: `B-${xi + 1}-${yi + 1}`,
        x_m: x,
        y_m: y,
        z_m: 0,
        support: "none",
        column_top: false,
      });
      nodes.push({
        id: `T-${xi + 1}-${yi + 1}`,
        x_m: x,
        y_m: y,
        z_m: roofHeight(x, y, xs, ys, 0, 0.5, 8, 8),
        support: "none",
        column_top: true,
      });
    }),
  );
  const members: SceneGeometryProfile["members"] = [];
  const member_instances: NonNullable<SceneGeometryProfile["member_instances"]> = [];
  xs.forEach((_x, xi) =>
    ys.forEach((_y, yi) => {
      const id = `C-${xi + 1}-${yi + 1}`;
      members.push({
        id,
        start_node_id: `B-${xi + 1}-${yi + 1}`,
        end_node_id: `T-${xi + 1}-${yi + 1}`,
        role: "column",
        group_id: "column",
        behavior: "frame",
        end_release: "rigid",
      });
      member_instances.push({
        member_id: id,
        member_type_id: "column",
        mark: `C${String(member_instances.filter((item) => item.member_type_id === "column").length + 1).padStart(2, "0")}`,
        source: "type",
      });
    }),
  );
  ys.forEach((_y, yi) =>
    xs.slice(0, -1).forEach((_x, xi) => {
      const id = `BX-${xi + 1}-${yi + 1}`;
      members.push({
        id,
        start_node_id: `T-${xi + 1}-${yi + 1}`,
        end_node_id: `T-${xi + 2}-${yi + 1}`,
        role: "beam",
        group_id: "x-main",
        behavior: "frame",
        end_release: "rigid",
      });
      member_instances.push({
        member_id: id,
        member_type_id: "x-main",
        mark: `X-M${String(member_instances.filter((item) => item.member_type_id === "x-main").length + 1).padStart(2, "0")}`,
        source: "type",
      });
    }),
  );
  xs.forEach((_x, xi) =>
    ys.slice(0, -1).forEach((_y, yi) => {
      const id = `BY-${xi + 1}-${yi + 1}`;
      members.push({
        id,
        start_node_id: `T-${xi + 1}-${yi + 1}`,
        end_node_id: `T-${xi + 1}-${yi + 2}`,
        role: "beam",
        group_id: "y-main",
        behavior: "frame",
        end_release: "rigid",
      });
      member_instances.push({
        member_id: id,
        member_type_id: "y-main",
        mark: `Y-M${String(member_instances.filter((item) => item.member_type_id === "y-main").length + 1).padStart(2, "0")}`,
        source: "type",
      });
    }),
  );
  const supports = xs.flatMap((_x, xi) =>
    ys.map((_y, yi) => ({
      id: `SUP-B-${xi + 1}-${yi + 1}`,
      node_id: `B-${xi + 1}-${yi + 1}`,
      restraint: "fixed" as const,
      foundation_id: `FI-${xi + 1}-${yi + 1}`,
    })),
  );
  const foundation_instances = supports.map((support, index) => {
    const isEnd = index === 0 || index === supports.length - 1;
    const type = isEnd ? FOUNDATION_TYPES[1] : FOUNDATION_TYPES[0];
    const typeIndex = supports.slice(0, index + 1).filter((_item, itemIndex) => (itemIndex === 0 || itemIndex === supports.length - 1) === isEnd).length;
    return {
      id: support.foundation_id!,
      support_id: support.id,
      foundation_type_id: type.id,
      mark: `${type.mark}-${String(typeIndex).padStart(2, "0")}`,
      column_member_id: `C-${Math.floor(index / ys.length) + 1}-${(index % ys.length) + 1}`,
    };
  });
  const roof_surfaces: SceneGeometryProfile["roof_surfaces"] = [];
  xs.slice(0, -1).forEach((_x, xi) =>
    ys.slice(0, -1).forEach((_y, yi) =>
      roof_surfaces.push({
        id: `R-${xi + 1}-${yi + 1}`,
        node_ids: [`T-${xi + 1}-${yi + 1}`, `T-${xi + 2}-${yi + 1}`, `T-${xi + 2}-${yi + 2}`, `T-${xi + 1}-${yi + 2}`],
        form: "double_slope",
        load_path_group_ids: ["x-main", "y-main"],
      }),
    ),
  );
  const beamColumnConnections: NonNullable<SceneGeometryProfile["connection_instances"]> = [];
  nodes
    .filter((node) => node.id.startsWith("T-"))
    .forEach((node) => {
      const column = members.find((member) => member.role === "column" && member.end_node_id === node.id);
      if (!column) return;
      members
        .filter((member) => member.role !== "column" && (member.start_node_id === node.id || member.end_node_id === node.id))
        .forEach((beam) => {
          const index = beamColumnConnections.length + 1;
          beamColumnConnections.push({
            id: `JBC-${index}`,
            mark: `J-B-${String(index).padStart(2, "0")}`,
            connection_type_id: "joint-beam-column",
            node_id: node.id,
            member_ids: [column.id, beam.id],
            status: "defined",
          });
        });
    });
  return {
    profile_version: "2.3",
    layout_mode: "free_plan",
    axes: [
      { id: "X", direction: "x", positions_m: xs },
      { id: "Y", direction: "y", positions_m: ys },
    ],
    nodes,
    members,
    member_types: MEMBER_TYPES,
    member_instances,
    supports,
    foundation_types: FOUNDATION_TYPES.map((item) => ({
      ...item,
      cover_mm: item.cover_mm ?? 50,
      steps:
        item.steps ??
        (item.form_id === "spread-stepped"
          ? [
              {
                length_m: Math.max(item.length_m - 0.5, 0.3),
                width_m: Math.max(item.width_m - 0.5, 0.3),
                height_mm: 250,
              },
            ]
          : []),
      tapered_top_length_m: item.tapered_top_length_m ?? (item.form_id === "spread-tapered" ? 0.6 : null),
      tapered_top_width_m: item.tapered_top_width_m ?? (item.form_id === "spread-tapered" ? 0.6 : null),
      tapered_height_mm: item.tapered_height_mm ?? (item.form_id === "spread-tapered" ? 300 : null),
    })),
    foundation_instances,
    roof_surfaces,
    object_marks: [],
    work_planes: [
      { id: "roof", kind: "plan", elevation_m: 3 },
      { id: "x-elevation", kind: "x_elevation" },
      { id: "y-elevation", kind: "y_elevation" },
    ],
    double_slope_rule: {
      ridge_direction_deg: 0,
      ridge_offset_ratio: 0.5,
      left_slope_deg: 8,
      right_slope_deg: 8,
    },
    connection_types: [
      {
        id: "joint-column-base",
        mark: "J-A",
        title: "钢管柱脚底板＋锚栓",
        family: "column_base",
        behavior: "rigid",
        supported_section_families: ["SHS", "RHS", "H", "I"],
        parameters: { weld_mm: 8 },
        verification_status: "unverified",
      },
      {
        id: "joint-beam-column",
        mark: "J-B",
        title: "矩形管梁柱全周焊接节点",
        family: "beam_column",
        behavior: "rigid",
        supported_section_families: ["SHS", "RHS"],
        parameters: {
          connection_form: "rhs_full_perimeter_weld",
          weld_throat_mm: 8,
          stiffener_thickness_mm: 8,
        },
        verification_status: "unverified",
      },
    ],
    connection_instances: [
      ...supports.map((support, index) => ({
        id: `JCB-${index + 1}`,
        mark: `J-A-${String(index + 1).padStart(2, "0")}`,
        connection_type_id: "joint-column-base",
        node_id: support.node_id,
        member_ids: [foundation_instances[index].column_member_id!],
        status: "defined" as const,
      })),
      ...beamColumnConnections,
    ],
    column_bases: supports.map((support, index) => ({
      id: `CB-${index + 1}`,
      column_member_id: foundation_instances[index].column_member_id!,
      support_id: support.id,
      connection_instance_id: `JCB-${index + 1}`,
      base_plate_length_mm: 360,
      base_plate_width_mm: 360,
      base_plate_thickness_mm: 24,
      anchor_grade: "5.8",
      anchor_diameter_mm: 24,
      anchor_count: 4,
      anchor_embedment_mm: 600,
      anchor_spacing_mm: 260,
      anchor_edge_mm: 50,
      anchor_head_diameter_mm: 60,
      anchor_supplementary_reinforcement_area_mm2: 0,
      anchor_cracked_concrete: true,
      weld_throat_mm: 8,
      concrete_bearing_capacity_mpa: 10,
      grout_thickness_mm: 30,
    })),
    roof_elevation: {
      kind: "double_slope",
      datum_height_m: 3,
      slope_deg: 8,
      opposite_slope_deg: 8,
      direction_deg: 0,
      ridge_start: [0, 3],
      ridge_end: [8, 3],
    },
    plan_boundary: {
      outer_points: [
        { id: "BP-1", x_m: 0, y_m: 0 },
        { id: "BP-2", x_m: 8, y_m: 0 },
        { id: "BP-3", x_m: 8, y_m: 6 },
        { id: "BP-4", x_m: 0, y_m: 6 },
      ],
      outer_segments: [
        {
          id: "BS-1",
          start_point_id: "BP-1",
          end_point_id: "BP-2",
          kind: "line",
        },
        {
          id: "BS-2",
          start_point_id: "BP-2",
          end_point_id: "BP-3",
          kind: "line",
        },
        {
          id: "BS-3",
          start_point_id: "BP-3",
          end_point_id: "BP-4",
          kind: "line",
        },
        {
          id: "BS-4",
          start_point_id: "BP-4",
          end_point_id: "BP-1",
          kind: "line",
        },
      ],
      source: "QA 亭廊初始轴网",
    },
    roof_openings: [],
    roof_load_zones: roof_surfaces.map((surface) => ({
      id: `Z-${surface.id}`,
      surface_id: surface.id,
      boundary_node_ids: surface.node_ids,
      roof_assembly_id: "steel-panel",
      load_path_group_ids: surface.load_path_group_ids,
    })),
    source: "QA 亭廊工作台 2.3",
  };
}

function typeLetter(index: number) {
  return String.fromCharCode(65 + index);
}

export function PergolaWorkbenchV2({ mode = "qa", projects = [], onProjectsChange }: PergolaWorkbenchProps) {
  const shellRef = useRef<HTMLElement>(null);
  const [geometry, setGeometry] = useState<SceneGeometryProfile>(() => initialGeometry());
  const [selection, setSelection] = useState<WorkbenchSelection>(null);
  const [area, setArea] = useState<Area>("model");
  const [view, setView] = useState<OrthographicView>("plan");
  const [message, setMessage] = useState("选择图面对象后，左侧只显示该对象的必要属性。");
  const [canvasMessage, setCanvasMessage] = useState("");
  const [workElevation, setWorkElevation] = useState(3.2);
  const [activeMemberTypeId, setActiveMemberTypeId] = useState("secondary");
  const [sectionDrafts, setSectionDrafts] = useState<Record<string, SectionDraft>>(DEFAULT_SECTIONS);
  const [soilPresetId, setSoilPresetId] = useState("plastic-clay");
  const [geoStage, setGeoStage] = useState<"scheme_estimate" | "project_check">("scheme_estimate");
  const [report, setReport] = useState(INITIAL_REPORT);
  const [mobilePane, setMobilePane] = useState<"property" | "2d" | "3d">("2d");
  const [splitPercent, setSplitPercent] = useState(55);
  const [draggingSplit, setDraggingSplit] = useState(false);
  const [roofAssemblyId, setRoofAssemblyId] = useState("steel");
  const [maintenanceCategory, setMaintenanceCategory] = useState<"none" | "maintenance" | "walkway" | "occupied" | "custom">("maintenance");
  const [maintenanceLoad, setMaintenanceLoad] = useState(0.5);
  const [siteProfile, setSiteProfile] = useState<ProjectSiteProfile>(INITIAL_SITE_PROFILE);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(projects[0]?.id ?? null);
  const [newProjectName, setNewProjectName] = useState("");
  const [sceneInstanceId, setSceneInstanceId] = useState<number | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisSnapshotId, setAnalysisSnapshotId] = useState<number | null>(null);
  const [serverBusy, setServerBusy] = useState(false);
  const savedGeotechnical = useRef<{ profile: ProjectGeotechnicalProfile; ui: string } | null>(null);
  // Bumped whenever inputs change; an analysis response for an older input
  // generation is discarded instead of being shown as the current result.
  const inputGeneration = useRef(0);

  useEffect(() => {
    inputGeneration.current += 1;
    setAnalysisResult(null);
    setAnalysisSnapshotId(null);
  }, [geometry, siteProfile, sectionDrafts, soilPresetId, geoStage, report,
      roofAssemblyId, maintenanceCategory, maintenanceLoad]);

  useEffect(() => {
    if (mode !== "qa") return;
    const saved = window.localStorage.getItem("steel-compass:qa:pergola-workbench-v2");
    if (!saved) return;
    try {
      const candidate = JSON.parse(saved) as SceneGeometryProfile;
      if (candidate.profile_version !== "2.3") {
        setMessage("检测到旧 Geometry 草稿；为避免升级孤立对象，本次使用干净 2.3 模型，可在场景库选择重建。");
        return;
      }
      const connected = new Set(candidate.members.flatMap((item) => [item.start_node_id, item.end_node_id]));
      if (candidate.nodes.some((item) => !connected.has(item.id) && !(candidate.supports ?? []).some((support) => support.node_id === item.id))) {
        setMessage("旧 QA 草稿含孤立节点，已阻止自动加载；请在场景库重建或先修复旧草稿。");
        return;
      }
      setGeometry(candidate);
    } catch {
      setMessage("QA 草稿无法读取，已使用干净初始模型。");
    }
  }, [mode]);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem("steel-compass:qa:workbench-split"));
    if (saved >= 30 && saved <= 70) setSplitPercent(saved);
  }, []);

  useEffect(() => {
    if (!draggingSplit) return;
    const move = (event: PointerEvent) => {
      const shell = shellRef.current;
      if (!shell) return;
      const rect = shell.getBoundingClientRect();
      const contentLeft = rect.left + 56 + 300;
      const available = Math.max(1, rect.right - contentLeft);
      const value = Math.min(70, Math.max(30, ((event.clientX - contentLeft) / available) * 100));
      setSplitPercent(value);
    };
    const finish = () => setDraggingSplit(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish, { once: true });
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
    };
  }, [draggingSplit]);

  useEffect(() => {
    window.localStorage.setItem("steel-compass:qa:workbench-split", String(splitPercent));
  }, [splitPercent]);

  useEffect(() => {
    if (mode === "qa") window.localStorage.setItem("steel-compass:qa:pergola-workbench-v2", JSON.stringify(geometry));
  }, [geometry, mode]);

  useEffect(() => {
    if (mode !== "project" || selectedProjectId !== null || projects.length === 0) return;
    setSelectedProjectId(projects[0].id);
  }, [mode, projects, selectedProjectId]);

  useEffect(() => {
    if (mode !== "project" || selectedProjectId === null) return;
    let cancelled = false;
    Promise.all([
      api<
        Array<{
          id: number;
          family_id: string;
          variant_id: string;
          archived: boolean;
        }>
      >(`/api/v2/projects/${selectedProjectId}/scene-instances`),
      api<ProjectSiteProfile | null>(`/api/v2/projects/${selectedProjectId}/site-profile`),
      api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${selectedProjectId}/custom-sections`),
      api<ProjectGeotechnicalProfile | null>(`/api/v2/projects/${selectedProjectId}/geotechnical-profile`),
    ])
      .then(async ([instances, profile, sectionCatalog, geotechnical]) => {
        if (cancelled) return;
        // Reset first so a project without saved data never inherits the
        // previous project's conditions or model.
        setSiteProfile(profile ?? INITIAL_SITE_PROFILE);
        setReport(INITIAL_REPORT);
        setGeoStage("scheme_estimate");
        setSoilPresetId("plastic-clay");
        setGeometry(initialGeometry());
        setSectionDrafts(DEFAULT_SECTIONS);
        savedGeotechnical.current = null;
        if (geotechnical) {
          const soil = SOIL_PRESETS.find(item => item.id === geotechnical.regional_hint_id || item.title === geotechnical.confirmed_soil_class)?.id ?? "plastic-clay";
          const layer = geotechnical.settlement_layers?.[0];
          const restoredReport = {
            name: geotechnical.report_name ?? "", date: geotechnical.report_date ?? "",
            bearing: geotechnical.bearing_capacity_kpa,
            modulus: geotechnical.deformation_modulus_mpa ?? layer?.compression_modulus_mpa ?? 0,
            layerThickness: layer?.thickness_m ?? 0, unitWeight: layer?.unit_weight_kn_m3 ?? 18,
            settlementFactor: geotechnical.settlement_correction_factor ?? 1,
            settlementLimit: geotechnical.settlement_limit_mm ?? 0,
            construction: geotechnical.groundwater.construction_level_m ?? 0,
            service: geotechnical.groundwater.service_level_m ?? 0,
            antifloat: geotechnical.groundwater.antifloat_level_m ?? 0,
            friction: geotechnical.base_friction_coefficient ?? 0.25,
          };
          setGeoStage(geotechnical.stage); setSoilPresetId(soil); setReport(restoredReport);
          savedGeotechnical.current = { profile: geotechnical,
            ui: JSON.stringify({ report: restoredReport, soilPresetId: soil, geoStage: geotechnical.stage }) };
        }
        const instance = instances.find((item) => !item.archived && item.family_id === "pergola-pavilion" && item.variant_id === "guided-grid");
        if (!instance) {
          setSceneInstanceId(null);
          return;
        }
        setSceneInstanceId(instance.id);
        const savedGeometry = await api<SceneGeometryProfile | null>(`/api/v2/projects/${selectedProjectId}/scene-instances/${instance.id}/geometry`);
        if (!cancelled && savedGeometry?.profile_version === "2.3") {
          setGeometry(savedGeometry);
          setSectionDrafts((current) => {
            const next = { ...current };
            for (const type of savedGeometry.member_types ?? []) {
              const section = sectionCatalog.items.find((item) => item.id === type.section_id);
              if (!section || !["SHS", "RHS", "H"].includes(section.family)) continue;
              next[type.id] = {
                family: section.family as SectionDraft["family"],
                h: section.dimensions.h_mm ?? 100,
                b: section.dimensions.b_mm ?? section.dimensions.h_mm ?? 100,
                tw: section.dimensions.t_mm ?? section.dimensions.tw_mm ?? 4,
                tf: section.dimensions.tf_mm ?? section.dimensions.t_mm ?? 4,
              };
            }
            return next;
          });
          const savedAssembly = savedGeometry.roof_load_zones?.[0]?.roof_assembly_id;
          const uiAssembly = Object.entries({
            none: "none",
            louver: "louver-light",
            glass: "glass-canopy",
            aluminum: "aluminum-panel",
            steel: "steel-panel",
            polycarbonate: "polycarbonate",
            timber: "timber-cover",
          }).find(([, value]) => value === savedAssembly)?.[0];
          if (uiAssembly) setRoofAssemblyId(uiAssembly);
        }
      })
      .catch((error) => {
        if (!cancelled) setMessage(errorMessage(error));
      });
    return () => {
      cancelled = true;
    };
  }, [mode, selectedProjectId]);

  const selectedMember = selection?.kind === "member" ? geometry.members.find((item) => item.id === selection.id) : null;
  const selectedMemberInstance = selectedMember ? geometry.member_instances?.find((item) => item.member_id === selectedMember.id) : null;
  const selectedMemberType = selectedMemberInstance ? geometry.member_types?.find((item) => item.id === selectedMemberInstance.member_type_id) : null;
  const selectedNode = selection?.kind === "node" ? geometry.nodes.find((item) => item.id === selection.id) : null;
  const selectedFoundation = selection?.kind === "foundation" ? geometry.foundation_instances?.find((item) => item.id === selection.id) : null;
  const selectedFoundationType = selectedFoundation ? geometry.foundation_types?.find((item) => item.id === selectedFoundation.foundation_type_id) : null;
  const selectedSupport = selectedFoundation ? geometry.supports?.find((item) => item.id === selectedFoundation.support_id) : null;
  const selectedSupportNode = selectedSupport ? geometry.nodes.find((item) => item.id === selectedSupport.node_id) : null;
  const selectedColumnBase = selectedSupport ? geometry.column_bases?.find((item) => item.support_id === selectedSupport.id) : null;
  const selectedDirectSupport = selection?.kind === "support" ? geometry.supports?.find((item) => item.id === selection.id) : null;
  const selectedSoil = SOIL_PRESETS.find((item) => item.id === soilPresetId)!;
  const selectedRoofAssembly = ROOF_ASSEMBLIES.find((item) => item.id === roofAssemblyId)!;

  const foundationsBySupportId = useMemo(
    () =>
      Object.fromEntries(
        (geometry.foundation_instances ?? []).flatMap((instance) => {
          const type = geometry.foundation_types?.find((item) => item.id === instance.foundation_type_id);
          if (!type) return [];
          const specification: FoundationDesignSpecification = {
            node_id: instance.id,
            foundation_system_id: "spread",
            selection_source: "user_locked",
            length_m: type.length_m,
            width_m: type.width_m,
            thickness_mm: type.thickness_mm,
            embedment_m: type.embedment_m,
            concrete_grade: type.concrete_grade,
            rebar_grade: type.rebar_grade,
            bar_diameter_mm: 14,
            bar_spacing_mm: 150,
            section_shape: type.form_id.includes("tapered") ? "tapered" : type.form_id.includes("stepped") ? "stepped" : "prismatic",
            steps: type.form_id.includes("stepped")
              ? [
                  {
                    length_m: Math.max(0.5, type.length_m - 0.5),
                    width_m: Math.max(0.5, type.width_m - 0.5),
                    height_mm: 250,
                  },
                ]
              : [],
            tapered_top_length_m: type.form_id.includes("tapered") ? 0.6 : null,
            tapered_top_width_m: type.form_id.includes("tapered") ? 0.6 : null,
            reinforcement: {
              bottom_x_diameter_mm: 14,
              bottom_x_spacing_mm: 150,
              bottom_y_diameter_mm: 12,
              bottom_y_spacing_mm: 150,
            },
            pedestal: type.pedestal
              ? {
                  enabled: type.pedestal.enabled,
                  length_mm: type.pedestal.length_mm,
                  width_mm: type.pedestal.width_mm,
                  height_mm: type.pedestal.clear_height_mm,
                  longitudinal_bar_count: (type.pedestal.longitudinal_bar_count_x ?? 0) * 2 + (type.pedestal.longitudinal_bar_count_y ?? 0) * 2,
                  longitudinal_bar_diameter_mm: type.pedestal.longitudinal_bar_diameter_mm,
                  stirrup_diameter_mm: type.pedestal.stirrup_diameter_mm,
                  stirrup_spacing_mm: type.pedestal.stirrup_spacing_mm,
                }
              : null,
            override_reason: "QA 工作台显式基础类型",
          };
          return [[instance.support_id, specification]];
        }),
      ),
    [geometry.foundation_instances, geometry.foundation_types],
  );

  function updateNode(id: string, values: Partial<SceneGeometryProfile["nodes"][number]>) {
    setGeometry((current) => ({
      ...current,
      nodes: current.nodes.map((item) => (item.id === id ? { ...item, ...values } : item)),
    }));
  }

  function updateMemberType(typeId: string, values: Partial<MemberTypeDefinition>) {
    const release = values.end_release === "pinned" ? { ux: false, uy: false, uz: false, rx: false, ry: true, rz: true } : values.end_release === "rigid" ? { ux: false, uy: false, uz: false, rx: false, ry: false, rz: false } : null;
    setGeometry((current) => ({
      ...current,
      member_types: (current.member_types ?? []).map((item) => (item.id === typeId ? { ...item, ...values } : item)),
      members:
        release === null && values.orientation === undefined
          ? current.members
          : current.members.map((item) =>
              item.group_id === typeId
                ? {
                    ...item,
                    ...(release === null ? {} : {
                      end_release: values.end_release!,
                      start_release: release,
                      end_release_dofs: release,
                    }),
                    ...(values.orientation === undefined || !item.design_parameters ? {} : {
                      design_parameters: {
                        ...item.design_parameters,
                        local_axis_rotation_deg: values.orientation === "weak_axis" ? 90 : 0,
                      },
                    }),
                  }
                : item,
            ),
    }));
  }

  function changeMemberAssignment(typeId: string) {
    if (!selectedMemberInstance || !selectedMember) return;
    const type = geometry.member_types?.find((item) => item.id === typeId);
    if (!type) return;
    const index = (geometry.member_instances ?? []).filter((item) => item.member_type_id === typeId).length + 1;
    setGeometry((current) => ({
      ...current,
      members: current.members.map((item) =>
        item.id === selectedMember.id
          ? {
              ...item,
              group_id: typeId,
              role: type.role,
              end_release: type.end_release,
              start_release:
                type.end_release === "pinned"
                  ? {
                      ux: false,
                      uy: false,
                      uz: false,
                      rx: false,
                      ry: true,
                      rz: true,
                    }
                  : {
                      ux: false,
                      uy: false,
                      uz: false,
                      rx: false,
                      ry: false,
                      rz: false,
                    },
              end_release_dofs:
                type.end_release === "pinned"
                  ? {
                      ux: false,
                      uy: false,
                      uz: false,
                      rx: false,
                      ry: true,
                      rz: true,
                    }
                  : {
                      ux: false,
                      uy: false,
                      uz: false,
                      rx: false,
                      ry: false,
                      rz: false,
                    },
            }
          : item,
      ),
      member_instances: (current.member_instances ?? []).map((item) =>
        item.member_id === selectedMember.id
          ? {
              ...item,
              member_type_id: typeId,
              mark: `${type.mark_prefix}${String(index).padStart(2, "0")}`,
            }
          : item,
      ),
    }));
    setMessage(`已将 ${selectedMemberInstance.mark} 改为 ${type.title}。`);
  }

  function updateRoof(values: Partial<NonNullable<SceneGeometryProfile["double_slope_rule"]>>) {
    const rule = {
      ...(geometry.double_slope_rule ?? {
        ridge_direction_deg: 0,
        ridge_offset_ratio: 0.5,
        left_slope_deg: 8,
        right_slope_deg: 8,
      }),
      ...values,
    };
    const topNodes = geometry.nodes.filter((item) => item.column_top || item.id.startsWith("T-"));
    const xs = topNodes.map((item) => item.x_m);
    const ys = topNodes.map((item) => item.y_m);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const center = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
    const angle = (rule.ridge_direction_deg * Math.PI) / 180;
    const length = Math.hypot(maxX - minX, maxY - minY) * 0.75;
    const ridgeStart: [number, number] = [center.x - Math.cos(angle) * length, center.y - Math.sin(angle) * length];
    const ridgeEnd: [number, number] = [center.x + Math.cos(angle) * length, center.y + Math.sin(angle) * length];
    setGeometry((current) => ({
      ...current,
      nodes: current.nodes.map((item) =>
        item.column_top || item.id.startsWith("T-")
          ? {
              ...item,
              z_m: roofHeight(item.x_m, item.y_m, xs, ys, rule.ridge_direction_deg, rule.ridge_offset_ratio, rule.left_slope_deg, rule.right_slope_deg),
            }
          : item,
      ),
      double_slope_rule: rule,
      roof_elevation: {
        kind: "double_slope",
        datum_height_m: 3,
        slope_deg: rule.left_slope_deg,
        opposite_slope_deg: rule.right_slope_deg,
        direction_deg: rule.ridge_direction_deg,
        ridge_start: ridgeStart,
        ridge_end: ridgeEnd,
      },
    }));
    setMessage(`双坡屋脊已旋转到 ${rule.ridge_direction_deg.toFixed(0)}°，构件编号保持不变。`);
  }

  function updateFoundationType(typeId: string, values: Partial<FoundationTypeDefinition>) {
    setGeometry((current) => ({
      ...current,
      foundation_types: (current.foundation_types ?? []).map((item) => {
        if (item.id !== typeId) return item;
        const merged = { ...item, ...values };
        if (values.form_id === "spread-stepped" && !merged.steps?.length)
          merged.steps = [
            {
              length_m: Math.max(merged.length_m - 0.5, 0.3),
              width_m: Math.max(merged.width_m - 0.5, 0.3),
              height_mm: 250,
            },
          ];
        if (values.form_id === "spread-tapered") {
          merged.tapered_top_length_m ??= 0.6;
          merged.tapered_top_width_m ??= 0.6;
          merged.tapered_height_mm ??= 300;
        }
        return merged;
      }),
    }));
  }

  function updatePedestal(typeId: string, values: Partial<NonNullable<FoundationTypeDefinition["pedestal"]>>) {
    setGeometry((current) => ({
      ...current,
      foundation_types: (current.foundation_types ?? []).map((item) =>
        item.id === typeId
          ? {
              ...item,
              pedestal: {
                enabled: false,
                auto_enabled: true,
                splice_type: "lap",
                top_local_reinforcement: false,
                ...(item.pedestal ?? {}),
                ...values,
              },
            }
          : item,
      ),
    }));
  }

  function updateColumnBase(values: Partial<NonNullable<SceneGeometryProfile["column_bases"]>[number]>) {
    if (!selectedColumnBase) return;
    setGeometry((current) => ({
      ...current,
      column_bases: (current.column_bases ?? []).map((item) => (item.id === selectedColumnBase.id ? { ...item, ...values } : item)),
    }));
  }

  function updateSupport(id: string, restraint: "pinned" | "fixed" | "spring") {
    setGeometry((current) => ({
      ...current,
      supports: (current.supports ?? []).map((item) =>
        item.id === id
          ? {
              ...item,
              restraint,
              restrained_dofs: restraint === "fixed" ? ["ux", "uy", "uz", "rx", "ry", "rz"] : restraint === "pinned" ? ["ux", "uy", "uz"] : [],
              spring_stiffness: restraint === "spring" ? { ux: 10000, uy: 10000, uz: 50000 } : {},
            }
          : item,
      ),
    }));
  }

  function detachFoundation() {
    if (!selectedFoundation || !selectedFoundationType) return;
    const nextIndex = geometry.foundation_types?.length ?? 0;
    const mark = `F-${typeLetter(nextIndex)}`;
    const id = `foundation-${typeLetter(nextIndex).toLowerCase()}`;
    setGeometry((current) => ({
      ...current,
      foundation_types: [
        ...(current.foundation_types ?? []),
        {
          ...selectedFoundationType,
          id,
          mark,
          title: `${selectedFoundationType.title}（独立调整）`,
        },
      ],
      foundation_instances: (current.foundation_instances ?? []).map((item) => (item.id === selectedFoundation.id ? { ...item, foundation_type_id: id, mark: `${mark}-01` } : item)),
    }));
    setMessage(`${selectedFoundation.mark} 已从原类型分离为 ${mark}。`);
  }

  function autoClassifyFoundations() {
    const types = geometry.foundation_types ?? [];
    const signature = (item: FoundationTypeDefinition) => [item.form_id, item.length_m, item.width_m, item.thickness_mm, item.embedment_m, item.concrete_grade, item.rebar_grade, item.bottom_x, item.bottom_y, item.top_x ?? null, item.top_y ?? null, item.cover_mm, JSON.stringify(item.steps ?? []), item.tapered_top_length_m, item.tapered_top_width_m, item.tapered_height_mm, JSON.stringify(item.pedestal ?? null)].join("|");
    const canonical = new Map<string, FoundationTypeDefinition>();
    types.forEach((item) => {
      if (!canonical.has(signature(item))) canonical.set(signature(item), item);
    });
    const kept = [...canonical.values()].map((item, index) => ({
      ...item,
      mark: `F-${typeLetter(index)}`,
    }));
    const map = new Map(types.map((item) => [item.id, kept.find((candidate) => signature(candidate) === signature(item))!]));
    const counters = new Map<string, number>();
    const instances = (geometry.foundation_instances ?? []).map((item) => {
      const target = map.get(item.foundation_type_id)!;
      const count = (counters.get(target.id) ?? 0) + 1;
      counters.set(target.id, count);
      return {
        ...item,
        foundation_type_id: target.id,
        mark: `${target.mark}-${String(count).padStart(2, "0")}`,
      };
    });
    setGeometry((current) => ({
      ...current,
      foundation_types: kept,
      foundation_instances: instances,
    }));
    setMessage(`基础已按几何、材料和配筋自动归为 ${kept.length} 类。`);
  }

  function completeBeamColumnConnections() {
    setGeometry((current) => {
      const typeId = "joint-beam-column";
      const connectionTypes = current.connection_types?.some((item) => item.id === typeId)
        ? (current.connection_types ?? [])
        : [
            ...(current.connection_types ?? []),
            {
              id: typeId,
              mark: "J-B",
              title: "矩形管梁柱全周焊接节点",
              family: "beam_column" as const,
              behavior: "rigid" as const,
              supported_section_families: ["SHS", "RHS"],
              parameters: {
                connection_form: "rhs_full_perimeter_weld",
                weld_throat_mm: 8,
                stiffener_thickness_mm: 8,
              },
              verification_status: "unverified" as const,
            },
          ];
      const existing = [...(current.connection_instances ?? [])];
      const signatures = new Set(existing.map((item) => `${item.node_id}:${[...item.member_ids].sort().join("+")}`));
      let nextIndex = existing.filter((item) => item.connection_type_id === typeId).length + 1;
      current.nodes.forEach((node) => {
        const connected = current.members.filter((member) => member.start_node_id === node.id || member.end_node_id === node.id);
        const column = connected.find((member) => member.role === "column");
        if (!column) return;
        connected
          .filter((member) => member.role !== "column")
          .forEach((beam) => {
            const signature = `${node.id}:${[column.id, beam.id].sort().join("+")}`;
            if (signatures.has(signature)) return;
            existing.push({
              id: `JBC-${nextIndex}`,
              mark: `J-B-${String(nextIndex).padStart(2, "0")}`,
              connection_type_id: typeId,
              node_id: node.id,
              member_ids: [column.id, beam.id],
              status: "defined",
            });
            signatures.add(signature);
            nextIndex += 1;
          });
      });
      return {
        ...current,
        connection_types: connectionTypes,
        connection_instances: existing,
      };
    });
    setMessage("已补齐可识别的矩形管梁柱连接实例；既有连接未被覆盖。");
  }

  function handleSelection(value: WorkbenchSelection) {
    setSelection(value);
    if (value?.kind === "foundation") setArea("foundation");
    else if (value) setArea("model");
  }

  function projectGeotechnicalProfile(): ProjectGeotechnicalProfile {
    if (savedGeotechnical.current?.ui === JSON.stringify({ report, soilPresetId, geoStage })) {
      return savedGeotechnical.current.profile;
    }
    if (geoStage === "project_check") {
      return {
        profile_version: "1.1",
        stage: "project_check",
        regional_hint_id: null,
        confirmed_soil_class: selectedSoil.title,
        bearing_capacity_kpa: report.bearing,
        bearing_capacity_source: `勘察报告：${report.name}`,
        deformation_modulus_mpa: report.modulus,
        compression_modulus_mpa: null,
        settlement_layers: [
          {
            id: "layer-1",
            name: "持力层及主要压缩层",
            thickness_m: report.layerThickness,
            compression_modulus_mpa: report.modulus,
            unit_weight_kn_m3: report.unitWeight,
            source: `勘察报告：${report.name}`,
          },
        ],
        settlement_correction_factor: report.settlementFactor,
        settlement_limit_mm: report.settlementLimit,
        base_friction_coefficient: report.friction,
        groundwater: {
          condition: "known_levels",
          construction_level_m: report.construction,
          service_level_m: report.service,
          antifloat_level_m: report.antifloat,
          source: `勘察报告：${report.name}`,
          observation_date: report.date || null,
        },
        report_name: report.name,
        report_date: report.date || null,
        catalog_versions: {
          geotechnical_hints: "geotechnical-hints-cn-2026.1-unverified",
        },
      };
    }
    return {
      profile_version: "1.0",
      stage: "scheme_estimate",
      regional_hint_id: soilPresetId,
      confirmed_soil_class: selectedSoil.title,
      bearing_capacity_kpa: selectedSoil.adopted,
      bearing_capacity_source: `方案持力层参考档：${selectedSoil.title}`,
      deformation_modulus_mpa: null,
      compression_modulus_mpa: null,
      base_friction_coefficient: selectedSoil.friction,
      groundwater: {
        condition: "no_influence",
        source: "方案阶段暂按地下水不影响；改变此条件必须重新分析",
      },
      report_name: null,
      report_date: null,
      catalog_versions: {
        geotechnical_hints: "geotechnical-hints-cn-2026.1-unverified",
      },
    };
  }

  async function persistProjectModel() {
    if (selectedProjectId === null) throw new Error("请先选择一个项目，再保存亭廊模型。");
    const unsupportedGrade = geometry.member_types?.find((type) => !["Q235B", "Q355B"].includes(type.material_grade));
    if (unsupportedGrade) throw new Error(`${unsupportedGrade.title} 的钢材牌号 ${unsupportedGrade.material_grade} 尚未在工作台开放，请选择 Q235B 或 Q355B。`);
    if ((siteProfile.completed_conditions?.length ?? 0) < 3) throw new Error("项目条件未完成：风、雪、地震必须全部明确。");
    if (geoStage === "project_check" && (!report.name || !report.date || report.modulus <= 0)) throw new Error("工程校核必须填写勘察报告名称、日期和变形参数。");
    setServerBusy(true);
    try {
      const existingCatalog = await api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${selectedProjectId}/custom-sections`);
      const typeSectionIds: Record<string, string> = {};
      for (const type of geometry.member_types ?? []) {
        const draft = sectionDrafts[type.id] ?? DEFAULT_SECTIONS.secondary;
        const dimensions =
          draft.family === "H"
            ? { h_mm: draft.h, b_mm: draft.b, tw_mm: draft.tw, tf_mm: draft.tf }
            : {
                h_mm: draft.h,
                b_mm: draft.family === "SHS" ? draft.h : draft.b,
                t_mm: draft.tw,
              };
        const baseId = `pergola-${type.id}`;
        const existing = existingCatalog.items.find((item) => item.id === type.section_id) ?? existingCatalog.items.find((item) => item.id === baseId);
        const unchanged = existing && existing.family === draft.family && Object.entries(dimensions).every(([key, value]) => Math.abs((existing.dimensions[key] ?? Number.NaN) - value) < 1e-9);
        if (unchanged) {
          typeSectionIds[type.id] = existing.id;
          continue;
        }
        const payload = {
          name: `${type.title} 项目截面`,
          family: draft.family,
          dimensions,
          source_reference: "亭廊工作台用户几何输入",
        };
        if (existing) {
          const revised = await api<CustomSectionDefinition>(`/api/v2/projects/${selectedProjectId}/custom-sections/${existing.id}/revisions`, {
            method: "POST",
            body: JSON.stringify(payload),
          });
          typeSectionIds[type.id] = revised.id;
          existingCatalog.items.push(revised);
          continue;
        }
        const created = await api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${selectedProjectId}/custom-sections`, {
          method: "POST",
          body: JSON.stringify({ id: baseId, ...payload }),
        });
        typeSectionIds[type.id] = created.items.find((item) => item.id === baseId)?.id ?? baseId;
        existingCatalog.items = created.items;
      }
      const profileToSave: ProjectSiteProfile = {
        ...siteProfile,
        climate_source_reference: siteProfile.climate_source_reference || (siteProfile.region_preset === "manual" ? "用户录入项目资料" : "浙江区域气候目录（未验证）"),
      };
      await api(`/api/v2/projects/${selectedProjectId}/site-profile`, {
        method: "PUT",
        body: JSON.stringify(profileToSave),
      });
      await api(`/api/v2/projects/${selectedProjectId}/geotechnical-profile`, {
        method: "PUT",
        body: JSON.stringify(projectGeotechnicalProfile()),
      });
      let instanceId = sceneInstanceId;
      if (instanceId === null) {
        const created = await api<{ id: number }>(`/api/v2/projects/${selectedProjectId}/scene-instances`, {
          method: "POST",
          body: JSON.stringify({
            family_id: "pergola-pavilion",
            variant_id: "guided-grid",
            title: "亭廊 Geometry 2.3",
            mode: "quick",
          }),
        });
        instanceId = created.id;
        setSceneInstanceId(instanceId);
      }
      const assemblyId =
        (
          {
            none: "none",
            louver: "louver-light",
            glass: "glass-canopy",
            aluminum: "aluminum-panel",
            steel: "steel-panel",
            polycarbonate: "polycarbonate",
            timber: "timber-cover",
          } as Record<string, string>
        )[roofAssemblyId] ?? "steel-panel";
      const savedGeometry: SceneGeometryProfile = {
        ...geometry,
        member_types: (geometry.member_types ?? []).map((type) => ({
          ...type,
          section_id: typeSectionIds[type.id],
        })),
        roof_load_zones: (geometry.roof_load_zones ?? []).map((zone) => ({
          ...zone,
          roof_assembly_id: assemblyId,
        })),
      };
      await api(`/api/v2/projects/${selectedProjectId}/scene-instances/${instanceId}/geometry`, { method: "PUT", body: JSON.stringify(savedGeometry) });
      setGeometry(savedGeometry);
      setSiteProfile(profileToSave);
      setAnalysisResult(null);
      setAnalysisSnapshotId(null);
      setMessage("项目条件、截面修订、Geometry 2.3 与地下条件已保存；旧分析结果已失效。");
      return { instanceId, assemblyId };
    } finally {
      setServerBusy(false);
    }
  }

  async function createWorkbenchProject() {
    if (!newProjectName.trim()) { setMessage("请输入新项目名称。"); return; }
    setServerBusy(true);
    try {
      const project = await api<Project>("/api/v2/projects", {
        method: "POST", body: JSON.stringify({ name: newProjectName.trim(), description: "" }),
      });
      onProjectsChange?.([...projects, project]);
      setSelectedProjectId(project.id);
      setSceneInstanceId(null);
      setAnalysisResult(null);
      setAnalysisSnapshotId(null);
      setNewProjectName("");
      setMessage("项目已创建，请完善条件后保存模型。");
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setServerBusy(false); }
  }

  async function runProjectAnalysis() {
    if (mode !== "project" || selectedProjectId === null) return;
    try {
      const { instanceId, assemblyId } = await persistProjectModel();
      const generation = inputGeneration.current;
      setServerBusy(true);
      const maintenance = maintenanceCategory === "none" ? "not_applicable" : maintenanceCategory === "walkway" ? "walkway_equipment" : maintenanceCategory;
      const result = await api<AnalysisResult>(`/api/v2/projects/${selectedProjectId}/scene-instances/${instanceId}/analyze`, {
        method: "POST",
        body: JSON.stringify({
          stage: geoStage,
          roof_load_selection: {
            roof_assembly_id: assemblyId,
            maintenance_category: maintenance,
            maintenance_load_kn_m2: maintenance === "maintenance" || maintenance === "not_applicable" ? null : maintenanceLoad,
            concentrated_maintenance_check_required: maintenance === "maintenance",
            custom_basis: maintenance === "custom" ? "亭廊工作台用户自定义" : null,
          },
        }),
      });
      if (generation !== inputGeneration.current) {
        setMessage("分析期间模型或条件已修改，本次结果已作废，请重新分析。");
        return;
      }
      setAnalysisResult(result);
      setAnalysisSnapshotId(result.snapshot_id ?? null);
      setArea("results");
      setMessage(`服务端分析完成：${statusLabel(result.workflow_status)}`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setServerBusy(false);
    }
  }

  async function saveWorkbench() {
    if (mode === "qa") {
      window.localStorage.setItem("steel-compass:qa:pergola-workbench-v2", JSON.stringify(geometry));
      setMessage("QA 草稿已保存，不影响现有项目和快照。");
      return;
    }
    try {
      await persistProjectModel();
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  function renderComposite(
    values: Array<{
      label: string;
      value: number;
      unit: string;
      onChange: (value: number) => void;
    }>,
  ) {
    return (
      <div className="qa-composite-input">
        {values.map((item, index) => (
          <label key={item.label}>
            <span>{item.label}</span>
            <input type="number" value={Number(item.value.toFixed(3))} onChange={(event) => item.onChange(Number(event.target.value))} />
            <em>{item.unit}</em>
            {index < values.length - 1 && <b>×</b>}
          </label>
        ))}
      </div>
    );
  }

  function renderModelPanel() {
    if (selectedMember && selectedMemberInstance && selectedMemberType) {
      const start = geometry.nodes.find((item) => item.id === selectedMember.start_node_id)!;
      const end = geometry.nodes.find((item) => item.id === selectedMember.end_node_id)!;
      const angle = (Math.atan2(end.y_m - start.y_m, end.x_m - start.x_m) * 180) / Math.PI;
      const section = sectionDrafts[selectedMemberType.id] ?? DEFAULT_SECTIONS.secondary;
      return (
        <>
          <div className="qa-inspector-heading">
            <span className="qa-object-mark">{selectedMemberInstance.mark}</span>
            <div>
              <strong>{selectedMemberType.title}</strong>
              <small>
                {selectedMember.id} · 方向 {angle.toFixed(1)}°
              </small>
            </div>
          </div>
          <label className="qa-field">
            <span>构件类型</span>
            <select value={selectedMemberType.id} onChange={(event) => changeMemberAssignment(event.target.value)}>
              {geometry.member_types?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <div className="qa-property-group">
            <strong>起止节点与标高</strong>
            {renderComposite([
              {
                label: "起点Z",
                value: start.z_m,
                unit: "m",
                onChange: (value) => updateNode(start.id, { z_m: value }),
              },
              {
                label: "终点Z",
                value: end.z_m,
                unit: "m",
                onChange: (value) => updateNode(end.id, { z_m: value }),
              },
            ])}
            <small>
              {start.id} → {end.id}；柱高只通过这里修改，平面拖动不会改变高度。
            </small>
          </div>
          <label className="qa-field">
            <span>钢材牌号</span>
            <select
              value={selectedMemberType.material_grade}
              onChange={(event) =>
                updateMemberType(selectedMemberType.id, {
                  material_grade: event.target.value,
                })
              }
            >
              <option>Q235B</option>
              <option>Q355B</option>
              {!["Q235B", "Q355B"].includes(selectedMemberType.material_grade) && (
                <option value={selectedMemberType.material_grade} disabled>{selectedMemberType.material_grade}（请选择已开放牌号）</option>
              )}
            </select>
          </label>
          <div className="qa-property-group">
            <strong>截面尺寸</strong>
            {renderComposite(
              section.family === "H"
                ? [
                    {
                      label: "H",
                      value: section.h,
                      unit: "mm",
                      onChange: (value) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: { ...section, h: value },
                        })),
                    },
                    {
                      label: "B",
                      value: section.b,
                      unit: "mm",
                      onChange: (value) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: { ...section, b: value },
                        })),
                    },
                    {
                      label: "tw",
                      value: section.tw,
                      unit: "mm",
                      onChange: (value) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: { ...section, tw: value },
                        })),
                    },
                    {
                      label: "tf",
                      value: section.tf,
                      unit: "mm",
                      onChange: (value) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: { ...section, tf: value },
                        })),
                    },
                  ]
                : [
                    {
                      label: section.family === "SHS" ? "边长" : "高",
                      value: section.h,
                      unit: "mm",
                      onChange: (value) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: { ...section, h: value, ...(section.family === "SHS" ? { b: value } : {}) },
                        })),
                    },
                    ...(section.family === "SHS" ? [] : [{
                      label: "宽",
                      value: section.b,
                      unit: "mm",
                      onChange: (value: number) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: { ...section, b: value },
                        })),
                    }]),
                    {
                      label: "厚",
                      value: section.tw,
                      unit: "mm",
                      onChange: (value) =>
                        setSectionDrafts((current) => ({
                          ...current,
                          [selectedMemberType.id]: {
                            ...section,
                            tw: value,
                            tf: value,
                          },
                        })),
                    },
                  ],
            )}
            <small>{section.family === "SHS" ? "方管高宽相等，按边长保存；修改作用于同类型全部构件。" : "修改作用于同类型全部构件。"}保存时生成新截面修订，不覆盖历史规格。</small>
          </div>
          <details className="qa-details">
            <summary>详细参数</summary>
            <label className="qa-field">
              <span>杆端连接</span>
              <select
                value={selectedMemberType.end_release}
                onChange={(event) =>
                  updateMemberType(selectedMemberType.id, {
                    end_release: event.target.value as "rigid" | "pinned",
                  })
                }
              >
                <option value="rigid">刚接</option>
                <option value="pinned">铰接</option>
              </select>
            </label>
            <label className="qa-field">
              <span>截面方向</span>
              <select
                value={selectedMemberType.orientation}
                onChange={(event) =>
                  updateMemberType(selectedMemberType.id, {
                    orientation: event.target.value as "strong_axis" | "weak_axis",
                  })
                }
              >
                <option value="strong_axis">强轴受弯</option>
                <option value="weak_axis">弱轴受弯</option>
              </select>
            </label>
          </details>
        </>
      );
    }
    if (selectedDirectSupport) {
      const node = geometry.nodes.find((item) => item.id === selectedDirectSupport.node_id);
      return (
        <>
          <div className="qa-inspector-heading">
            <span className="qa-object-mark">S</span>
            <div>
              <strong>支承 {selectedDirectSupport.id}</strong>
              <small>节点 {selectedDirectSupport.node_id} · 与基础分开定义</small>
            </div>
          </div>
          <label className="qa-field">
            <span>约束类型</span>
            <select value={selectedDirectSupport.restraint} onChange={(event) => updateSupport(selectedDirectSupport.id, event.target.value as "pinned" | "fixed" | "spring")}>
              <option value="pinned">铰接（约束 UX/UY/UZ）</option>
              <option value="fixed">固定（约束六自由度）</option>
              <option value="spring">弹簧支承</option>
            </select>
          </label>
          {selectedDirectSupport.restraint === "spring" && (
            <div className="qa-property-group">
              <strong>平移弹簧刚度</strong>
              <small>默认仅用于交互草稿；工程计算须按地基或连接资料填写。</small>
              {renderComposite([
                {
                  label: "Kx",
                  value: selectedDirectSupport.spring_stiffness?.ux ?? 10000,
                  unit: "kN/m",
                  onChange: (value) =>
                    setGeometry((current) => ({
                      ...current,
                      supports: (current.supports ?? []).map((item) =>
                        item.id === selectedDirectSupport.id
                          ? {
                              ...item,
                              spring_stiffness: {
                                ...item.spring_stiffness,
                                ux: value,
                              },
                            }
                          : item,
                      ),
                    })),
                },
                {
                  label: "Ky",
                  value: selectedDirectSupport.spring_stiffness?.uy ?? 10000,
                  unit: "kN/m",
                  onChange: (value) =>
                    setGeometry((current) => ({
                      ...current,
                      supports: (current.supports ?? []).map((item) =>
                        item.id === selectedDirectSupport.id
                          ? {
                              ...item,
                              spring_stiffness: {
                                ...item.spring_stiffness,
                                uy: value,
                              },
                            }
                          : item,
                      ),
                    })),
                },
                {
                  label: "Kz",
                  value: selectedDirectSupport.spring_stiffness?.uz ?? 50000,
                  unit: "kN/m",
                  onChange: (value) =>
                    setGeometry((current) => ({
                      ...current,
                      supports: (current.supports ?? []).map((item) =>
                        item.id === selectedDirectSupport.id
                          ? {
                              ...item,
                              spring_stiffness: {
                                ...item.spring_stiffness,
                                uz: value,
                              },
                            }
                          : item,
                      ),
                    })),
                },
              ])}
            </div>
          )}
          <div className="qa-location-card">
            <MapPin size={17} />
            <div>
              <strong>约束位置</strong>
              <span>
                X {node?.x_m.toFixed(2)} / Y {node?.y_m.toFixed(2)} / Z {node?.z_m.toFixed(2)}
              </span>
            </div>
          </div>
        </>
      );
    }
    if (selectedNode)
      return (
        <>
          <div className="qa-inspector-heading">
            <span className="qa-object-mark">N</span>
            <div>
              <strong>节点 {selectedNode.id}</strong>
              <small>结构几何坐标</small>
            </div>
          </div>
          {renderComposite([
            {
              label: "X",
              value: selectedNode.x_m,
              unit: "m",
              onChange: (value) => updateNode(selectedNode.id, { x_m: value }),
            },
            {
              label: "Y",
              value: selectedNode.y_m,
              unit: "m",
              onChange: (value) => updateNode(selectedNode.id, { y_m: value }),
            },
            {
              label: "Z",
              value: selectedNode.z_m,
              unit: "m",
              onChange: (value) => updateNode(selectedNode.id, { z_m: value }),
            },
          ])}
        </>
      );
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>模型对象</strong>
            <small>按图纸编号定位和批量修改</small>
          </div>
          <MousePointer2 size={18} />
        </div>
        <div className="qa-model-summary">
          <span>
            <b>{geometry.nodes.length}</b> 节点
          </span>
          <span>
            <b>{geometry.members.length}</b> 构件
          </span>
          <span>
            <b>{geometry.foundation_instances?.length ?? 0}</b> 基础
          </span>
        </div>
        <button type="button" className="qa-secondary-action" onClick={completeBeamColumnConnections}>
          <GitBranch size={16} />
          识别并补齐梁柱连接
        </button>
        <small>只增加柱与梁在同一节点真实相交的 J-B 实例，不覆盖已有连接。</small>
        <label className="qa-field">
          <span>新增构件类型</span>
          <select value={activeMemberTypeId} onChange={(event) => setActiveMemberTypeId(event.target.value)}>
            {geometry.member_types
              ?.filter((item) => item.role !== "column")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
          </select>
        </label>
        <label className="qa-field">
          <span>新增构件工作标高</span>
          <div className="qa-value-unit">
            <input type="number" step="0.1" value={workElevation} onChange={(event) => setWorkElevation(Number(event.target.value))} />
            <em>m</em>
          </div>
        </label>
        <div className="qa-model-tree">
          {geometry.member_types?.map((type) => (
            <button
              type="button"
              key={type.id}
              onClick={() => {
                const instance = geometry.member_instances?.find((item) => item.member_type_id === type.id);
                if (instance) handleSelection({ kind: "member", id: instance.member_id });
              }}
            >
              <span>{type.mark_prefix}</span>
              <div>
                <strong>{type.title}</strong>
                <small>
                  {geometry.member_instances?.filter((item) => item.member_type_id === type.id).length ?? 0} 根 · {type.material_grade}
                </small>
              </div>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <div className="qa-task-list">
          <strong>当前任务</strong>
          <span className="done">
            <ClipboardCheck size={15} />
            对象编号和类型已建立
          </span>
          <span>
            <TriangleAlert size={15} />
            荷载分配与二阶分析仍待验证
          </span>
        </div>
      </>
    );
  }

  function renderLibraryPanel() {
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>场景库</strong>
            <small>保持当前项目条件，不跳回旧首页</small>
          </div>
          <Trees size={18} />
        </div>
        <div className="qa-scene-drawer">
          <button type="button" className="active">
            <strong>亭廊 / 花架</strong>
            <small>当前 Geometry 2.3 模型</small>
          </button>
          {["雨棚", "导视牌", "景墙", "门楼", "栈道 / 平台"].map((title) => (
            <button type="button" key={title} disabled>
              <strong>{title}</strong>
              <small>待共享专业闭环验证后开放</small>
            </button>
          ))}
        </div>
        <button
          type="button"
          className="qa-secondary-action"
          onClick={() => {
            const clean = initialGeometry();
            setGeometry(clean);
            setSelection(null);
            setMessage("已重建干净的 Geometry 2.3 亭廊模型；项目条件保持不变。");
          }}
        >
          <RefreshCw size={16} />
          重建当前亭廊模型
        </button>
        <small>旧 QA 草稿不会自动升级，避免把孤立对象带入正式模型。</small>
      </>
    );
  }

  function renderConditionsPanel() {
    const preset = siteProfile.region_preset ? SITE_PRESETS[siteProfile.region_preset] : null;
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>项目条件</strong>
            <small>项目级保存，荷载自动读取</small>
          </div>
          <MapPin size={18} />
        </div>
        <label className="qa-field">
          <span>地区档</span>
          <select
            value={siteProfile.region_preset ?? ""}
            onChange={(event) => {
              const region = event.target.value as ProjectSiteProfile["region_preset"];
              const values = region ? SITE_PRESETS[region] : null;
              setSiteProfile((current) => ({
                ...current,
                region_preset: region,
                basic_wind_pressure_kpa: values?.wind || null,
                basic_snow_pressure_kpa: values?.snow || null,
                completed_conditions: region && region !== "manual" ? Array.from(new Set([...(current.completed_conditions ?? []), "wind", "snow"])) : (current.completed_conditions ?? []).filter((item) => item !== "wind" && item !== "snow"),
              }));
            }}
          >
            <option value="">待选择</option>
            {Object.entries(SITE_PRESETS).map(([id, item]) => (
              <option key={id} value={id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
        <label className="qa-field">
          <span>重现期</span>
          <select
            value={siteProfile.recurrence_period_years}
            onChange={(event) =>
              setSiteProfile((current) => ({
                ...current,
                recurrence_period_years: Number(event.target.value) as 10 | 50 | 100,
              }))
            }
          >
            <option value={10}>10年</option>
            <option value={50}>50年（默认）</option>
            <option value={100}>100年</option>
          </select>
        </label>
        {renderComposite([
          {
            label: "基本风压",
            value: siteProfile.basic_wind_pressure_kpa ?? 0,
            unit: "kPa",
            onChange: (value) =>
              setSiteProfile((current) => ({
                ...current,
                basic_wind_pressure_kpa: value || null,
                completed_conditions: value > 0 ? Array.from(new Set([...(current.completed_conditions ?? []), "wind"])) : (current.completed_conditions ?? []).filter((item) => item !== "wind"),
              })),
          },
          {
            label: "基本雪压",
            value: siteProfile.basic_snow_pressure_kpa ?? 0,
            unit: "kPa",
            onChange: (value) =>
              setSiteProfile((current) => ({
                ...current,
                basic_snow_pressure_kpa: value || null,
                completed_conditions: value > 0 ? Array.from(new Set([...(current.completed_conditions ?? []), "snow"])) : (current.completed_conditions ?? []).filter((item) => item !== "snow"),
              })),
          },
        ])}
        <label className="qa-field">
          <span>地面环境类别</span>
          <select
            value={siteProfile.terrain_category}
            onChange={(event) =>
              setSiteProfile((current) => ({
                ...current,
                terrain_category: event.target.value as "A" | "B" | "C" | "D",
              }))
            }
          >
            <option value="A">A · 近海海面、海岛</option>
            <option value="B">B · 田野、乡村</option>
            <option value="C">C · 城镇密集建筑</option>
            <option value="D">D · 高层密集城区</option>
          </select>
        </label>
        <label className="qa-field">
          <span>抗震设防烈度 / 加速度</span>
          <select
            value={siteProfile.seismic_level ?? ""}
            onChange={(event) => {
              const value = event.target.value as ProjectSiteProfile["seismic_level"];
              setSiteProfile((current) => ({
                ...current,
                seismic_level: value || null,
                completed_conditions: value ? Array.from(new Set([...(current.completed_conditions ?? []), "seismic"])) : (current.completed_conditions ?? []).filter((item) => item !== "seismic"),
              }));
            }}
          >
            <option value="">待填写（无隐含默认）</option>
            <option value="6_005g">6度 / 0.05g</option>
            <option value="7_010g">7度 / 0.10g</option>
            <option value="7_015g">7度 / 0.15g</option>
            <option value="8_020g">8度 / 0.20g</option>
            <option value="8_030g">8度 / 0.30g</option>
            <option value="9_040g">9度 / 0.40g</option>
          </select>
        </label>
        <div className="qa-soil-card">
          <span>条件完整性</span>
          <strong>{siteProfile.completed_conditions?.length ?? 0} / 3</strong>
          <p>{preset ? `${preset.title}：风 ${siteProfile.basic_wind_pressure_kpa ?? "待填"}、雪 ${siteProfile.basic_snow_pressure_kpa ?? "待填"} kPa` : "请选择地区或手动填写风雪基本值。"}</p>
          <small>{siteProfile.seismic_level ? "地震档已明确。" : "仍缺地震烈度，不会按零地震计算。"}</small>
        </div>
      </>
    );
  }

  function renderLoadPanel() {
    const rule = geometry.double_slope_rule!;
    const noCover = roofAssemblyId === "none";
    const maintenance = noCover || maintenanceCategory === "none" ? null : maintenanceCategory === "maintenance" ? 0.5 : maintenanceLoad;
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>屋面与荷载</strong>
            <small>方向变化立即更新三维标高</small>
          </div>
          <CloudSnow size={18} />
        </div>
        <div className="qa-property-group">
          <strong>双坡屋盖</strong>
          <label className="qa-field">
            <span>屋脊方向</span>
            <div className="qa-value-unit">
              <input
                aria-label="屋脊方向"
                type="number"
                min="0"
                max="359"
                value={rule.ridge_direction_deg}
                onChange={(event) =>
                  updateRoof({
                    ridge_direction_deg: Number(event.target.value),
                  })
                }
              />
              <em>°</em>
            </div>
            <small>0° 为 X 向屋脊，90° 为 Y 向屋脊。</small>
          </label>
          <label className="qa-field">
            <span>屋脊位置</span>
            <input type="range" min="0.1" max="0.9" step="0.05" value={rule.ridge_offset_ratio} onChange={(event) => updateRoof({ ridge_offset_ratio: Number(event.target.value) })} />
            <small>距一侧边界 {(rule.ridge_offset_ratio * 100).toFixed(0)}%</small>
          </label>
          {renderComposite([
            {
              label: "左坡",
              value: rule.left_slope_deg,
              unit: "°",
              onChange: (value) => updateRoof({ left_slope_deg: value }),
            },
            {
              label: "右坡",
              value: rule.right_slope_deg,
              unit: "°",
              onChange: (value) => updateRoof({ right_slope_deg: value }),
            },
          ])}
        </div>
        <label className="qa-field">
          <span>屋面构造</span>
          <select
            value={roofAssemblyId}
            onChange={(event) => {
              setRoofAssemblyId(event.target.value);
              if (event.target.value === "none") setMaintenanceCategory("none");
            }}
          >
            {ROOF_ASSEMBLIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
          <small>
            {selectedRoofAssembly.layers.map((item) => `${item.name} ${item.surface_weight_kn_m2}kN/m²`).join("；") || "无构造层"}
            。参考范围 {selectedRoofAssembly.reference_range_kn_m2[0]}–{selectedRoofAssembly.reference_range_kn_m2[1]} kN/m²。
          </small>
        </label>
        <label className="qa-field">
          <span>屋面使用 / 检修类别</span>
          <select value={maintenanceCategory} disabled={noCover} onChange={(event) => setMaintenanceCategory(event.target.value as typeof maintenanceCategory)}>
            <option value="none">无顶部覆盖，不适用</option>
            <option value="maintenance">不上人屋面检修</option>
            <option value="walkway">设检修走道或设备</option>
            <option value="occupied">可上人平台</option>
            <option value="custom">自定义</option>
          </select>
        </label>
        {maintenanceCategory !== "none" && maintenanceCategory !== "maintenance" && (
          <label className="qa-field">
            <span>采用面荷载</span>
            <div className="qa-value-unit">
              <input type="number" min="0" step="0.1" value={maintenanceLoad} onChange={(event) => setMaintenanceLoad(Number(event.target.value))} />
              <em>kN/m²</em>
            </div>
          </label>
        )}
        <div className="qa-load-cards">
          <div>
            <span>屋面构造恒载</span>
            <strong>{selectedRoofAssembly.total_dead_load_kn_m2.toFixed(2)} kN/m²</strong>
            <small>{selectedRoofAssembly.source_reference}</small>
          </div>
          <div>
            <span>检修 / 使用荷载</span>
            <strong>{maintenance === null ? "不适用" : `${maintenance.toFixed(2)} kN/m²`}</strong>
            <small>{maintenanceCategory === "maintenance" ? "集中检修作用仍需独立检查" : "按所选类别生成"}</small>
          </div>
          <div>
            <span>屋面雪荷载</span>
            <strong>{noCover ? "不适用" : siteProfile.basic_snow_pressure_kpa ? `${siteProfile.basic_snow_pressure_kpa.toFixed(2)} kPa 基本值` : "待填写地区"}</strong>
            <small>{noCover ? "无顶部覆盖不生成屋面雪" : "坡度与分区系数由模型生成"}</small>
          </div>
          <div>
            <span>风 / 地震</span>
            <strong>
              {siteProfile.basic_wind_pressure_kpa ? `风 ${siteProfile.basic_wind_pressure_kpa.toFixed(2)} kPa` : "风待填写"} · {siteProfile.seismic_level ?? "地震待填写"}
            </strong>
            <small>自动生成 ±X / ±Y，条件不足不进入完整分析</small>
          </div>
        </div>
      </>
    );
  }

  function renderFoundationPanel() {
    const coverField = selectedFoundationType ? (
      <label className="qa-field">
        <span>基础保护层</span>
        <div className="qa-value-unit">
          <input
            aria-label="基础保护层"
            type="number"
            min="35"
            max="150"
            value={selectedFoundationType.cover_mm ?? 50}
            onChange={(event) =>
              updateFoundationType(selectedFoundationType.id, {
                cover_mm: Number(event.target.value),
              })
            }
          />
          <em>mm</em>
        </div>
        <small>保护层参与有效高度、剪切、冲切和配筋计算，不再使用隐藏默认值。</small>
      </label>
    ) : null;
    const shapeGeometryFields =
      selectedFoundationType?.form_id === "spread-stepped" ? (
        <div className="qa-property-group">
          <strong>阶形基础分级（1～3级）</strong>
          {(selectedFoundationType.steps ?? []).map((step, index) => (
            <div key={index} className="qa-step-editor">
              {renderComposite([
                {
                  label: `第${index + 1}级长`,
                  value: step.length_m,
                  unit: "m",
                  onChange: (value) =>
                    updateFoundationType(selectedFoundationType.id, {
                      steps: (selectedFoundationType.steps ?? []).map((item, itemIndex) => (itemIndex === index ? { ...item, length_m: value } : item)),
                    }),
                },
                {
                  label: "宽",
                  value: step.width_m,
                  unit: "m",
                  onChange: (value) =>
                    updateFoundationType(selectedFoundationType.id, {
                      steps: (selectedFoundationType.steps ?? []).map((item, itemIndex) => (itemIndex === index ? { ...item, width_m: value } : item)),
                    }),
                },
                {
                  label: "高",
                  value: step.height_mm,
                  unit: "mm",
                  onChange: (value) =>
                    updateFoundationType(selectedFoundationType.id, {
                      steps: (selectedFoundationType.steps ?? []).map((item, itemIndex) => (itemIndex === index ? { ...item, height_mm: value } : item)),
                    }),
                },
              ])}
              <button
                type="button"
                className="qa-inline-remove"
                onClick={() =>
                  updateFoundationType(selectedFoundationType.id, {
                    steps: (selectedFoundationType.steps ?? []).filter((_, itemIndex) => itemIndex !== index),
                  })
                }
              >
                删除本级
              </button>
            </div>
          ))}
          {(selectedFoundationType.steps?.length ?? 0) < 3 && (
            <button
              type="button"
              className="qa-secondary-action"
              onClick={() =>
                updateFoundationType(selectedFoundationType.id, {
                  steps: [
                    ...(selectedFoundationType.steps ?? []),
                    {
                      length_m: Math.max(selectedFoundationType.length_m - 0.5 - (selectedFoundationType.steps?.length ?? 0) * 0.3, 0.3),
                      width_m: Math.max(selectedFoundationType.width_m - 0.5 - (selectedFoundationType.steps?.length ?? 0) * 0.3, 0.3),
                      height_mm: 250,
                    },
                  ],
                })
              }
            >
              增加一级台阶
            </button>
          )}
          <small>底板厚度与各级台阶高度分别计入混凝土体积、自重和基础总高度。</small>
        </div>
      ) : selectedFoundationType?.form_id === "spread-tapered" ? (
        <div className="qa-property-group">
          <strong>锥形基础坡面</strong>
          {renderComposite([
            {
              label: "顶台长",
              value: selectedFoundationType.tapered_top_length_m ?? 0.6,
              unit: "m",
              onChange: (value) =>
                updateFoundationType(selectedFoundationType.id, {
                  tapered_top_length_m: value,
                }),
            },
            {
              label: "顶台宽",
              value: selectedFoundationType.tapered_top_width_m ?? 0.6,
              unit: "m",
              onChange: (value) =>
                updateFoundationType(selectedFoundationType.id, {
                  tapered_top_width_m: value,
                }),
            },
            {
              label: "坡面高",
              value: selectedFoundationType.tapered_height_mm ?? 300,
              unit: "mm",
              onChange: (value) =>
                updateFoundationType(selectedFoundationType.id, {
                  tapered_height_mm: value,
                }),
            },
          ])}
          <small>按矩形棱台体积计算坡面混凝土量；底板厚度仍单独参与剪切和冲切有效高度。</small>
        </div>
      ) : null;
    if (selectedFoundation && selectedFoundationType)
      return (
        <>
          {coverField}
          {shapeGeometryFields}
          <div className="qa-inspector-heading">
            <span className="qa-object-mark foundation">{selectedFoundation.mark}</span>
            <div>
              <strong>{selectedFoundationType.title}</strong>
              <small>{selectedFoundation.id}</small>
            </div>
          </div>
          <div className="qa-location-card">
            <MapPin size={17} />
            <div>
              <strong>对应 {selectedFoundation.column_member_id ?? "未绑定柱"}</strong>
              <span>
                支承 {selectedSupport?.id} · X {selectedSupportNode?.x_m.toFixed(2)} / Y {selectedSupportNode?.y_m.toFixed(2)}
              </span>
            </div>
          </div>
          <div className={`qa-foundation-diagram ${selectedFoundationType.form_id.replace("spread-", "")}`} aria-label={`${selectedFoundationType.title}剖面示意`}>
            <div className="base" />
            <div className="step" />
            {selectedFoundationType.pedestal?.enabled && (
              <div className="pedestal">
                <span>短柱</span>
              </div>
            )}
            <i>基础底板</i>
          </div>
          <label className="qa-field">
            <span>基础类型</span>
            <select
              value={selectedFoundationType.id}
              onChange={(event) =>
                setGeometry((current) => ({
                  ...current,
                  foundation_instances: (current.foundation_instances ?? []).map((item) => (item.id === selectedFoundation.id ? { ...item, foundation_type_id: event.target.value } : item)),
                }))
              }
            >
              {geometry.foundation_types?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.mark} · {item.title}
                </option>
              ))}
            </select>
          </label>
          <label className="qa-field">
            <span>基础底板形式</span>
            <select
              value={selectedFoundationType.form_id}
              onChange={(event) =>
                updateFoundationType(selectedFoundationType.id, {
                  form_id: event.target.value,
                })
              }
            >
              <option value="spread-stepped">阶形独立基础</option>
              <option value="spread-tapered">锥形独立基础</option>
              <option value="spread-prismatic">等厚独立基础</option>
            </select>
            <small>短柱是附属构造，不是另一种基础形式。</small>
          </label>
          <div className="qa-property-group">
            <strong>类型尺寸（同步全部 {selectedFoundationType.mark}）</strong>
            {renderComposite([
              {
                label: "长",
                value: selectedFoundationType.length_m,
                unit: "m",
                onChange: (value) =>
                  updateFoundationType(selectedFoundationType.id, {
                    length_m: value,
                  }),
              },
              {
                label: "宽",
                value: selectedFoundationType.width_m,
                unit: "m",
                onChange: (value) =>
                  updateFoundationType(selectedFoundationType.id, {
                    width_m: value,
                  }),
              },
              {
                label: "厚",
                value: selectedFoundationType.thickness_mm,
                unit: "mm",
                onChange: (value) =>
                  updateFoundationType(selectedFoundationType.id, {
                    thickness_mm: value,
                  }),
              },
              {
                label: "埋深",
                value: selectedFoundationType.embedment_m,
                unit: "m",
                onChange: (value) =>
                  updateFoundationType(selectedFoundationType.id, {
                    embedment_m: value,
                  }),
              },
            ])}
          </div>
          <div className="qa-two-fields">
            <label className="qa-field">
              <span>X向底筋</span>
              <input
                value={selectedFoundationType.bottom_x}
                onChange={(event) =>
                  updateFoundationType(selectedFoundationType.id, {
                    bottom_x: event.target.value,
                  })
                }
              />
            </label>
            <label className="qa-field">
              <span>Y向底筋</span>
              <input
                value={selectedFoundationType.bottom_y}
                onChange={(event) =>
                  updateFoundationType(selectedFoundationType.id, {
                    bottom_y: event.target.value,
                  })
                }
              />
            </label>
            {(["top_x", "top_y"] as const).map((key) => <label className="qa-field" key={key}>
              <span>{key === "top_x" ? "X向顶筋" : "Y向顶筋"}</span>
              <input value={selectedFoundationType[key] ?? ""} placeholder="如 Φ12@150；存在反向弯矩时必填"
                onChange={event => updateFoundationType(selectedFoundationType.id, { [key]: event.target.value || null })} />
            </label>)}
          </div>
          <div className="qa-property-group">
            <label className="qa-check-row">
              <input
                type="checkbox"
                checked={selectedFoundationType.pedestal?.enabled ?? false}
                onChange={(event) =>
                  updatePedestal(selectedFoundationType.id, {
                    enabled: event.target.checked,
                    auto_enabled: false,
                    override_reason: "QA 工作台用户明确选择",
                  })
                }
              />
              <span>
                <strong>钢筋混凝土短柱</strong>
                <small>柱脚高出基础顶超过 150mm 时默认启用；参与自重、力臂、冲切和配筋。</small>
              </span>
            </label>
            {selectedFoundationType.pedestal?.enabled && (
              <>
                {renderComposite([
                  {
                    label: "长",
                    value: selectedFoundationType.pedestal.length_mm ?? 500,
                    unit: "mm",
                    onChange: (value) =>
                      updatePedestal(selectedFoundationType.id, {
                        length_mm: value,
                      }),
                  },
                  {
                    label: "宽",
                    value: selectedFoundationType.pedestal.width_mm ?? 500,
                    unit: "mm",
                    onChange: (value) =>
                      updatePedestal(selectedFoundationType.id, {
                        width_mm: value,
                      }),
                  },
                  {
                    label: "净高",
                    value: selectedFoundationType.pedestal.clear_height_mm ?? 650,
                    unit: "mm",
                    onChange: (value) =>
                      updatePedestal(selectedFoundationType.id, {
                        clear_height_mm: value,
                        bottom_elevation_m: (selectedFoundationType.pedestal?.top_elevation_m ?? 0) - value / 1000,
                      }),
                  },
                ])}
                <div className="qa-two-fields">
                  <label className="qa-field">
                    <span>纵筋</span>
                    <input value={`${selectedFoundationType.pedestal.longitudinal_bar_count_x ?? 2}+${selectedFoundationType.pedestal.longitudinal_bar_count_y ?? 2} / Φ${selectedFoundationType.pedestal.longitudinal_bar_diameter_mm ?? 16}`} readOnly />
                  </label>
                  <label className="qa-field">
                    <span>箍筋</span>
                    <input value={`Φ${selectedFoundationType.pedestal.stirrup_diameter_mm ?? 8}@${selectedFoundationType.pedestal.stirrup_spacing_mm ?? 150}`} readOnly />
                  </label>
                </div>
                <details className="qa-details">
                  <summary>短柱详细配筋与构造</summary>
                  <div className="qa-two-fields">
                    <label className="qa-field">
                      <span>混凝土</span>
                      <select
                        value={selectedFoundationType.pedestal.concrete_grade ?? ""}
                        onChange={(event) =>
                          updatePedestal(selectedFoundationType.id, {
                            concrete_grade: event.target.value,
                          })
                        }
                      >
                        <option value="C25">C25</option>
                        <option value="C30">C30</option>
                        <option value="C35">C35</option>
                        <option value="C40">C40</option>
                      </select>
                    </label>
                    <label className="qa-field">
                      <span>保护层</span>
                      <div className="qa-value-unit">
                        <input
                          type="number"
                          min="20"
                          max="150"
                          value={selectedFoundationType.pedestal.cover_mm ?? ""}
                          placeholder="必填"
                          onChange={(event) =>
                            updatePedestal(selectedFoundationType.id, {
                              cover_mm: event.target.value ? Number(event.target.value) : null,
                            })
                          }
                        />
                        <em>mm</em>
                      </div>
                    </label>
                  </div>
                  {renderComposite([
                    {
                      label: "X边纵筋",
                      value: selectedFoundationType.pedestal.longitudinal_bar_count_x ?? 2,
                      unit: "根/边",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          longitudinal_bar_count_x: value,
                        }),
                    },
                    {
                      label: "Y边纵筋",
                      value: selectedFoundationType.pedestal.longitudinal_bar_count_y ?? 2,
                      unit: "根/边",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          longitudinal_bar_count_y: value,
                        }),
                    },
                    {
                      label: "纵筋直径",
                      value: selectedFoundationType.pedestal.longitudinal_bar_diameter_mm ?? 16,
                      unit: "mm",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          longitudinal_bar_diameter_mm: value,
                        }),
                    },
                  ])}
                  {renderComposite([
                    {
                      label: "箍筋直径",
                      value: selectedFoundationType.pedestal.stirrup_diameter_mm ?? 8,
                      unit: "mm",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          stirrup_diameter_mm: value,
                        }),
                    },
                    {
                      label: "箍筋间距",
                      value: selectedFoundationType.pedestal.stirrup_spacing_mm ?? 150,
                      unit: "mm",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          stirrup_spacing_mm: value,
                        }),
                    },
                    {
                      label: "加密区间距",
                      value: selectedFoundationType.pedestal.confinement_spacing_mm ?? 90,
                      unit: "mm",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          confinement_spacing_mm: value,
                        }),
                    },
                  ])}
                  {renderComposite([
                    {
                      label: "插筋锚固",
                      value: selectedFoundationType.pedestal.dowel_anchorage_mm ?? 600,
                      unit: "mm",
                      onChange: (value) =>
                        updatePedestal(selectedFoundationType.id, {
                          dowel_anchorage_mm: value,
                        }),
                    },
                  ])}
                  <div className="qa-two-fields">
                    <label className="qa-field">
                      <span>插筋连接</span>
                      <select
                        value={selectedFoundationType.pedestal.splice_type}
                        onChange={(event) =>
                          updatePedestal(selectedFoundationType.id, {
                            splice_type: event.target.value as NonNullable<FoundationTypeDefinition["pedestal"]>["splice_type"],
                          })
                        }
                      >
                        <option value="none">不搭接 / 连续钢筋</option>
                        <option value="lap">搭接</option>
                        <option value="mechanical">机械连接</option>
                        <option value="welded">焊接</option>
                      </select>
                    </label>
                    <label className="qa-check-row">
                      <input
                        type="checkbox"
                        checked={selectedFoundationType.pedestal.top_local_reinforcement}
                        onChange={(event) =>
                          updatePedestal(selectedFoundationType.id, {
                            top_local_reinforcement: event.target.checked,
                          })
                        }
                      />
                      <span>
                        <strong>柱脚顶部局部加强筋</strong>
                        <small>用于底板和锚栓作用区构造记录。</small>
                      </span>
                    </label>
                  </div>
                  <small>当前计算覆盖轴压、上拔、双向偏压、双向受剪、纵筋率、箍筋、插筋锚固及地震组合下的轴压比、全高加密和体积配箍筛查；全部仍为 unverified。</small>
                </details>
              </>
            )}
          </div>
          {selectedColumnBase && (
            <details className="qa-details" open>
              <summary>钢柱脚底板、锚栓与焊缝</summary>
              <small>锚栓等级是 4.8 / 5.8 / 8.8 性能等级，不是钢材牌号。旧草稿中的 Q355B 必须重新选择。</small>
              {renderComposite([
                {
                  label: "底板长",
                  value: selectedColumnBase.base_plate_length_mm,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ base_plate_length_mm: value }),
                },
                {
                  label: "底板宽",
                  value: selectedColumnBase.base_plate_width_mm,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ base_plate_width_mm: value }),
                },
                {
                  label: "底板厚",
                  value: selectedColumnBase.base_plate_thickness_mm,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ base_plate_thickness_mm: value }),
                },
              ])}
              <label className="qa-field">
                <span>锚栓性能等级</span>
                <select value={selectedColumnBase.anchor_grade} onChange={(event) => updateColumnBase({ anchor_grade: event.target.value })}>
                  {!["4.8", "5.8", "8.8"].includes(selectedColumnBase.anchor_grade) && <option value={selectedColumnBase.anchor_grade}>旧值 {selectedColumnBase.anchor_grade}（需改选）</option>}
                  <option value="4.8">4.8</option>
                  <option value="5.8">5.8</option>
                  <option value="8.8">8.8</option>
                </select>
              </label>
              {renderComposite([
                {
                  label: "锚栓直径",
                  value: selectedColumnBase.anchor_diameter_mm,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ anchor_diameter_mm: value }),
                },
                {
                  label: "锚栓数量",
                  value: selectedColumnBase.anchor_count,
                  unit: "根",
                  onChange: (value) => updateColumnBase({ anchor_count: value }),
                },
                {
                  label: "有效埋深",
                  value: selectedColumnBase.anchor_embedment_mm,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ anchor_embedment_mm: value }),
                },
              ])}
              {renderComposite([
                {
                  label: "锚栓间距",
                  value: selectedColumnBase.anchor_spacing_mm ?? 0,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ anchor_spacing_mm: value || null }),
                },
                {
                  label: "边距",
                  value: selectedColumnBase.anchor_edge_mm ?? 0,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ anchor_edge_mm: value || null }),
                },
                {
                  label: "锚板/锚头直径",
                  value: selectedColumnBase.anchor_head_diameter_mm ?? 0,
                  unit: "mm",
                  onChange: (value) =>
                    updateColumnBase({
                      anchor_head_diameter_mm: value || null,
                    }),
                },
              ])}
              {renderComposite([
                {
                  label: "附加锚固钢筋",
                  value: selectedColumnBase.anchor_supplementary_reinforcement_area_mm2 ?? 0,
                  unit: "mm²",
                  onChange: (value) =>
                    updateColumnBase({
                      anchor_supplementary_reinforcement_area_mm2: value,
                    }),
                },
                {
                  label: "焊脚有效厚度",
                  value: selectedColumnBase.weld_throat_mm ?? 0,
                  unit: "mm",
                  onChange: (value) => updateColumnBase({ weld_throat_mm: value || null }),
                },
              ])}
              <label className="qa-check-row">
                <input
                  type="checkbox"
                  checked={selectedColumnBase.anchor_cracked_concrete ?? true}
                  onChange={(event) =>
                    updateColumnBase({
                      anchor_cracked_concrete: event.target.checked,
                    })
                  }
                />
                <span>
                  <strong>按开裂混凝土验算锚固区</strong>
                  <small>影响劈裂承载力；不能由软件静默假定为不开裂。</small>
                </span>
              </label>
              <label className="qa-field">
                <span>混凝土局部承压设计值</span>
                <div className="qa-value-unit">
                  <input
                    type="number"
                    min="1"
                    step="0.5"
                    value={selectedColumnBase.concrete_bearing_capacity_mpa ?? ""}
                    placeholder="必填"
                    onChange={(event) =>
                      updateColumnBase({
                        concrete_bearing_capacity_mpa: event.target.value ? Number(event.target.value) : null,
                      })
                    }
                  />
                  <em>MPa</em>
                </div>
                <small>用于柱脚底板下局部承压；工作台不再静默套用单项快算默认值。</small>
              </label>
              <ColumnBaseContactFields value={selectedColumnBase} onChange={updateColumnBase} />
            </details>
          )}
          <button type="button" className="qa-secondary-action" onClick={detachFoundation}>
            <Split size={16} />从 {selectedFoundationType.mark} 分离为新类型
          </button>
        </>
      );
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>基础与地基</strong>
            <small>按基础类型归类和套用</small>
          </div>
          <Building2 size={18} />
        </div>
        <div className="qa-type-list">
          <div className="qa-list-heading">
            <strong>基础类型</strong>
            <button type="button" onClick={autoClassifyFoundations}>
              <RefreshCw size={14} />
              自动归类
            </button>
          </div>
          {geometry.foundation_types?.map((type) => (
            <button
              key={type.id}
              type="button"
              onClick={() => {
                const instance = geometry.foundation_instances?.find((item) => item.foundation_type_id === type.id);
                if (instance) handleSelection({ kind: "foundation", id: instance.id });
              }}
            >
              <span className="qa-foundation-swatch">{type.mark}</span>
              <div>
                <strong>{type.title}</strong>
                <small>
                  {type.length_m}×{type.width_m}×{type.thickness_mm}mm · {geometry.foundation_instances?.filter((item) => item.foundation_type_id === type.id).length} 处
                </small>
              </div>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <div className="qa-property-group">
          <div className="qa-segmented">
            <button type="button" className={geoStage === "scheme_estimate" ? "active" : ""} onClick={() => setGeoStage("scheme_estimate")}>
              方案测算
            </button>
            <button type="button" className={geoStage === "project_check" ? "active" : ""} onClick={() => setGeoStage("project_check")}>
              工程校核
            </button>
          </div>
          {geoStage === "scheme_estimate" ? (
            <>
              <label className="qa-field">
                <span>持力层参考档</span>
                <select value={soilPresetId} onChange={(event) => setSoilPresetId(event.target.value)}>
                  {SOIL_PRESETS.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
              <div className="qa-soil-card">
                <span>{selectedSoil.title}</span>
                <strong>
                  {selectedSoil.range[0]}–{selectedSoil.range[1]} kPa
                </strong>
                <b>方案采用 {selectedSoil.adopted} kPa · 基底摩擦系数 {selectedSoil.friction.toFixed(2)}</b>
                <p>{selectedSoil.description}</p>
                <small>{selectedSoil.risk}</small>
              </div>
            </>
          ) : (
            <div className="qa-report-card">
              <label className="qa-field">
                <span>勘察报告名称</span>
                <input
                  value={report.name}
                  onChange={(event) =>
                    setReport((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="qa-field">
                <span>报告日期</span>
                <input
                  type="date"
                  value={report.date}
                  onChange={(event) =>
                    setReport((current) => ({
                      ...current,
                      date: event.target.value,
                    }))
                  }
                />
              </label>
              {renderComposite([
                {
                  label: "承载力",
                  value: report.bearing,
                  unit: "kPa",
                  onChange: (value) => setReport((current) => ({ ...current, bearing: value })),
                },
                {
                  label: "压缩模量",
                  value: report.modulus,
                  unit: "MPa",
                  onChange: (value) => setReport((current) => ({ ...current, modulus: value })),
                },
              ])}
              {renderComposite([
                {
                  label: "压缩层厚度",
                  value: report.layerThickness,
                  unit: "m",
                  onChange: (value) => setReport((current) => ({ ...current, layerThickness: value })),
                },
                {
                  label: "土层天然重度",
                  value: report.unitWeight,
                  unit: "kN/m³",
                  onChange: (value) => setReport((current) => ({ ...current, unitWeight: value })),
                },
              ])}
              {renderComposite([
                {
                  label: "沉降经验系数",
                  value: report.settlementFactor,
                  unit: "1",
                  onChange: (value) => setReport((current) => ({ ...current, settlementFactor: value })),
                },
                {
                  label: "允许沉降",
                  value: report.settlementLimit,
                  unit: "mm",
                  onChange: (value) => setReport((current) => ({ ...current, settlementLimit: value })),
                },
                {
                  label: "基底摩擦系数",
                  value: report.friction,
                  unit: "1",
                  onChange: (value) => setReport((current) => ({ ...current, friction: value })),
                },
              ])}
              {renderComposite([
                {
                  label: "施工水位",
                  value: report.construction,
                  unit: "m",
                  onChange: (value) =>
                    setReport((current) => ({
                      ...current,
                      construction: value,
                    })),
                },
                {
                  label: "使用水位",
                  value: report.service,
                  unit: "m",
                  onChange: (value) => setReport((current) => ({ ...current, service: value })),
                },
                {
                  label: "抗浮水位",
                  value: report.antifloat,
                  unit: "m",
                  onChange: (value) => setReport((current) => ({ ...current, antifloat: value })),
                },
              ])}
              <small>报告资料在项目级录入一次，场景直接引用，不再逐项填写来源。</small>
            </div>
          )}
        </div>
      </>
    );
  }

  function renderResultsPanel() {
    if (!analysisResult)
      return (
        <>
          <div className="qa-panel-title">
            <div>
              <strong>计算闭环状态</strong>
              <small>保存模型后由服务端生成荷载、组合与快照</small>
            </div>
            <BarChart3 size={18} />
          </div>
          <div className="qa-result-summary">
            <span>当前状态</span>
            <strong>尚未分析</strong>
            <span>模型版本</span>
            <strong>Geometry 2.3</strong>
            <span>专业验证</span>
            <strong className="warning">unverified</strong>
          </div>
          {mode === "project" && (
            <button type="button" className="qa-secondary-action" disabled={serverBusy} onClick={runProjectAnalysis}>
              <BarChart3 size={16} />
              {serverBusy ? "分析中…" : "保存并开始完整分析"}
            </button>
          )}
        </>
      );
    const failedMembers = analysisResult.member_checks?.items.filter((item) => item.status === "failed") ?? [];
    const incompleteMembers = analysisResult.member_checks?.items.filter((item) => item.status !== "pass" && item.status !== "failed") ?? [];
    const incompleteConnections = analysisResult.connection_checks.items.filter((item) => item.status !== "complete" && item.status !== "failed");
    const memberItems = [...(analysisResult.member_checks?.items ?? [])].sort((a, b) => (b.utilization ?? -1) - (a.utilization ?? -1));
    return (
      <>
        <div className="qa-panel-title">
          <div>
            <strong>计算闭环结果</strong>
            <small>结果来自不可变 Schema 4.0 分析快照</small>
          </div>
          <BarChart3 size={18} />
        </div>
        <div className="qa-result-summary">
          <span>工作流</span>
          <strong className={analysisResult.workflow_status !== "ready" ? "warning" : ""}>{statusLabel(analysisResult.workflow_status)}</strong>
          <span>结构分析</span>
          <strong>{statusLabel(analysisResult.structural_analysis.status)}</strong>
          <span>构件验算</span>
          <strong>{statusLabel(analysisResult.member_checks?.status ?? "incomplete")}</strong>
          <span>连接验算</span>
          <strong>{statusLabel(analysisResult.connection_checks.status)}</strong>
          <span>基础与地基</span>
          <strong>{statusLabel(analysisResult.foundation_checks.status)}</strong>
          <span>最低屈曲系数</span>
          <strong>{analysisResult.buckling_analysis?.factors?.[0]?.toFixed(3) ?? "未计算"}</strong>
        </div>
        <div className="qa-task-list">
          <span className={analysisResult.structural_analysis.balance_checks.length > 0 && analysisResult.structural_analysis.balance_checks.every((item) => item.balanced) ? "done" : ""}>
            <ClipboardCheck size={15} />
            逐工况荷载与反力平衡
          </span>
          <span className={memberItems.length > 0 && failedMembers.length === 0 && incompleteMembers.length === 0 && analysisResult.member_checks?.status === "complete" ? "done" : ""}>
            <TriangleAlert size={15} />
            失败构件 {failedMembers.length} 根 · 未完成 {incompleteMembers.length} 根
          </span>
          <span className={analysisResult.connection_checks.items.length > 0 && incompleteConnections.length === 0 && analysisResult.connection_checks.status === "complete" ? "done" : ""}>
            <TriangleAlert size={15} />
            未完成连接 {incompleteConnections.length} 个
          </span>
          {analysisResult.trace.unsupported_capabilities.map((item) => (
            <span key={item}>
              <TriangleAlert size={15} />
              {item}
            </span>
          ))}
        </div>
        <details className="qa-result-details" open>
          <summary>荷载与反力平衡</summary>
          {analysisResult.structural_analysis.balance_checks.map((item) => (
            <div key={item.case} className={item.balanced ? "pass" : "fail"}>
              <strong>{item.case ?? "未编号组合"}</strong>
              <span>{item.balanced ? "平衡" : "不平衡"}</span>
              <small>{item.residual_kn?.map((value) => Number(value).toExponential(2)).join(" / ") ?? "无残差记录"} kN</small>
            </div>
          ))}
        </details>
        <details className="qa-result-details" open>
          <summary>构件验算与图面定位</summary>
          {memberItems.map((item) => (
            <button key={item.member_id} type="button" onClick={() => item.member_id && handleSelection({ kind: "member", id: item.member_id })}>
              <strong>{item.member_id ?? "未编号构件"}</strong>
              <span className={item.status === "failed" ? "fail" : item.status === "pass" ? "pass" : "warning"}>{statusLabel(item.status ?? "not_calculated")}</span>
              <small>
                利用率 {item.utilization == null ? "未计算" : item.utilization.toFixed(3)} · {item.controlling_case ?? "无控制组合"}
              </small>
              {item.reason && <small>{item.reason}</small>}
            </button>
          ))}
        </details>
        <details className="qa-result-details">
          <summary>连接、柱脚与锚栓</summary>
          {analysisResult.connection_checks.items.map((item) => (
            <button key={item.connection_id ?? item.mark} type="button" disabled={!item.node_id} onClick={() => item.node_id && handleSelection({ kind: "node", id: item.node_id })}>
              <strong>{item.mark ?? item.connection_id ?? "未编号连接"}</strong>
              <span className={item.status === "failed" ? "fail" : item.status === "complete" || item.status === "pass" ? "pass" : "warning"}>{statusLabel(item.status ?? "not_calculated")}</span>
              <small>{item.failed_checks?.join("、") || item.issue_code || "已形成检查包"}</small>
            </button>
          ))}
        </details>
        <details className="qa-result-details">
          <summary>短柱、基础与地基</summary>
          {analysisResult.foundation_checks.items.map((item) => (
            <button key={item.foundation_id ?? item.mark} type="button" disabled={!item.foundation_id} onClick={() => item.foundation_id && handleSelection({ kind: "foundation", id: item.foundation_id })}>
              <strong>{item.mark ?? item.foundation_id ?? "未编号基础"}</strong>
              <span className={item.status === "failed" ? "fail" : item.status === "complete" || item.status === "pass" ? "pass" : "warning"}>{statusLabel(item.status ?? "not_calculated")}</span>
              <small>{item.failed_checks?.join("、") || item.pending_checks?.join("、") || "已形成检查包"}</small>
            </button>
          ))}
        </details>
        <details className="qa-result-details">
          <summary>公式、版本与未支持范围</summary>
          {analysisResult.trace.formulas?.map((item) => (
            <div key={`${item.topic}-${item.source}`}>
              <strong>{item.topic ?? "计算主题"}</strong>
              <small>{item.source ?? "未记录来源"}</small>
            </div>
          ))}
          {analysisResult.trace.unsupported_capabilities.map((item) => (
            <div key={item} className="fail">
              <strong>未完成</strong>
              <small>{item}</small>
            </div>
          ))}
        </details>
        {mode === "project" && selectedProjectId !== null && sceneInstanceId !== null && analysisSnapshotId !== null && (
          <a className="qa-secondary-action" href={`/api/v2/projects/${selectedProjectId}/scene-instances/${sceneInstanceId}/analysis-snapshots/${analysisSnapshotId}/report.pdf`}>
            <Save size={16} />
            下载快照计算书 PDF
          </a>
        )}
      </>
    );
  }

  const navigation: Array<{ id: Area; label: string; icon: typeof Trees }> = [
    { id: "library", label: "场景库", icon: Trees },
    { id: "conditions", label: "项目条件", icon: MapPin },
    { id: "model", label: "模型", icon: Grid2X2 },
    { id: "loads", label: "荷载", icon: CloudSnow },
    { id: "foundation", label: "基础", icon: Building2 },
    { id: "results", label: "结果", icon: BarChart3 },
  ];

  return (
    <main
      ref={shellRef}
      className="qa-workbench-shell"
      style={
        {
          "--qa-plan-fr": `${splitPercent}fr`,
          "--qa-3d-fr": `${100 - splitPercent}fr`,
        } as React.CSSProperties
      }
    >
      <aside className="qa-icon-rail" aria-label="亭廊工作台一级入口">
        <div className="qa-brand-mark">SC</div>
        {navigation.map((item) => (
          <button
            key={item.id}
            type="button"
            className={area === item.id ? "active" : ""}
            aria-label={item.label}
            title={item.label}
            onClick={() => {
              setArea(item.id);
              setMobilePane("property");
              setSelection(null);
            }}
          >
            <item.icon size={20} />
            <span>{item.label}</span>
          </button>
        ))}
        <div className="qa-rail-spacer" />
        <button type="button" aria-label="收起说明" title="一级入口保持56px图标栏">
          <PanelLeftClose size={19} />
          <span>收起</span>
        </button>
      </aside>
      <section className={`qa-property-panel ${mobilePane === "property" ? "mobile-active" : ""}`}>
        <header>
          <div>
            <span>{mode === "qa" ? "亭廊 QA 工作台" : "亭廊专业工作台"}</span>
            <h1>{area === "library" ? "场景库" : area === "conditions" ? "项目条件" : area === "results" ? "分析结果" : "对象属性"}</h1>
          </div>
          <span className="qa-schema-badge">Geometry 2.3</span>
        </header>
        <div className="qa-property-scroll">{area === "results" ? renderResultsPanel() : area === "library" ? renderLibraryPanel() : area === "conditions" ? renderConditionsPanel() : area === "model" ? renderModelPanel() : area === "loads" ? renderLoadPanel() : renderFoundationPanel()}</div>
        <footer>
          <small role="status">{message}</small>
          {mode === "project" && (
            <div className="qa-project-create">
              <input aria-label="新项目名称" placeholder="新项目名称" value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)} />
              <button type="button" disabled={serverBusy} onClick={createWorkbenchProject}>新建项目</button>
            </div>
          )}
          {mode === "project" && (
            <select
              aria-label="保存到项目"
              value={selectedProjectId ?? ""}
              onChange={(event) => {
                setSelectedProjectId(event.target.value ? Number(event.target.value) : null);
                setSceneInstanceId(null);
                setAnalysisResult(null);
              }}
            >
              <option value="">选择项目</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          )}
          <button type="button" disabled={serverBusy} onClick={saveWorkbench}>
            <Save size={16} />
            {serverBusy ? "处理中…" : mode === "qa" ? "保存 QA 草稿" : "保存项目模型"}
          </button>
          {mode === "project" && (
            <button type="button" disabled={serverBusy} onClick={runProjectAnalysis}>
              <BarChart3 size={16} />
              完整分析
            </button>
          )}
          <small>{mode === "qa" ? "隔离存储 · 不写入项目数据" : "项目数据 · 分析生成不可变快照"}</small>
        </footer>
      </section>
      <section className={`qa-canvas-panel qa-plan-pane ${mobilePane === "2d" ? "mobile-active" : ""}`}>
        <header>
          <div>
            <span>二维精确编辑</span>
            <strong>{view === "plan" ? "平面" : view === "x_elevation" ? "X立面" : "Y立面"}</strong>
          </div>
          <div className="qa-view-tabs" role="tablist">
            <button type="button" className={view === "plan" ? "active" : ""} onClick={() => setView("plan")}>
              平面
            </button>
            <button type="button" className={view === "x_elevation" ? "active" : ""} onClick={() => setView("x_elevation")}>
              X立面
            </button>
            <button type="button" className={view === "y_elevation" ? "active" : ""} onClick={() => setView("y_elevation")}>
              Y立面
            </button>
          </div>
        </header>
        <PergolaPlanEditorV2 geometry={geometry} selection={selection} view={view} workElevation={workElevation} activeMemberTypeId={activeMemberTypeId} onSelectionChange={handleSelection} onGeometryChange={setGeometry} onMessage={setCanvasMessage} />
        <div className="qa-status-bar">
          <span>
            <GitBranch size={14} />
            {canvasMessage}
          </span>
          <em>
            节点 {geometry.nodes.length} · 构件 {geometry.members.length} · 基础 {geometry.foundation_instances?.length ?? 0}
          </em>
        </div>
      </section>
      <div
        className="qa-canvas-splitter"
        role="separator"
        aria-label="调整二维与三维视图宽度"
        aria-valuemin={30}
        aria-valuemax={70}
        aria-valuenow={Math.round(splitPercent)}
        tabIndex={0}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDraggingSplit(true);
        }}
        onDoubleClick={() => setSplitPercent(55)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setSplitPercent((value) => Math.max(30, value - (event.shiftKey ? 5 : 1)));
          if (event.key === "ArrowRight") setSplitPercent((value) => Math.min(70, value + (event.shiftKey ? 5 : 1)));
        }}
      >
        <span />
      </div>
      <section className={`qa-canvas-panel qa-3d-pane ${mobilePane === "3d" ? "mobile-active" : ""}`}>
        <header>
          <div>
            <span>三维实时视图</span>
            <strong>选择与二维同步</strong>
          </div>
          <div className="qa-view-key">
            <i className="column" />柱<i className="beam" />梁
            <i className="foundation" />
            基础
          </div>
        </header>
        <SceneModelPreview geometry={geometry} foundationsBySupportId={foundationsBySupportId} selectedMemberId={selection?.kind === "member" ? selection.id : null} selectedFoundationId={selection?.kind === "foundation" ? selection.id : null} onSelectMember={(id) => handleSelection({ kind: "member", id })} onSelectFoundation={(id) => handleSelection({ kind: "foundation", id })} />
        <div className="qa-3d-overlay">
          <Box size={16} />
          <span>拖动旋转 · 滚轮缩放 · 点击构件或基础定位</span>
        </div>
      </section>
      <nav className="qa-mobile-tabs" aria-label="移动端工作台视图">
        <button type="button" className={mobilePane === "property" ? "active" : ""} onClick={() => setMobilePane("property")}>
          <Settings2 size={17} />
          属性
        </button>
        <button type="button" className={mobilePane === "2d" ? "active" : ""} onClick={() => setMobilePane("2d")}>
          <Ruler size={17} />
          二维
        </button>
        <button type="button" className={mobilePane === "3d" ? "active" : ""} onClick={() => setMobilePane("3d")}>
          <Box size={17} />
          三维
        </button>
      </nav>
    </main>
  );
}
