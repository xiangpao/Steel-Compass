// Pure builders for the project profiles a legacy scene saves with its
// revision. Each returns the profile or an error message for the user.

import type {
  ClimateRegionCatalog,
  ClimateRegionId,
  FoundationDesignSpecification,
  MemberSpecification,
  ProjectGeotechnicalProfile,
  ProjectSiteProfile,
  RoofAssembly,
  SceneConditionProfile,
  SceneStructuralProfile,
  SeismicDesignCatalog,
  SeismicLevel,
} from "@/lib/types";
import { toRoofForm, type DesignStage, type GroundwaterCondition, type SnowExposure } from "@/lib/scene-model";

export type Recurrence = "10" | "50" | "100";
export type Terrain = "A" | "B" | "C" | "D";
export type OptionalNumber = number | "";

export type SceneConditions = {
  climateLocationId: ClimateRegionId;
  recurrence: Recurrence;
  terrainCategory: Terrain;
  seismicLevel: SeismicLevel | "";
  snowExposure: SnowExposure;
  snowExemptionReason: string;
  optionalWindEnabled: boolean;
  manualWind: OptionalNumber;
  manualSnow: OptionalNumber;
  manualClimateSource: string;
  heightFactorOverride: OptionalNumber;
  shapeFactorOverride: OptionalNumber;
  snowFactorOverride: OptionalNumber;
  factorOverrideReason: string;
};

export const INITIAL_CONDITIONS: SceneConditions = {
  climateLocationId: "zhejiang_inland",
  recurrence: "50",
  terrainCategory: "B",
  seismicLevel: "",
  snowExposure: "exposed",
  snowExemptionReason: "",
  optionalWindEnabled: false,
  manualWind: "",
  manualSnow: "",
  manualClimateSource: "",
  heightFactorOverride: "",
  shapeFactorOverride: "",
  snowFactorOverride: "",
  factorOverrideReason: "",
};

export type SceneGeotech = {
  designStage: DesignStage;
  soilHintId: string;
  soilClass: string;
  bearingCapacity: OptionalNumber;
  bearingSource: string;
  baseFriction: OptionalNumber;
  groundwaterCondition: GroundwaterCondition;
  /** Legacy single water-table depth, kept only for saved drafts. */
  waterTableDepth: OptionalNumber;
  groundwaterSource: string;
  constructionWaterLevel: OptionalNumber;
  serviceWaterLevel: OptionalNumber;
  antifloatWaterLevel: OptionalNumber;
  reportName: string;
  reportDate: string;
  deformationModulus: OptionalNumber;
};

export const INITIAL_GEOTECH: SceneGeotech = {
  designStage: "scheme_estimate",
  soilHintId: "zj-inland-alluvial",
  soilClass: "可塑黏性土或中密粉土",
  bearingCapacity: "",
  bearingSource: "浙江区域参考档，用户已确认现场土质类别",
  baseFriction: "",
  groundwaterCondition: "unknown",
  waterTableDepth: "",
  groundwaterSource: "",
  constructionWaterLevel: "",
  serviceWaterLevel: "",
  antifloatWaterLevel: "",
  reportName: "",
  reportDate: "",
  deformationModulus: "",
};

/** Zhejiang regional soil reference classes for scheme estimates. */
export const SOIL_HINTS: Record<string, { title: string; soilClass: string; bearing: number }> = {
  "zj-coastal-soft-clay": { title: "浙江沿海平原—软黏土参考档", soilClass: "软塑至流塑黏性土", bearing: 60 },
  "zj-inland-alluvial": { title: "浙江内陆平原—一般黏性土参考档", soilClass: "可塑黏性土或中密粉土", bearing: 100 },
  "zj-mountain-residual": { title: "浙江山地丘陵—残积土参考档", soilClass: "可塑至硬塑残积土", bearing: 160 },
};

export type VerticalEnclosure = "none" | "open_members" | "perforated_panel" | "solid_panel";
export type TopCover = "none" | "louver_grid" | "permeable_cover" | "solid_roof";

export type SceneExposure = {
  verticalEnclosure: VerticalEnclosure;
  topCover: TopCover;
  verticalOpenRatio: OptionalNumber;
  topOpenRatio: OptionalNumber;
  roofAssemblyId: string;
};

