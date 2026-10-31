import { MODULE_MAP } from "@/lib/modules";
import type {
  FoundationDesignSpecification,
  Module,
  SceneConditionProfile,
  SceneFamily,
  SceneGraphTemplate,
  SceneLoadCase,
  SceneRevision,
  SceneVariant,
} from "@/lib/types";

// Pure scene helpers shared by the scene workspace and its hooks.

export const STATUS_LABELS = {
  completed: "已录入",
  passed: "已完成",
  failed: "不满足",
  incomplete: "待补齐",
  not_applicable: "不适用",
};

export type WorkspaceTab = "settings" | "results";
export type GroundwaterCondition = "no_influence" | "known_water_table" | "unknown";
export type SnowExposure = "exposed" | "not_applicable";
export type DesignStage = "scheme_estimate" | "project_check";

const LEGACY_SCENE_CONDITIONS: Record<string, SceneConditionProfile> = {
  "pergola-pavilion": { wind: "required", snow: "required", seismic: "required", wind_semantics: "roof", snow_semantics: "roof", height_parameter_keys: ["height_m", "column_height_m"], geotechnical_mode: "generic" },
  canopy: { wind: "required", snow: "required", seismic: "required", wind_semantics: "roof", snow_semantics: "roof", height_parameter_keys: ["height_m", "column_height_m"], geotechnical_mode: "generic" },
  "signage-billboard": { wind: "required", snow: "not_applicable", seismic: "required", wind_semantics: "solid_panel", snow_semantics: "not_applicable", height_parameter_keys: ["height_m", "post_height_m", "panel_cg_height_m"], geotechnical_mode: "generic" },
  "landscape-wall-fence": { wind: "required", snow: "not_applicable", seismic: "required", wind_semantics: "solid_panel", snow_semantics: "not_applicable", height_parameter_keys: ["height_m", "wall_height_m"], geotechnical_mode: "generic" },
  "entrance-frame": { wind: "required", snow: "not_applicable", seismic: "required", wind_semantics: "solid_panel", snow_semantics: "not_applicable", height_parameter_keys: ["height_m", "right_height_m"], geotechnical_mode: "generic" },
  "boardwalk-platform": { wind: "not_applicable", snow: "required", seismic: "required", wind_semantics: "not_applicable", snow_semantics: "exposed_horizontal", height_parameter_keys: [], geotechnical_mode: "generic" },
  "bench-planter": { wind: "not_applicable", snow: "not_applicable", seismic: "not_applicable", wind_semantics: "not_applicable", snow_semantics: "not_applicable", height_parameter_keys: [], geotechnical_mode: "generic" },
  "water-feature-pool": { wind: "not_applicable", snow: "not_applicable", seismic: "not_supported", wind_semantics: "not_applicable", snow_semantics: "not_applicable", height_parameter_keys: [], geotechnical_mode: "variant_owned" },
  "landscape-bridge": { wind: "required", snow: "not_applicable", seismic: "not_supported", wind_semantics: "bridge_side", snow_semantics: "not_applicable", height_parameter_keys: ["deck_width_m"], geotechnical_mode: "variant_owned" },
  "retaining-facility": { wind: "not_applicable", snow: "not_applicable", seismic: "not_supported", wind_semantics: "not_applicable", snow_semantics: "not_applicable", height_parameter_keys: [], geotechnical_mode: "variant_owned" },
};

export function sceneConditionProfile(
  family: SceneFamily,
  variant: SceneVariant | undefined,
): SceneConditionProfile {
  if (!variant?.condition_profile && family.id === "bench-planter" && variant?.id === "planter") {
    return { wind: "optional", snow: "not_applicable", seismic: "not_supported", wind_semantics: "solid_panel", snow_semantics: "not_applicable", height_parameter_keys: ["wall_height_m"], geotechnical_mode: "variant_owned" };
  }
  return variant?.condition_profile ?? LEGACY_SCENE_CONDITIONS[family.id] ?? {
    wind: "not_applicable",
    snow: "not_applicable",
    seismic: "not_applicable",
    wind_semantics: "not_applicable",
    snow_semantics: "not_applicable",
    height_parameter_keys: [],
    geotechnical_mode: "generic",
  };
}

export function toRoofForm(value: unknown): "flat" | "single_slope" | "double_slope" | "other" {
  const name = String(value ?? "");
  if (name.includes("单坡")) return "single_slope";
  if (name.includes("双坡")) return "double_slope";
  if (name.includes("平")) return "flat";
  return "other";
}

export function initialValues(family: SceneFamily, variantId: string) {
  const variant =
    family.variants.find((item) => item.id === variantId) ?? family.variants[0];
  return Object.fromEntries(
    (variant?.parameters ?? []).map((parameter) => [
      parameter.key,
      parameter.default ?? "",
    ]),
  );
}

export function graphFor(family: SceneFamily, variant?: SceneVariant): SceneGraphTemplate {
  return variant?.graph_template ?? family.graph_template;
}

