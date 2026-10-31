// Pure conversions between workbench input state and the project payloads
// saved by the pergola workbench.

import { evidenceStatus } from "@/lib/evidence-status";
import { DEFAULT_SECTIONS, INITIAL_REPORT, SOIL_PRESETS, type AnalysisResult, type SectionDraft, type SoilPreset } from "@/lib/pergola-catalog";
import type { CustomSectionDefinition, MemberTypeDefinition, ProjectGeotechnicalProfile } from "@/lib/types";

export type GeoReport = typeof INITIAL_REPORT;
export type GeoStage = "scheme_estimate" | "project_check";
export type MaintenanceCategory = "none" | "maintenance" | "walkway" | "occupied" | "custom";

export function buildGeotechnicalProfile(geoStage: GeoStage, soil: SoilPreset, soilPresetId: string, report: GeoReport): ProjectGeotechnicalProfile {
  const hints = { geotechnical_hints: "geotechnical-hints-cn-2026.1-unverified" };
  if (geoStage === "project_check") {
    const source = `勘察报告：${report.name}`;
    return {
      profile_version: "1.1",
      stage: "project_check",
      regional_hint_id: null,
      confirmed_soil_class: soil.title,
      bearing_capacity_kpa: report.bearing,
      bearing_capacity_source: source,
      deformation_modulus_mpa: report.modulus,
      compression_modulus_mpa: null,
      settlement_layers: [
        {
          id: "layer-1",
          name: "持力层及主要压缩层",
          thickness_m: report.layerThickness,
          compression_modulus_mpa: report.modulus,
          unit_weight_kn_m3: report.unitWeight,
          source,
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
        source,
        observation_date: report.date || null,
      },
      report_name: report.name,
      report_date: report.date || null,
      catalog_versions: hints,
    };
  }
  return {
    profile_version: "1.0",
    stage: "scheme_estimate",
    regional_hint_id: soilPresetId,
    confirmed_soil_class: soil.title,
    bearing_capacity_kpa: soil.adopted,
    bearing_capacity_source: `方案持力层参考档：${soil.title}`,
    deformation_modulus_mpa: null,
    compression_modulus_mpa: null,
    base_friction_coefficient: soil.friction,
    groundwater: { condition: "no_influence", source: "方案阶段暂按地下水不影响；改变此条件必须重新分析" },
    report_name: null,
    report_date: null,
    catalog_versions: hints,
  };
}

/** Restore the geotechnical UI state from a saved project profile. */
export function geotechnicalUiState(profile: ProjectGeotechnicalProfile): { report: GeoReport; soilPresetId: string; geoStage: GeoStage } {
  const soilPresetId =
    SOIL_PRESETS.find((item) => item.id === profile.regional_hint_id || item.title === profile.confirmed_soil_class)?.id ?? "plastic-clay";
  const layer = profile.settlement_layers?.[0];
  return {
    soilPresetId,
    geoStage: profile.stage,
    report: {
      name: profile.report_name ?? "",
      date: profile.report_date ?? "",
      bearing: profile.bearing_capacity_kpa,
      modulus: profile.deformation_modulus_mpa ?? layer?.compression_modulus_mpa ?? 0,
      layerThickness: layer?.thickness_m ?? 0,
      unitWeight: layer?.unit_weight_kn_m3 ?? 18,
      settlementFactor: profile.settlement_correction_factor ?? 1,
      settlementLimit: profile.settlement_limit_mm ?? 0,
      construction: profile.groundwater.construction_level_m ?? 0,
      service: profile.groundwater.service_level_m ?? 0,
      antifloat: profile.groundwater.antifloat_level_m ?? 0,
      friction: profile.base_friction_coefficient ?? 0.25,
    },
  };
}

/** Section drafts of member types whose saved section is an editable SHS/RHS/H profile. */
export function sectionDraftsFromCatalog(
  current: Record<string, SectionDraft>,
  memberTypes: MemberTypeDefinition[],
  catalog: CustomSectionDefinition[],
): Record<string, SectionDraft> {
  const next = { ...current };
  for (const type of memberTypes) {
    const section = catalog.find((item) => item.id === type.section_id);
    if (!section || !["SHS", "RHS", "H"].includes(section.family)) continue;
    const d = section.dimensions;
    next[type.id] = {
      family: section.family as SectionDraft["family"],
      h: d.h_mm ?? 100,
      b: d.b_mm ?? d.h_mm ?? 100,
      tw: d.t_mm ?? d.tw_mm ?? 4,
      tf: d.tf_mm ?? d.t_mm ?? 4,
    };
  }
  return next;
}

export function sectionDimensions(draft: SectionDraft): Record<string, number> {
  return draft.family === "H"
    ? { h_mm: draft.h, b_mm: draft.b, tw_mm: draft.tw, tf_mm: draft.tf }
    : { h_mm: draft.h, b_mm: draft.family === "SHS" ? draft.h : draft.b, t_mm: draft.tw };
}

export function sectionDraftFor(drafts: Record<string, SectionDraft>, typeId: string): SectionDraft {
  return drafts[typeId] ?? DEFAULT_SECTIONS.secondary;
}

/**
 * Evidence wording of a pergola analysis. Every check is unverified, so the
 * workflow is a scheme screening whichever geotechnical stage was requested.
 */
export function analysisEvidence(workflowStatus: AnalysisResult["workflow_status"]) {
  return evidenceStatus({ result_class: "scheme_estimate", workflow_status: workflowStatus, verification_status: "unverified" });
}

export function roofLoadSelection(roofAssemblyCatalogId: string, category: MaintenanceCategory, maintenanceLoad: number) {
  const maintenance = category === "none" ? "not_applicable" : category === "walkway" ? "walkway_equipment" : category;
  return {
    roof_assembly_id: roofAssemblyCatalogId,
    maintenance_category: maintenance,
    maintenance_load_kn_m2: maintenance === "maintenance" || maintenance === "not_applicable" ? null : maintenanceLoad,
    concentrated_maintenance_check_required: maintenance === "maintenance",
    custom_basis: maintenance === "custom" ? "亭廊工作台用户自定义" : null,
  };
}