export function geotechFromProfile(profile: ProjectGeotechnicalProfile): Partial<SceneGeotech> {
  return {
    designStage: profile.stage,
    soilHintId: profile.regional_hint_id ?? "",
    soilClass: profile.confirmed_soil_class,
    bearingCapacity: profile.bearing_capacity_kpa,
    bearingSource: profile.bearing_capacity_source,
    groundwaterCondition: profile.groundwater.condition === "known_levels" ? "known_water_table" : profile.groundwater.condition,
    constructionWaterLevel: profile.groundwater.construction_level_m ?? "",
    serviceWaterLevel: profile.groundwater.service_level_m ?? "",
    antifloatWaterLevel: profile.groundwater.antifloat_level_m ?? "",
    baseFriction: profile.base_friction_coefficient ?? "",
    groundwaterSource: profile.groundwater.source,
    reportName: profile.report_name ?? "",
    reportDate: profile.report_date ?? "",
    deformationModulus: profile.deformation_modulus_mpa ?? "",
  };
}

export function conditionsFromSiteProfile(profile: ProjectSiteProfile): Partial<SceneConditions> {
  const manual = profile.region_preset === "manual";
  return {
    ...(profile.region_preset ? { climateLocationId: profile.region_preset } : {}),
    recurrence: String(profile.recurrence_period_years) as Recurrence,
    terrainCategory: profile.terrain_category,
    ...(profile.seismic_level ? { seismicLevel: profile.seismic_level } : {}),
    manualWind: manual ? profile.basic_wind_pressure_kpa ?? "" : "",
    manualSnow: manual ? profile.basic_snow_pressure_kpa ?? "" : "",
    manualClimateSource: manual ? profile.climate_source_reference ?? "" : "",
    heightFactorOverride: profile.height_factor_override ?? "",
    shapeFactorOverride: profile.wind_shape_factor_override ?? "",
    snowFactorOverride: profile.snow_shape_factor_override ?? "",
    factorOverrideReason: profile.override_reason ?? "",
  };
}

export type SemanticFactors = {
  heightFactor: number;
  windShape: number;
  snowShape: number;
  structureShape: "roof" | "solid_panel" | "open_frame";
  roofForm: "flat" | "single_slope" | "double_slope" | "other";
};

export function semanticFactors(
  conditionProfile: SceneConditionProfile,
  parameters: Record<string, unknown>,
  variantRoofForm: string | undefined,
  conditions: SceneConditions,
): SemanticFactors {
  const height =
    conditionProfile.height_parameter_keys
      .map((key) => Number(parameters[key]))
      .find((value) => Number.isFinite(value) && value > 0) ??
    Number(parameters.height_m ?? parameters.height ?? parameters.column_height_m ?? 5);
  const terrain = { A: 0.85, B: 1, C: 1.15, D: 1.3 }[conditions.terrainCategory];
  const structureShape =
    conditionProfile.wind_semantics === "roof"
      ? "roof"
      : conditionProfile.wind_semantics === "solid_panel"
        ? "solid_panel"
        : "open_frame";
  const roofSource =
    (conditionProfile.roof_form_parameter_key ? parameters[conditionProfile.roof_form_parameter_key] : undefined) ??
    variantRoofForm;
  const roofForm = conditionProfile.snow_semantics === "exposed_horizontal" ? "flat" : toRoofForm(roofSource);
  const heightFactor =
    conditions.heightFactorOverride === ""
      ? terrain * (height <= 5 ? 0.9 : height <= 10 ? 1 : 1.1)
      : conditions.heightFactorOverride;
  return {
    heightFactor: Number(heightFactor.toFixed(3)),
    windShape:
      conditions.shapeFactorOverride === ""
        ? { open_frame: 0.8, solid_panel: 1.3, roof: 0.9 }[structureShape]
        : conditions.shapeFactorOverride,
    snowShape:
      conditions.snowFactorOverride === ""
        ? { flat: 0.8, single_slope: 1, double_slope: 1, other: 1.2 }[roofForm]
        : conditions.snowFactorOverride,
    structureShape,
    roofForm,
  };
}

type ProfileResult<T> = { profile: T | null; error?: string };