function fallbackLoadCases(
  family: SceneFamily,
  graph: SceneGraphTemplate,
): SceneLoadCase[] {
  const calculationNode = graph.nodes.find(
    (node) => node.calculation_module && node.calculation_module in MODULE_MAP,
  );
  if (!calculationNode?.calculation_module) return [];
  const definition = MODULE_MAP[calculationNode.calculation_module as Module];
  return definition.defaultLoads.map((load, index) => ({
    id: `${family.id}-legacy-${index + 1}`,
    label:
      load.kind === "dead"
        ? "附加恒载"
        : load.kind === "live"
          ? "使用活荷载"
          : load.kind === "wind"
            ? "风荷载"
            : load.kind === "snow"
              ? "雪荷载"
              : "结构自重",
    kind: load.kind,
    value_type: load.kind === "self_weight" ? "calculated" : "fixed",
    recommended_default: load.value,
    adopted_value: load.value,
    unit: load.unit,
    source_reference: load.source_reference ?? "legacy-module-default",
    applicable_when: family.title,
    distribution: load.unit === "kN" ? "point" : load.unit === "kN/m" ? "line" : "area",
    direction: load.direction ?? "gravity",
    application_target: calculationNode.id,
    notes: "兼容旧场景数据；请核对后采用。",
  }));
}

export function copiedLoadCases(
  family: SceneFamily,
  variant: SceneVariant | undefined,
  graph: SceneGraphTemplate,
) {
  const source = variant?.load_package?.items ?? fallbackLoadCases(family, graph);
  return source.map((item) => {
    const { confirmed: _legacyConfirmation, ...current } = item as SceneLoadCase & {
      confirmed?: boolean;
    };
    void _legacyConfirmation;
    return {
      ...current,
      adopted_value: current.adopted_value ?? current.recommended_default ?? 0,
    };
  });
}

export function currentLoadCases(items: SceneLoadCase[]): SceneLoadCase[] {
  return items.map((item) => {
    const { confirmed: _legacyConfirmation, ...current } = item as SceneLoadCase & {
      confirmed?: boolean;
    };
    void _legacyConfirmation;
    return current;
  });
}

export function controllingUtilization(revision: SceneRevision): number | null {
  const values = Object.values(revision.result_bundle).flatMap((result) =>
    result.checks.map((check) => check.utilization),
  );
  return values.length ? Math.max(...values) : null;
}

export function loadRange(item: SceneLoadCase) {
  if (item.value_type === "calculated") return "按几何与材料自动计算";
  if (item.value_type === "project_defined") return "项目资料取值";
  if (
    item.recommended_min !== undefined &&
    item.recommended_max !== undefined &&
    item.recommended_min !== item.recommended_max
  ) {
    return `${item.recommended_min}–${item.recommended_max} ${item.unit}`;
  }
  return `${item.recommended_default ?? item.adopted_value} ${item.unit}`;
}

export function foundationTypeForGraph(graph: SceneGraphTemplate | undefined): string {
  const modules = new Set(
    (graph?.nodes ?? [])
      .map((node) => node.calculation_module)
      .filter((module): module is string => Boolean(module)),
  );
  if (modules.has("strip_footing") && !modules.has("spread_footing")) {
    return "条形基础";
  }
  return "独立基础";
}

export function normalizedFoundations(items: FoundationDesignSpecification[]): FoundationDesignSpecification[] {
  return items.map((item) => ({
    ...item,
    concrete_grade: item.concrete_grade ?? "C30",
    rebar_grade: item.rebar_grade ?? "HRB400",
    bar_diameter_mm: item.bar_diameter_mm ?? 14,
    bar_spacing_mm: item.bar_spacing_mm ?? 150,
    reinforcement: item.reinforcement ?? {
      bottom_x_diameter_mm: item.bar_diameter_mm ?? 14,
      bottom_x_spacing_mm: item.bar_spacing_mm ?? 150,
      bottom_y_diameter_mm: item.bar_diameter_mm ?? 14,
      bottom_y_spacing_mm: item.bar_spacing_mm ?? 150,
    },
  }));
}

export function defaultCustomSectionDimensions(family: "SHS" | "RHS" | "CHS" | "H" | "I"): Record<string, number> {
  if (family === "SHS") return { h_mm: 150, b_mm: 150, t_mm: 6 };
  if (family === "RHS") return { h_mm: 200, b_mm: 100, t_mm: 6 };
  if (family === "CHS") return { diameter_mm: 168, t_mm: 6 };
  return { h_mm: 250, b_mm: 125, tw_mm: 6, tf_mm: 9 };
}

export const CUSTOM_SECTION_DIMENSION_LABELS: Record<string, string> = {
  h_mm: "截面高度",
  b_mm: "截面宽度",
  t_mm: "壁厚",
  diameter_mm: "外径",
  tw_mm: "腹板厚度",
  tf_mm: "翼缘厚度",
};