export function buildSiteProfile({
  existing,
  conditions,
  factors,
  needs,
  selectedClimate,
  climateCatalog,
  seismicCatalog,
}: {
  existing: ProjectSiteProfile | null;
  conditions: SceneConditions;
  factors: SemanticFactors;
  needs: { wind: boolean; snow: boolean; seismic: boolean };
  selectedClimate: ClimateRegionCatalog["items"][number] | undefined;
  climateCatalog?: ClimateRegionCatalog | null;
  seismicCatalog?: SeismicDesignCatalog | null;
}): ProfileResult<ProjectSiteProfile> {
  if (!needs.wind && !needs.snow && !needs.seismic) return { profile: existing };
  const completed = new Set(existing?.completed_conditions ?? []);
  const profile: ProjectSiteProfile = {
    ...(existing ?? {}),
    profile_version: "1.1",
    recurrence_period_years: Number(conditions.recurrence) as 10 | 50 | 100,
    terrain_category: conditions.terrainCategory,
    structure_shape: factors.structureShape,
    roof_form: factors.roofForm,
    catalog_versions: {
      ...(existing?.catalog_versions ?? {}),
      climate_regions: climateCatalog?.version ?? "unknown",
      seismic: seismicCatalog?.version ?? "unknown",
      standards: "CN-2026.6",
    },
  };

  if (needs.wind || needs.snow) {
    if (!selectedClimate) return { profile: null, error: "请选择项目地区档。 " };
    const isManual = conditions.climateLocationId === "manual";
    const wind = isManual ? Number(conditions.manualWind) : selectedClimate.wind_kpa[conditions.recurrence];
    const snow = isManual ? Number(conditions.manualSnow) : selectedClimate.snow_kpa[conditions.recurrence];
    if (needs.wind && (!Number.isFinite(wind) || wind <= 0)) return { profile: null, error: "请填写有效的基本风压。" };
    if (needs.snow && (!Number.isFinite(snow) || snow < 0)) return { profile: null, error: "请填写有效的基本雪压。" };
    if (isManual && conditions.manualClimateSource.trim().length < 4) {
      return { profile: null, error: "其他地区必须填写项目资料来源。 " };
    }
    if (needs.snow && conditions.snowExposure === "not_applicable" && conditions.snowExemptionReason.trim().length < 4) {
      return { profile: null, error: "不计露天积雪时，请填写项目依据。 " };
    }
    profile.region_preset = conditions.climateLocationId;
    profile.climate_source_reference = isManual ? conditions.manualClimateSource.trim() : selectedClimate.source_reference;
    if (needs.wind) {
      profile.basic_wind_pressure_kpa = wind;
      completed.add("wind");
    }
    if (needs.snow) {
      profile.basic_snow_pressure_kpa = snow;
      completed.add("snow");
    }
  }
  if (needs.seismic) {
    if (!conditions.seismicLevel) {
      return { profile: null, error: "请选择地震烈度与设计基本加速度；软件不会代填默认值。 " };
    }
    profile.seismic_level = conditions.seismicLevel;
    completed.add("seismic");
  }
  const changedWindFactor = needs.wind && (conditions.heightFactorOverride !== "" || conditions.shapeFactorOverride !== "");
  const changedSnowFactor = needs.snow && conditions.snowFactorOverride !== "";
  if ((changedWindFactor || changedSnowFactor) && !conditions.factorOverrideReason.trim()) {
    return { profile: null, error: "修改高级系数时必须填写覆盖原因。 " };
  }
  if (needs.wind) {
    profile.height_factor_override = conditions.heightFactorOverride === "" ? null : conditions.heightFactorOverride;
    profile.wind_shape_factor_override = conditions.shapeFactorOverride === "" ? null : conditions.shapeFactorOverride;
  }
  if (needs.snow) {
    profile.snow_shape_factor_override = conditions.snowFactorOverride === "" ? null : conditions.snowFactorOverride;
  }
  if (changedWindFactor || changedSnowFactor) profile.override_reason = conditions.factorOverrideReason.trim();
  profile.completed_conditions = Array.from(completed);
  return { profile };
}

export function buildGeotechnicalProfile(geotech: SceneGeotech): ProfileResult<ProjectGeotechnicalProfile> {
  const optional = (value: OptionalNumber) => (value === "" ? null : Number(value));
  if (!geotech.bearingCapacity || !geotech.soilClass.trim() || !geotech.bearingSource.trim()) {
    return { profile: null, error: "请确认土质类别、地基承载力和资料来源；软件不再代填 120 kPa。" };
  }
  if (!geotech.groundwaterSource.trim() || geotech.groundwaterCondition === "unknown") {
    return { profile: null, error: "请明确地下水边界及资料来源；未知水位不能作为基础计算输入。" };
  }
  if (
    geotech.groundwaterCondition === "known_water_table" &&
    [geotech.constructionWaterLevel, geotech.serviceWaterLevel, geotech.antifloatWaterLevel].some((value) => value === "")
  ) {
    return { profile: null, error: "已知地下水时必须填写施工期、正常使用和抗浮设计水位标高。" };
  }
  if (geotech.designStage === "project_check" && (!geotech.reportName.trim() || !geotech.reportDate || !geotech.deformationModulus)) {
    return { profile: null, error: "工程校核需要勘察报告名称、日期及沉降计算参数；资料不足时请选择方案测算。" };
  }
  return {
    profile: {
      profile_version: "1.0",
      stage: geotech.designStage,
      regional_hint_id: geotech.designStage === "scheme_estimate" ? geotech.soilHintId : null,
      confirmed_soil_class: geotech.soilClass.trim(),
      bearing_capacity_kpa: Number(geotech.bearingCapacity),
      bearing_capacity_source: geotech.bearingSource.trim(),
      deformation_modulus_mpa: optional(geotech.deformationModulus),
      base_friction_coefficient: optional(geotech.baseFriction),
      groundwater: {
        condition: geotech.groundwaterCondition === "known_water_table" ? "known_levels" : geotech.groundwaterCondition,
        construction_level_m: optional(geotech.constructionWaterLevel),
        service_level_m: optional(geotech.serviceWaterLevel),
        antifloat_level_m: optional(geotech.antifloatWaterLevel),
        source: geotech.groundwaterSource.trim(),
      },
      report_name: geotech.reportName.trim() || null,
      report_date: geotech.reportDate || null,
      catalog_versions: { geotechnical_hints: "zhejiang-geotech-2026.1-unverified" },
    },
  };
}

export function buildStructuralProfile({
  steelNodeIds,
  foundationNodeIds,
  memberSpecifications,
  foundationSpecifications,
  designStage,
  needsWind,
  exposure,
  roofForm,
  roofAssembly,
}: {
  steelNodeIds: Set<string>;
  foundationNodeIds: Set<string>;
  memberSpecifications: MemberSpecification[];
  foundationSpecifications: FoundationDesignSpecification[];
  designStage: DesignStage;
  needsWind: boolean;
  exposure: SceneExposure;
  roofForm: SemanticFactors["roofForm"];
  /** Selected roof assembly, or undefined when the scene has no roof. */
  roofAssembly: RoofAssembly | null | undefined;
}): ProfileResult<SceneStructuralProfile> {
  const members = memberSpecifications.filter((item) => steelNodeIds.has(item.node_id));
  const foundations = foundationSpecifications
    .filter((item) => foundationNodeIds.has(item.node_id))
    .map((item) => ({
      ...item,
      concrete_grade: item.concrete_grade ?? "C30",
      rebar_grade: item.rebar_grade ?? "HRB400",
      bar_diameter_mm: item.bar_diameter_mm ?? 14,
      bar_spacing_mm: item.bar_spacing_mm ?? 150,
      section_shape: item.section_shape ?? ("stepped" as const),
      steps:
        item.section_shape === "tapered" || item.section_shape === "prismatic"
          ? (item.steps ?? [])
          : item.steps?.length
            ? item.steps
            : [{ length_m: Math.max(0.5, item.length_m - 0.6), width_m: Math.max(0.5, item.width_m - 0.6), height_mm: 250 }],
      reinforcement: item.reinforcement ?? {
        bottom_x_diameter_mm: item.bar_diameter_mm ?? 14,
        bottom_x_spacing_mm: item.bar_spacing_mm ?? 150,
        bottom_y_diameter_mm: item.bar_diameter_mm ?? 14,
        bottom_y_spacing_mm: item.bar_spacing_mm ?? 150,
      },
    }));
  if ((steelNodeIds.size && !members.length) || (foundationNodeIds.size && !foundations.length)) {
    return { profile: null, error: "请先明确所有钢构件截面和基础尺寸。" };
  }
  const optional = (value: OptionalNumber) => (value === "" ? null : Number(value));
  return {
    profile: {
      profile_version: "3.0",
      stage: designStage,
      exposure: needsWind
        ? {
            vertical_enclosure: exposure.verticalEnclosure,
            top_cover: exposure.topCover,
            vertical_open_ratio: optional(exposure.verticalOpenRatio),
            top_open_ratio: optional(exposure.topOpenRatio),
            roof_form: exposure.topCover === "solid_roof" ? roofForm : null,
            source: "场景几何与用户确认的围护/顶部覆盖",
          }
        : null,
      members,
      // Geometry, member groups and per-member overrides are only produced by
      // the pergola workbench; legacy scenes send explicit member specs.
      member_groups: [],
      member_overrides: [],
      foundations,
      geometry: null,
      roof_assembly: roofAssembly ?? null,
      catalog_versions: {
        steel_sections: "steel-sections-2026.2-unverified",
        foundation_systems: "foundation-systems-2026.2-unverified",
        roof_assemblies: "roof-assemblies-2026.1-unverified",
      },
    },
  };
}