export function specialistLabel(key: string): string {
  const labels: Record<string, string> = {
    groundwater_condition: "地下水条件", groundwater_source: "地下水资料依据", submerged_depth: "承台淹没高度", buoyancy_factor_uls: "ULS浮力分项系数",
    frame_wind_exposed_height: "门楣迎风高度",
    base_restraint: "柱脚边界条件", poisson_ratio: "泊松比",
    base_projection: "底板外挑", retained_soil_height: "墙外挡土高度", full_external_head: "满池外水头", empty_external_head: "空池外水头", external_water_head: "外部地下水水头",
    concrete_unit_weight: "混凝土重度", water_unit_weight: "水重度", soil_unit_weight: "土重度", wall_unit_weight: "墙体重度", concrete_fc: "混凝土抗压设计值", concrete_ft: "混凝土抗拉设计值", rebar_fy: "钢筋抗拉设计值", rebar_es: "钢筋弹性模量",
    wall_vertical_as: "池壁竖向配筋", wall_horizontal_as: "池壁水平配筋", base_x_as: "底板X向配筋", base_y_as: "底板Y向配筋", wall_bar_diameter: "池壁钢筋直径", base_bar_diameter: "底板钢筋直径", wall_cover: "池壁保护层", base_cover: "底板保护层", minimum_reinforcement_ratio: "最小配筋率", maximum_reinforcement_ratio: "最大配筋率", crack_width_limit: "裂缝限值",
    girder_count: "主梁数量", thickness: "厚度", elastic_modulus: "弹性模量", bending_strength: "抗弯设计强度", shear_strength: "抗剪设计强度", unit_weight: "材料重度", deflection_limit_ratio: "挠度限值分母", area: "截面面积", inertia: "截面惯性矩", section_modulus: "截面模量", shear_area: "抗剪面积", yield_strength: "屈服强度", damping_ratio: "阻尼比", walking_frequency: "步行激振频率", pedestrian_dynamic_force: "行人动力荷载", acceleration_limit: "加速度限值", wind_height: "迎风高度",
    concrete_elastic_modulus: "混凝土弹性模量", concrete_compressive_strength: "混凝土抗压强度", concrete_tensile_strength: "混凝土抗拉强度", rebar_yield_strength: "钢筋屈服强度", concrete_density: "混凝土重度", cover: "保护层", slab_bar_diameter: "板钢筋直径", slab_bar_spacing: "板钢筋间距", girder_bottom_area: "主梁底筋面积", girder_top_area: "主梁顶筋面积", girder_stirrup_area: "主梁箍筋面积", girder_stirrup_spacing: "主梁箍筋间距", minimum_vertical_frequency: "最小竖向频率", slab_deflection_ratio: "板挠度限值分母", girder_deflection_ratio: "梁挠度限值分母", cracked_stiffness_factor: "开裂刚度折减系数", railing_left: "左侧栏杆恒载", railing_right: "右侧栏杆恒载",
    length_x: "X向长度", width_y: "Y向宽度", column_x: "柱X向尺寸", column_y: "柱Y向尺寸", bar_diameter: "钢筋直径", provided_rebar_x: "X向配筋", provided_rebar_y: "Y向配筋", material_compressive_design: "材料抗压设计值", sliding_safety_factor: "抗滑安全系数", overturning_safety_factor: "抗倾覆安全系数", short_moment_capacity: "短向抗弯承载力", long_moment_capacity: "长向抗弯承载力", support_condition: "板边界条件", deflection_limit: "挠度限值", displacement_limit: "节点位移限值", roof_member_tributary_width: "屋面构件分担宽度", post_height: "面板中心离地高度", additional_ballast: "附加抗浮压重", antifloat_factor: "抗浮安全系数",
  };
  let base = key.replace(/_(kn_m3|mm2_m|kn_m_m|kn_m|m_s2|mpa|kpa|mm4|mm3|mm2|mm|deg|hz|kn|m|n)$/, "");
  let prefix = "";
  for (const [token, label] of [["timber_", "木面板·"], ["crossbeam_", "钢横梁·"], ["longitudinal_", "钢纵梁·"], ["cap_", "承台·"]]) {
    if (base.startsWith(token)) { prefix = label; base = base.slice(token.length); break; }
  }
  return prefix + (labels[base] ?? key);
}

/** First load-case problem that blocks evaluation, or "" when none. */
export function validateLoadCases(loadCases: SceneLoadCase[]): string {
  if (!loadCases.length) return "当前场景没有可用荷载包。";
  const invalidCustom = loadCases.find(
    (item) =>
      item.value_type === "project_defined" &&
      (!Number.isFinite(item.adopted_value) || !item.project_source?.trim() || !item.source_reference.trim()),
  );
  if (invalidCustom) return `“${invalidCustom.label}”需要填写数值、资料名称和来源页码/条款。`;
  const missingCalculatedValue = loadCases.find((item) => item.value_type === "calculated" && item.adopted_value <= 0);
  if (missingCalculatedValue) return `“${missingCalculatedValue.label}”需要通过风雪向导或项目资料填写最终采用值。`;
  const missingOverride = loadCases.find(
    (item) =>
      item.value_type !== "project_defined" &&
      item.recommended_default !== undefined &&
      item.adopted_value !== item.recommended_default &&
      !item.override_reason?.trim(),
  );
  if (missingOverride) return `“${missingOverride.label}”覆盖了建议值，请填写调整原因。`;
  return "";
}
