"use client";

import {
  AlertTriangle,
  Archive,
  Check,
  ChevronDown,
  CircleDot,
  Copy,
  FileClock,
  GitCompare,
  Pencil,
  Plus,
  RotateCcw,
  Save,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { api, errorMessage } from "@/lib/api";
import { HelpTip } from "@/components/help-tip";
import { PergolaWorkbenchV2 } from "@/components/pergola-workbench-v2";
import { SceneModelPreview } from "@/components/scene-model-preview";
import { MODULE_MAP, normalizeInputs } from "@/lib/modules";
import type {
  ClimateRegionCatalog,
  ClimateRegionId,
  CustomSectionDefinition,
  LoadItem,
  Mode,
  Module,
  Project,
  ProjectSiteProfile,
  ProjectGeotechnicalProfile,
  RoofAssembly,
  SceneStructuralProfile,
  SectionCatalogEntry,
  MemberSpecification,
  FoundationDesignSpecification,
  SceneFamily,
  SceneGraphTemplate,
  SceneGeometryProfile,
  SceneConditionProfile,
  SceneInstance,
  SceneLoadCase,
  SceneRevision,
  SceneVariant,
  SeismicDesignCatalog,
  SeismicLevel,
} from "@/lib/types";

const STATUS_LABELS = {
  completed: "已录入",
  passed: "已完成",
  failed: "不满足",
  incomplete: "待补齐",
  not_applicable: "不适用",
};

type Props = {
  family: SceneFamily;
  projects: Project[];
  onProjectsChange: (projects: Project[]) => void;
  climateCatalog?: ClimateRegionCatalog | null;
  seismicCatalog?: SeismicDesignCatalog | null;
};

type WorkspaceTab = "settings" | "results";
type GroundwaterCondition = "no_influence" | "known_water_table" | "unknown";
type SnowExposure = "exposed" | "not_applicable";
type DesignStage = "scheme_estimate" | "project_check";

const PlanModelEditor = dynamic(
  () => import("@/components/plan-model-editor").then((module) => module.PlanModelEditor),
  { ssr: false },
);

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

function sceneConditionProfile(
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

function toRoofForm(value: unknown): "flat" | "single_slope" | "double_slope" | "other" {
  const name = String(value ?? "");
  if (name.includes("单坡")) return "single_slope";
  if (name.includes("双坡")) return "double_slope";
  if (name.includes("平")) return "flat";
  return "other";
}

function initialValues(family: SceneFamily, variantId: string) {
  const variant =
    family.variants.find((item) => item.id === variantId) ?? family.variants[0];
  return Object.fromEntries(
    (variant?.parameters ?? []).map((parameter) => [
      parameter.key,
      parameter.default ?? "",
    ]),
  );
}

function graphFor(family: SceneFamily, variant?: SceneVariant): SceneGraphTemplate {
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

function copiedLoadCases(
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

function currentLoadCases(items: SceneLoadCase[]): SceneLoadCase[] {
  return items.map((item) => {
    const { confirmed: _legacyConfirmation, ...current } = item as SceneLoadCase & {
      confirmed?: boolean;
    };
    void _legacyConfirmation;
    return current;
  });
}

function controllingUtilization(revision: SceneRevision): number | null {
  const values = Object.values(revision.result_bundle).flatMap((result) =>
    result.checks.map((check) => check.utilization),
  );
  return values.length ? Math.max(...values) : null;
}

function resultStatus(revision: SceneRevision): string {
  if (["quick_estimate", "scheme_estimate"].includes(revision.scene_result.result_class ?? "")) {
    return revision.scene_result.quick_outcome === "screening_failed"
      ? "方案筛查需调整"
      : "方案筛查完成";
  }
  return revision.scene_result.engineering_status === "passed"
    ? "专业检查通过"
    : revision.scene_result.engineering_status === "failed"
      ? "专业检查不满足"
      : "专业检查待补齐";
}

function loadRange(item: SceneLoadCase) {
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

function foundationTypeForGraph(graph: SceneGraphTemplate | undefined): string {
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

function normalizedFoundations(items: FoundationDesignSpecification[]): FoundationDesignSpecification[] {
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

function defaultCustomSectionDimensions(family: "SHS" | "RHS" | "CHS" | "H" | "I"): Record<string, number> {
  if (family === "SHS") return { h_mm: 150, b_mm: 150, t_mm: 6 };
  if (family === "RHS") return { h_mm: 200, b_mm: 100, t_mm: 6 };
  if (family === "CHS") return { diameter_mm: 168, t_mm: 6 };
  return { h_mm: 250, b_mm: 125, tw_mm: 6, tf_mm: 9 };
}

const CUSTOM_SECTION_DIMENSION_LABELS: Record<string, string> = {
  h_mm: "截面高度",
  b_mm: "截面宽度",
  t_mm: "壁厚",
  diameter_mm: "外径",
  tw_mm: "腹板厚度",
  tf_mm: "翼缘厚度",
};

export function SceneWorkspace(props: Props) {
  if (props.family.id === "pergola-pavilion") {
    return <PergolaWorkbenchV2 mode="project" projects={props.projects} onProjectsChange={props.onProjectsChange} />;
  }
  return <LegacySceneWorkspace {...props} />;
}

function LegacySceneWorkspace({
  family,
  projects,
  onProjectsChange,
  climateCatalog,
  seismicCatalog,
}: Props) {
  const initialVariantId =
    family.default_variant_id ?? family.variants[0]?.id ?? "";
  const [variantId, setVariantId] = useState(initialVariantId);
  const [mode, setMode] = useState<Mode>("quick");
  const [tab, setTab] = useState<WorkspaceTab>("settings");
  const [material, setMaterial] = useState(
    family.variants.find((item) => item.id === initialVariantId)
      ?.material_systems[0] ?? "",
  );
  const [parameters, setParameters] = useState<Record<string, unknown>>(
    initialValues(family, initialVariantId),
  );
  const [loadCases, setLoadCases] = useState<SceneLoadCase[]>([]);
  const [foundationType, setFoundationType] = useState("独立基础");
  const [bearingCapacity, setBearingCapacity] = useState<number | "">("");
  const [groundwaterCondition, setGroundwaterCondition] =
    useState<GroundwaterCondition>("unknown");
  const [waterTableDepth, setWaterTableDepth] = useState<number | "">("");
  const [groundwaterSource, setGroundwaterSource] = useState("");
  const [designStage, setDesignStage] = useState<DesignStage>("scheme_estimate");
  const [soilHintId, setSoilHintId] = useState("zj-inland-alluvial");
  const [soilClass, setSoilClass] = useState("可塑黏性土或中密粉土");
  const [bearingSource, setBearingSource] = useState("浙江区域参考档，用户已确认现场土质类别");
  const [constructionWaterLevel, setConstructionWaterLevel] = useState<number | "">("");
  const [serviceWaterLevel, setServiceWaterLevel] = useState<number | "">("");
  const [antifloatWaterLevel, setAntifloatWaterLevel] = useState<number | "">("");
  const [geotechnicalReportName, setGeotechnicalReportName] = useState("");
  const [geotechnicalReportDate, setGeotechnicalReportDate] = useState("");
  const [deformationModulus, setDeformationModulus] = useState<number | "">("");
  const [steelSections, setSteelSections] = useState<SectionCatalogEntry[]>([]);
  const [customSections, setCustomSections] = useState<CustomSectionDefinition[]>([]);
  const [customSectionOpen, setCustomSectionOpen] = useState(false);
  const [customSectionName, setCustomSectionName] = useState("项目自定义矩形管");
  const [customSectionFamily, setCustomSectionFamily] = useState<"SHS" | "RHS" | "CHS" | "H" | "I">("RHS");
  const [customSectionDimensions, setCustomSectionDimensions] = useState<Record<string, number>>({ h_mm: 200, b_mm: 100, t_mm: 6 });
  const [customCornerRadius, setCustomCornerRadius] = useState<number | "">("");
  const [customSectionPreview, setCustomSectionPreview] = useState<CustomSectionDefinition | null>(null);
  const [roofAssemblies, setRoofAssemblies] = useState<RoofAssembly[]>([]);
  const [roofAssemblyId, setRoofAssemblyId] = useState("steel-panel");
  const [layoutMode, setLayoutMode] = useState<"preset" | "custom_grid">("custom_grid");
  const [xBaySpans, setXBaySpans] = useState("4");
  const [yBaySpans, setYBaySpans] = useState("3,3");
  const [columnHeights, setColumnHeights] = useState("3");
  const [omittedColumns, setOmittedColumns] = useState("");
  const [roofGeometry, setRoofGeometry] = useState<"flat" | "single_slope" | "double_slope" | "custom_heights">("flat");
  const [roofSlopeDeg, setRoofSlopeDeg] = useState(8);
  const [roofDirectionDeg, setRoofDirectionDeg] = useState(0);
  const [geometryOverride, setGeometryOverride] = useState<SceneGeometryProfile | null>(null);
  const [modelSelection, setModelSelection] = useState<{ kind: "node" | "member"; id: string } | null>(null);
  const [modelMessage, setModelMessage] = useState("选择构件可查看并修改属性。");
  const [memberGroupSections, setMemberGroupSections] = useState<Record<string, string>>({});
  const [memberSectionOverrides, setMemberSectionOverrides] = useState<Record<string, string>>({});
  const [memberSpecifications, setMemberSpecifications] = useState<MemberSpecification[]>([]);
  const [foundationSpecifications, setFoundationSpecifications] = useState<FoundationDesignSpecification[]>([]);
  const [verticalEnclosure, setVerticalEnclosure] = useState<"none" | "open_members" | "perforated_panel" | "solid_panel">("none");
  const [topCover, setTopCover] = useState<"none" | "louver_grid" | "permeable_cover" | "solid_roof">("none");
  const [verticalOpenRatio, setVerticalOpenRatio] = useState<number | "">("");
  const [topOpenRatio, setTopOpenRatio] = useState<number | "">("");
  const [climateLocationId, setClimateLocationId] = useState<ClimateRegionId>("zhejiang_inland");
  const [recurrence, setRecurrence] = useState<"10" | "50" | "100">("50");
  const [terrainCategory, setTerrainCategory] = useState<"A" | "B" | "C" | "D">("B");
  const [seismicLevel, setSeismicLevel] = useState<SeismicLevel | "">("");
  const [snowExposure, setSnowExposure] = useState<SnowExposure>("exposed");
  const [snowExemptionReason, setSnowExemptionReason] = useState("");
  const [optionalWindEnabled, setOptionalWindEnabled] = useState(false);
  const [manualWind, setManualWind] = useState<number | "">("");
  const [manualSnow, setManualSnow] = useState<number | "">("");
  const [manualClimateSource, setManualClimateSource] = useState("");
  const [advancedClimateOpen, setAdvancedClimateOpen] = useState(false);
  const [heightFactorOverride, setHeightFactorOverride] = useState<number | "">("");
  const [shapeFactorOverride, setShapeFactorOverride] = useState<number | "">("");
  const [snowFactorOverride, setSnowFactorOverride] = useState<number | "">("");
  const [factorOverrideReason, setFactorOverrideReason] = useState("");
  const [selectedProject, setSelectedProject] = useState<number | "new">("new");
  const [sceneTitle, setSceneTitle] = useState(family.title);
  const [instance, setInstance] = useState<SceneInstance | null>(null);
  const [revision, setRevision] = useState<SceneRevision | null>(null);
  const [projectInstances, setProjectInstances] = useState<SceneInstance[]>([]);
  const [instanceRevisions, setInstanceRevisions] = useState<
    Record<number, SceneRevision[]>
  >({});
  const [inputVersion, setInputVersion] = useState(0);
  const [calculatedVersion, setCalculatedVersion] = useState(-1);
  const [changedNodeIds, setChangedNodeIds] = useState<string[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const hydrated = useRef(false);
  const projectLoadSequence = useRef(0);
  const suppressNextProjectLoad = useRef(false);
  const preserveHydratedGeometry = useRef(false);

  const variant = useMemo(
    () =>
      family.variants.find((item) => item.id === variantId) ??
      family.variants[0],
    [family, variantId],
  );
  const isParametricPergola = family.id === "pergola-pavilion";
  const availableSections = useMemo<SectionCatalogEntry[]>(
    () => [
      ...steelSections,
      ...customSections.map((item) => ({
        id: item.id,
        family: item.family,
        designation: `${item.name}（项目自定义）`,
        dimensions: item.dimensions,
        area_mm2: item.area_mm2,
        self_weight_kn_m: item.self_weight_kn_m,
        material_grades: ["Q235B", "Q355B"],
        source_reference: item.source_reference,
      })),
    ],
    [customSections, steelSections],
  );
  const conditionProfile = useMemo(
    () => sceneConditionProfile(family, variant),
    [family, variant],
  );
  const needsWind =
    conditionProfile.wind === "required" ||
    (conditionProfile.wind === "optional" && optionalWindEnabled);
  const needsSnow = conditionProfile.snow === "required";
  const needsSeismic = conditionProfile.seismic === "required";
  const hasConditions = needsWind || needsSnow || needsSeismic;
  const graph = useMemo(() => graphFor(family, variant), [family, variant]);
  const visibleNodes = useMemo(
    () =>
      graph.nodes.filter(
        (node) => node.applicability !== "not_applicable",
      ),
    [graph],
  );
  const foundationModules = useMemo(
    () =>
      new Set(
        visibleNodes
          .filter((node) => node.role === "foundation")
          .map((node) => node.calculation_module)
          .filter((module): module is string => Boolean(module)),
      ),
    [visibleNodes],
  );
  const hasFoundation = foundationModules.size > 0;
  const hasGenericFoundation =
    hasFoundation && conditionProfile.geotechnical_mode !== "variant_owned";
  const visibleParameters = isParametricPergola
    ? []
    : (variant?.parameters ?? []).filter(
        (parameter) => !parameter.hidden_when_condition_driven,
      );
  const stale = Boolean(revision && inputVersion !== calculatedVersion);
  const loadPackageTitle = variant?.load_package?.title ?? "场景荷载包";
  const comparisonInstances = projectInstances.slice(0, 3);

  useEffect(() => {
    api<{ items: SectionCatalogEntry[] }>("/api/v2/catalogs/steel-sections")
      .then((catalog) => setSteelSections(catalog.items))
      .catch(() => setSteelSections([]));
  }, []);

  useEffect(() => {
    if (selectedProject === "new") {
      setCustomSections([]);
      return;
    }
    api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${selectedProject}/custom-sections`)
      .then((result) => setCustomSections(result.items))
      .catch(() => setCustomSections([]));
  }, [selectedProject]);

  useEffect(() => {
    api<{ items: RoofAssembly[] }>("/api/v2/catalogs/roof-assemblies")
      .then((catalog) => setRoofAssemblies(catalog.items))
      .catch(() => setRoofAssemblies([]));
  }, []);

  useEffect(() => {
    if (!customSectionOpen || !customSectionName.trim()) return;
    let active = true;
    const timer = window.setTimeout(() => {
      api<CustomSectionDefinition>("/api/v2/catalogs/custom-section-properties", {
        method: "POST",
        body: JSON.stringify({
          id: "custom-preview",
          name: customSectionName.trim(),
          family: customSectionFamily,
          dimensions: customSectionDimensions,
          corner_radius_mm: customCornerRadius === "" ? null : customCornerRadius,
          source_reference: "用户几何实时计算预览",
        }),
      }).then((value) => { if (active) setCustomSectionPreview(value); })
        .catch(() => { if (active) setCustomSectionPreview(null); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [customCornerRadius, customSectionDimensions, customSectionFamily, customSectionName, customSectionOpen]);

  useEffect(() => {
    if (!availableSections.length) return;
    const steelNodes = visibleNodes.filter((node) =>
      ["steel_beam", "steel_column", "portal_frame"].includes(
        node.calculation_module ?? "",
      ),
    );
    setMemberSpecifications((current) => {
      const currentByKey = new Map(
        current.map((item) => [`${item.node_id}:${item.member_role}`, item]),
      );
      return steelNodes.flatMap((node) => {
        const roles =
          node.calculation_module === "portal_frame"
            ? ["beam", "column"]
            : [node.calculation_module === "steel_beam" ? "beam" : "column"];
        return roles.map((role) => {
          const existing = currentByKey.get(`${node.id}:${role}`);
          if (existing) return existing;
          const preferred = availableSections.find((item) =>
            role === "column"
              ? item.id === "shs-150x6"
              : item.id === "rhs-200x100x6",
          ) ?? availableSections[0];
          const length = Number(
            role === "column"
              ? parameters.height_m ?? parameters.column_height_m ?? 3
              : parameters.span_m ?? parameters.length_m ?? 5,
          );
          return {
            node_id: node.id,
            member_role: role,
            material_grade: "Q355B",
            section_catalog_id: preferred.id,
            section_type: preferred.family,
            section_name: preferred.designation,
            orientation: "strong_axis" as const,
            effective_length_m: length,
            unbraced_length_m: length,
            selection_source: "recommended" as const,
          };
        });
      });
    });
  }, [availableSections, visibleNodes, parameters.height_m, parameters.column_height_m, parameters.span_m, parameters.length_m]);

  useEffect(() => {
    const nodes = visibleNodes.filter(
      (node) =>
        node.role === "foundation" &&
        ["spread_footing", "strip_footing"].includes(node.calculation_module ?? ""),
    );
    setFoundationSpecifications((current) => {
      const currentByNode = new Map(current.map((item) => [item.node_id, item]));
      return nodes.map(
        (node) =>
          currentByNode.has(node.id) ? {
            ...currentByNode.get(node.id)!,
            concrete_grade: currentByNode.get(node.id)!.concrete_grade ?? "C30",
            rebar_grade: currentByNode.get(node.id)!.rebar_grade ?? "HRB400",
            bar_diameter_mm: currentByNode.get(node.id)!.bar_diameter_mm ?? 14,
            bar_spacing_mm: currentByNode.get(node.id)!.bar_spacing_mm ?? 150,
            section_shape: currentByNode.get(node.id)!.section_shape ?? "stepped",
            reinforcement: currentByNode.get(node.id)!.reinforcement ?? {
              bottom_x_diameter_mm: 14, bottom_x_spacing_mm: 150,
              bottom_y_diameter_mm: 14, bottom_y_spacing_mm: 150,
            },
          } : {
            node_id: node.id,
            foundation_system_id:
              node.calculation_module === "strip_footing" ? "strip" : "spread",
            selection_source: "recommended" as const,
            length_m: node.calculation_module === "strip_footing" ? 1 : 2,
            width_m: node.calculation_module === "strip_footing" ? 1.2 : 2,
            thickness_mm: node.calculation_module === "strip_footing" ? 400 : 500,
            embedment_m: 1,
            concrete_grade: "C30",
            rebar_grade: "HRB400",
            bar_diameter_mm: 14,
            bar_spacing_mm: 150,
            plan_shape: "rectangular" as const,
            section_shape: node.calculation_module === "spread_footing" ? "stepped" as const : "prismatic" as const,
            steps: node.calculation_module === "spread_footing" ? [{ length_m: 1.2, width_m: 1.2, height_mm: 250 }] : [],
            pedestal: { enabled: false },
            reinforcement: {
              bottom_x_diameter_mm: 14, bottom_x_spacing_mm: 150,
              bottom_y_diameter_mm: 14, bottom_y_spacing_mm: 150,
            },
          },
      );
    });
  }, [visibleNodes]);

  useEffect(() => {
    setVerticalEnclosure(
      conditionProfile.wind_semantics === "solid_panel" ? "solid_panel" : "none",
    );
    setTopCover(conditionProfile.wind_semantics === "roof" ? "solid_roof" : "none");
    setVerticalOpenRatio("");
    setTopOpenRatio("");
  }, [conditionProfile.wind_semantics, variantId]);

  const selectedClimate = climateCatalog?.items.find((item) => item.id === climateLocationId);
  const semanticFactors = useMemo(() => {
    const height = conditionProfile.height_parameter_keys
      .map((key) => Number(parameters[key]))
      .find((value) => Number.isFinite(value) && value > 0)
      ?? Number(parameters.height_m ?? parameters.height ?? parameters.column_height_m ?? 5);
    const terrain = { A: 0.85, B: 1, C: 1.15, D: 1.3 }[terrainCategory];
    const effectiveStructureShape =
      conditionProfile.wind_semantics === "roof"
        ? "roof"
        : conditionProfile.wind_semantics === "solid_panel"
          ? "solid_panel"
          : "open_frame";
    const roofSource = isParametricPergola
      ? roofGeometry === "single_slope"
        ? "单坡"
        : roofGeometry === "double_slope"
          ? "双坡"
          : roofGeometry === "flat"
            ? "平顶"
            : "其他"
      : (conditionProfile.roof_form_parameter_key
        ? parameters[conditionProfile.roof_form_parameter_key]
        : undefined) ?? variant?.roof_form;
    const effectiveRoofForm =
      conditionProfile.snow_semantics === "exposed_horizontal"
        ? "flat"
        : toRoofForm(roofSource);
    const heightFactor = heightFactorOverride === "" ? terrain * (height <= 5 ? 0.9 : height <= 10 ? 1 : 1.1) : heightFactorOverride;
    const windShape = shapeFactorOverride === "" ? { open_frame: 0.8, solid_panel: 1.3, roof: 0.9 }[effectiveStructureShape] : shapeFactorOverride;
    const snowShape = snowFactorOverride === "" ? { flat: 0.8, single_slope: 1, double_slope: 1, other: 1.2 }[effectiveRoofForm] : snowFactorOverride;
    return {
      heightFactor: Number(heightFactor.toFixed(3)),
      windShape,
      snowShape,
      structureShape: effectiveStructureShape,
      roofForm: effectiveRoofForm,
    };
  }, [parameters, terrainCategory, conditionProfile, variant, heightFactorOverride, shapeFactorOverride, snowFactorOverride, isParametricPergola, roofGeometry]);

  const generatedGeometryProfile = useMemo<SceneGeometryProfile | null>(() => {
    if (family.id !== "pergola-pavilion") return null;
    const parsePositive = (text: string, fallback: number[]) => {
      const values = text.split(/[,，\s]+/).map(Number).filter((value) => Number.isFinite(value) && value > 0);
      return values.length ? values : fallback;
    };
    const xSpans = layoutMode === "custom_grid" ? parsePositive(xBaySpans, [4]) : [Number(parameters.span_m ?? 4)];
    const ySpans = layoutMode === "custom_grid" ? parsePositive(yBaySpans, [3, 3]) : [Number(parameters.frame_spacing_m ?? parameters.bay_spacing_m ?? 3)];
    const positions = (spans: number[]) => spans.reduce<number[]>((all, span) => [...all, all[all.length - 1] + span], [0]);
    const xs = positions(xSpans);
    const ys = positions(ySpans);
    const customHeights = parsePositive(columnHeights, [Number(parameters.height_m ?? 3)]);
    const baseHeight = customHeights[0] ?? 3;
    const angle = (roofDirectionDeg * Math.PI) / 180;
    const projections = xs.flatMap((x) => ys.map((y) => x * Math.cos(angle) + y * Math.sin(angle)));
    const minProjection = Math.min(...projections);
    const maxProjection = Math.max(...projections);
    const projectionRange = Math.max(maxProjection - minProjection, 1);
    const roofRise = Math.tan((roofSlopeDeg * Math.PI) / 180) * projectionRange;
    const omitted = new Set(omittedColumns.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean));
    const nodes: SceneGeometryProfile["nodes"] = [];
    xs.forEach((x, ix) => ys.forEach((y, iy) => {
      const customHeight = customHeights[ix * ys.length + iy] ?? customHeights[customHeights.length - 1];
      const normalizedProjection = (x * Math.cos(angle) + y * Math.sin(angle) - minProjection) / projectionRange;
      const height = roofGeometry === "single_slope"
        ? baseHeight + roofRise * normalizedProjection
        : roofGeometry === "double_slope"
          ? baseHeight + roofRise * (1 - Math.abs(2 * normalizedProjection - 1)) / 2
          : roofGeometry === "flat"
            ? baseHeight
            : customHeight;
      if (!omitted.has(`${ix + 1}-${iy + 1}`)) nodes.push({ id: `B-${ix + 1}-${iy + 1}`, x_m: x, y_m: y, z_m: 0, support: "none", column_top: false });
      nodes.push({ id: `T-${ix + 1}-${iy + 1}`, x_m: x, y_m: y, z_m: height, support: "none", column_top: true });
    }));
    const known = new Set(nodes.map((node) => node.id));
    const members: SceneGeometryProfile["members"] = [];
    nodes.filter((node) => node.column_top && known.has(`B-${node.id.slice(2)}`)).forEach((node) => members.push({ id: `C-${node.id.slice(2)}`, start_node_id: `B-${node.id.slice(2)}`, end_node_id: node.id, role: "column", group_id: "columns", behavior: "frame", end_release: "rigid" }));
    const addBeam = (a: string, b: string, id: string) => { if (known.has(a) && known.has(b)) members.push({ id, start_node_id: a, end_node_id: b, role: "beam", group_id: "roof-beams", behavior: "frame", end_release: "rigid" }); };
    xs.forEach((_x, ix) => ys.slice(0, -1).forEach((_y, iy) => addBeam(`T-${ix + 1}-${iy + 1}`, `T-${ix + 1}-${iy + 2}`, `BY-${ix + 1}-${iy + 1}`)));
    ys.forEach((_y, iy) => xs.slice(0, -1).forEach((_x, ix) => addBeam(`T-${ix + 1}-${iy + 1}`, `T-${ix + 2}-${iy + 1}`, `BX-${ix + 1}-${iy + 1}`)));
    const roofSurfaces: SceneGeometryProfile["roof_surfaces"] = [];
    xs.slice(0, -1).forEach((_x, ix) => ys.slice(0, -1).forEach((_y, iy) => {
      const nodeIds = [`T-${ix + 1}-${iy + 1}`, `T-${ix + 2}-${iy + 1}`, `T-${ix + 2}-${iy + 2}`, `T-${ix + 1}-${iy + 2}`];
      if (nodeIds.every((id) => known.has(id))) roofSurfaces.push({ id: `R-${ix + 1}-${iy + 1}`, node_ids: nodeIds, form: roofGeometry === "custom_heights" ? "faceted" : roofGeometry, load_path_group_ids: ["roof-beams"] });
    }));
    return {
      profile_version: "2.0",
      layout_mode: "free_plan",
      axes: [{ id: "X", direction: "x", positions_m: xs }, { id: "Y", direction: "y", positions_m: ys }],
      nodes,
      members,
      roof_surfaces: roofSurfaces,
      supports: nodes.filter((node) => node.id.startsWith("B-")).map((node) => ({ id: `SUP-${node.id}`, node_id: node.id, restraint: "fixed", foundation_id: `F-${node.id}` })),
      plan_boundary: {
        outer_points: [
          { id: "BP-1", x_m: xs[0], y_m: ys[0] },
          { id: "BP-2", x_m: xs[xs.length - 1], y_m: ys[0] },
          { id: "BP-3", x_m: xs[xs.length - 1], y_m: ys[ys.length - 1] },
          { id: "BP-4", x_m: xs[0], y_m: ys[ys.length - 1] },
        ],
        outer_segments: [
          { id: "BS-1", start_point_id: "BP-1", end_point_id: "BP-2", kind: "line" },
          { id: "BS-2", start_point_id: "BP-2", end_point_id: "BP-3", kind: "line" },
          { id: "BS-3", start_point_id: "BP-3", end_point_id: "BP-4", kind: "line" },
          { id: "BS-4", start_point_id: "BP-4", end_point_id: "BP-1", kind: "line" },
        ],
        source: "参数化轴网生成，可在二维编辑器修改",
      },
      roof_elevation: {
        kind: roofGeometry === "custom_heights" ? "node_elevations" : roofGeometry,
        datum_height_m: baseHeight,
        slope_deg: roofGeometry === "flat" || roofGeometry === "custom_heights" ? null : roofSlopeDeg,
        direction_deg: roofGeometry === "flat" || roofGeometry === "custom_heights" ? null : roofDirectionDeg,
        ridge_start: roofGeometry === "double_slope" ? [xs[0], (ys[0] + ys[ys.length - 1]) / 2] : null,
        ridge_end: roofGeometry === "double_slope" ? [xs[xs.length - 1], (ys[0] + ys[ys.length - 1]) / 2] : null,
        opposite_slope_deg: roofGeometry === "double_slope" ? roofSlopeDeg : null,
      },
      source: layoutMode === "custom_grid" ? "用户引导式自定义轴网" : "亭廊快捷模板生成",
    };
  }, [family.id, layoutMode, xBaySpans, yBaySpans, columnHeights, omittedColumns, parameters, roofGeometry, roofSlopeDeg, roofDirectionDeg]);

  const geometryProfile = geometryOverride ?? generatedGeometryProfile;
  const selectedModelMember = modelSelection?.kind === "member"
    ? geometryProfile?.members.find((item) => item.id === modelSelection.id) ?? null
    : null;
  const selectedMemberNodes = selectedModelMember && geometryProfile
    ? [
        geometryProfile.nodes.find((item) => item.id === selectedModelMember.start_node_id),
        geometryProfile.nodes.find((item) => item.id === selectedModelMember.end_node_id),
      ]
    : [];
  const selectedMemberLength = selectedMemberNodes[0] && selectedMemberNodes[1]
    ? Math.hypot(
        selectedMemberNodes[1].x_m - selectedMemberNodes[0].x_m,
        selectedMemberNodes[1].y_m - selectedMemberNodes[0].y_m,
        selectedMemberNodes[1].z_m - selectedMemberNodes[0].z_m,
      )
    : null;

  useEffect(() => {
    if (preserveHydratedGeometry.current) {
      preserveHydratedGeometry.current = false;
      return;
    }
    setGeometryOverride(null);
  }, [family.id, xBaySpans, yBaySpans, columnHeights, omittedColumns, roofGeometry, roofSlopeDeg, roofDirectionDeg]);

  const climateInputsReady = useMemo(() => {
    if (!(needsWind || needsSnow)) return true;
    if (climateLocationId === "manual") {
      return (!needsWind || (manualWind !== "" && Number(manualWind) > 0)) &&
        (!needsSnow || (manualSnow !== "" && Number(manualSnow) >= 0)) &&
        manualClimateSource.trim().length >= 4;
    }
    return Boolean(selectedClimate);
  }, [needsWind, needsSnow, climateLocationId, manualWind, manualSnow, manualClimateSource, selectedClimate]);

  useEffect(() => {
    if (!climateInputsReady || !(needsWind || needsSnow)) return;
    const basicWind = climateLocationId === "manual"
      ? Number(manualWind)
      : Number(selectedClimate?.wind_kpa[recurrence]);
    const basicSnow = climateLocationId === "manual"
      ? Number(manualSnow)
      : Number(selectedClimate?.snow_kpa[recurrence]);
    const windAdopted = Number((basicWind * semanticFactors.heightFactor * semanticFactors.windShape).toFixed(3));
    const snowAdopted = Number((basicSnow * semanticFactors.snowShape).toFixed(3));
    setLoadCases((current) => {
      let changed = false;
      const next = current.map((item) => {
        const adopted = item.kind === "wind" && needsWind
          ? windAdopted
          : item.kind === "snow" && needsSnow
            ? (snowExposure === "not_applicable" ? 0 : snowAdopted)
            : null;
        if (adopted === null || item.adopted_value === adopted) return item;
        changed = true;
        return {
          ...item,
          value_type: item.kind === "snow" && snowExposure === "not_applicable" ? "project_defined" as const : "calculated" as const,
          adopted_value: adopted,
          source_reference: `${climateCatalog?.version ?? "climate"} · ${recurrence}年 · 自动随项目条件更新`,
          override_reason: "统一项目条件向导自动采用",
        };
      });
      if (changed) setInputVersion((value) => value + 1);
      return changed ? next : current;
    });
    const drivenWindParameter = variant?.parameters.find((parameter) => parameter.hidden_when_condition_driven);
    if (needsWind && drivenWindParameter) {
      setParameters((current) => current[drivenWindParameter.key] === windAdopted
        ? current
        : { ...current, [drivenWindParameter.key]: windAdopted });
    }
  }, [climateInputsReady, needsWind, needsSnow, climateLocationId, manualWind, manualSnow, selectedClimate, recurrence, semanticFactors, snowExposure, climateCatalog?.version, variant]);

  useEffect(() => {
    if (conditionProfile.wind_semantics !== "roof") return;
    const assembly = roofAssemblies.find((item) => item.id === roofAssemblyId);
    if (!assembly) return;
    setLoadCases((current) => current.map((item) =>
      item.id === "roof-finish" || item.id === "canopy-finish"
        ? {
            ...item,
            adopted_value: topCover === "none" ? 0 : assembly.total_dead_load_kn_m2,
            value_type: "calculated" as const,
            source_reference: `${assembly.source_reference} · ${assembly.reference_range_kn_m2[0]}～${assembly.reference_range_kn_m2[1]} kN/m²`,
          }
        : item,
    ));
  }, [conditionProfile.wind_semantics, roofAssemblies, roofAssemblyId, topCover]);

  useEffect(() => {
    if (selectedProject === "new") return;
    const profile = projects.find((item) => item.id === selectedProject)?.site_profile;
    if (!profile) return;
    if (profile.region_preset) setClimateLocationId(profile.region_preset);
    setRecurrence(String(profile.recurrence_period_years) as "10" | "50" | "100");
    setTerrainCategory(profile.terrain_category);
    if (profile.seismic_level) setSeismicLevel(profile.seismic_level);
    setManualWind(profile.region_preset === "manual" ? profile.basic_wind_pressure_kpa ?? "" : "");
    setManualSnow(profile.region_preset === "manual" ? profile.basic_snow_pressure_kpa ?? "" : "");
    setManualClimateSource(profile.region_preset === "manual" ? profile.climate_source_reference ?? "" : "");
    setHeightFactorOverride(profile.height_factor_override ?? "");
    setShapeFactorOverride(profile.wind_shape_factor_override ?? "");
    setSnowFactorOverride(profile.snow_shape_factor_override ?? "");
    setFactorOverrideReason(profile.override_reason ?? "");
  }, [projects, selectedProject]);

  useEffect(() => {
    if (selectedProject === "new") return;
    const profile = projects.find((item) => item.id === selectedProject)?.geotechnical_profile;
    if (!profile) return;
    setDesignStage(profile.stage);
    setSoilHintId(profile.regional_hint_id ?? "");
    setSoilClass(profile.confirmed_soil_class);
    setBearingCapacity(profile.bearing_capacity_kpa);
    setBearingSource(profile.bearing_capacity_source);
    setGroundwaterCondition(
      profile.groundwater.condition === "known_levels"
        ? "known_water_table"
        : profile.groundwater.condition,
    );
    setConstructionWaterLevel(profile.groundwater.construction_level_m ?? "");
    setServiceWaterLevel(profile.groundwater.service_level_m ?? "");
    setAntifloatWaterLevel(profile.groundwater.antifloat_level_m ?? "");
    setGroundwaterSource(profile.groundwater.source);
    setGeotechnicalReportName(profile.report_name ?? "");
    setGeotechnicalReportDate(profile.report_date ?? "");
    setDeformationModulus(profile.deformation_modulus_mpa ?? "");
  }, [projects, selectedProject]);

  useEffect(() => {
    hydrated.current = false;
    const defaultVariantId =
      family.default_variant_id ?? family.variants[0]?.id ?? "";
    const storageKey = `steel-compass:scene-draft:${family.id}`;
    const saved = window.localStorage.getItem(storageKey);
    let nextVariantId = defaultVariantId;
    let savedLoads: SceneLoadCase[] | undefined;
    if (saved) {
      try {
        const draft = JSON.parse(saved) as {
          variantId?: string;
          mode?: Mode;
          material?: string;
          parameters?: Record<string, unknown>;
          loadCases?: SceneLoadCase[];
          foundationType?: string;
          bearingCapacity?: number | "";
          groundwaterCondition?: GroundwaterCondition;
          waterTableDepth?: number | "";
          groundwaterSource?: string;
          snowExposure?: SnowExposure;
          snowExemptionReason?: string;
          optionalWindEnabled?: boolean;
          // Legacy local draft compatibility.
          groundwaterKnown?: boolean;
          sceneTitle?: string;
          selectedProject?: number | "new";
          designStage?: DesignStage;
          memberSpecifications?: MemberSpecification[];
          foundationSpecifications?: FoundationDesignSpecification[];
          guidedGrid?: { layoutMode?: "preset" | "custom_grid"; xBaySpans?: string; yBaySpans?: string; columnHeights?: string; omittedColumns?: string; roofGeometry?: "flat" | "single_slope" | "double_slope" | "custom_heights"; roofSlopeDeg?: number };
        };
        if (family.variants.some((item) => item.id === draft.variantId)) {
          nextVariantId = draft.variantId!;
        }
        const nextVariant = family.variants.find(
          (item) => item.id === nextVariantId,
        );
        const nextGraph = graphFor(family, nextVariant);
        setVariantId(nextVariantId);
        setMode("quick");
        setMaterial(
          draft.material ?? nextVariant?.material_systems[0] ?? "",
        );
        setParameters(
          draft.parameters ?? initialValues(family, nextVariantId),
        );
        savedLoads = draft.loadCases
          ? currentLoadCases(draft.loadCases)
          : undefined;
        setLoadCases(
          savedLoads ?? copiedLoadCases(family, nextVariant, nextGraph),
        );
        const defaultFoundationType = foundationTypeForGraph(nextGraph);
        const storedFoundationType = draft.foundationType;
        const supportsSpread = nextGraph.nodes.some(
          (node) => node.calculation_module === "spread_footing",
        );
        const supportsStrip = nextGraph.nodes.some(
          (node) => node.calculation_module === "strip_footing",
        );
        const storedTypeIsSupported =
          (storedFoundationType === "独立基础" && supportsSpread) ||
          (storedFoundationType === "条形基础" && supportsStrip);
        setFoundationType(
          storedTypeIsSupported ? storedFoundationType! : defaultFoundationType,
        );
        setBearingCapacity(draft.bearingCapacity ?? "");
        setGroundwaterCondition(
          draft.groundwaterCondition ??
            (draft.groundwaterKnown ? "no_influence" : "unknown"),
        );
        setWaterTableDepth(draft.waterTableDepth ?? "");
        setGroundwaterSource(draft.groundwaterSource ?? "");
        setSnowExposure(draft.snowExposure ?? "exposed");
        setSnowExemptionReason(draft.snowExemptionReason ?? "");
        setOptionalWindEnabled(draft.optionalWindEnabled ?? false);
        setDesignStage(draft.designStage ?? "scheme_estimate");
        if (draft.memberSpecifications) setMemberSpecifications(draft.memberSpecifications);
        if (draft.foundationSpecifications) setFoundationSpecifications(normalizedFoundations(draft.foundationSpecifications));
        if (draft.guidedGrid) {
          setLayoutMode(draft.guidedGrid.layoutMode ?? "custom_grid");
          setXBaySpans(draft.guidedGrid.xBaySpans ?? "4");
          setYBaySpans(draft.guidedGrid.yBaySpans ?? "3,3");
          setColumnHeights(draft.guidedGrid.columnHeights ?? "3");
          setOmittedColumns(draft.guidedGrid.omittedColumns ?? "");
          setRoofGeometry(draft.guidedGrid.roofGeometry ?? "flat");
          setRoofSlopeDeg(draft.guidedGrid.roofSlopeDeg ?? 8);
        }
        setSceneTitle(draft.sceneTitle ?? family.title);
        if (typeof draft.selectedProject === "number") {
          setSelectedProject(draft.selectedProject);
        }
      } catch {
        window.localStorage.removeItem(storageKey);
      }
    }
    if (!saved || !savedLoads) {
      const nextVariant = family.variants.find(
        (item) => item.id === nextVariantId,
      );
      const nextGraph = graphFor(family, nextVariant);
      setVariantId(nextVariantId);
      setMaterial(nextVariant?.material_systems[0] ?? "");
      setParameters(initialValues(family, nextVariantId));
      setLoadCases(copiedLoadCases(family, nextVariant, nextGraph));
      setSceneTitle(family.title);
    }
    setTab("settings");
    setInstance(null);
    setRevision(null);
    setProjectInstances([]);
    setInstanceRevisions({});
    setInputVersion(0);
    setCalculatedVersion(-1);
    setChangedNodeIds([]);
    setError("");
  }, [family]);

  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      return;
    }
    window.localStorage.setItem(
      `steel-compass:scene-draft:${family.id}`,
      JSON.stringify({
        variantId,
        mode,
        material,
        parameters,
        loadCases,
        foundationType,
        bearingCapacity,
        groundwaterCondition,
        waterTableDepth,
        groundwaterSource,
        snowExposure,
        snowExemptionReason,
        optionalWindEnabled,
        sceneTitle,
        selectedProject,
        designStage,
        memberSpecifications,
        foundationSpecifications,
        guidedGrid: { layoutMode, xBaySpans, yBaySpans, columnHeights, omittedColumns, roofGeometry, roofSlopeDeg },
      }),
    );
  }, [
    bearingCapacity,
    family.id,
    foundationType,
    groundwaterCondition,
    groundwaterSource,
    loadCases,
    material,
    mode,
    parameters,
    sceneTitle,
    selectedProject,
    waterTableDepth,
    snowExposure,
    snowExemptionReason,
    optionalWindEnabled,
    designStage,
    memberSpecifications,
    foundationSpecifications,
    layoutMode,
    xBaySpans,
    yBaySpans,
    columnHeights,
    omittedColumns,
    roofGeometry,
    roofSlopeDeg,
    variantId,
  ]);

  useEffect(() => {
    if (suppressNextProjectLoad.current) {
      suppressNextProjectLoad.current = false;
      return;
    }
    if (selectedProject === "new") {
      setProjectInstances([]);
      setInstanceRevisions({});
      return;
    }
    void loadProjectWorkspace(selectedProject, instance?.project_id === selectedProject ? instance.id : undefined);
    // Loading is keyed by explicit project/family selection. Instance changes are
    // handled by the action that created or selected the instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject, family.id]);

  function hydrateFromInstance(
    selected: SceneInstance,
    revisions: SceneRevision[],
  ) {
    preserveHydratedGeometry.current = true;
    const selectedVariant = family.variants.find(
      (item) => item.id === selected.variant_id,
    );
    if (!selectedVariant) return;
    const state = selected.draft_state ?? {};
    const restoredLoads = state.load_cases as SceneLoadCase[] | undefined;
    setInstance(selected);
    setVariantId(selected.variant_id);
    setMode("quick");
    setSceneTitle(selected.title);
    setMaterial(
      (state.material_system as string | undefined) ??
        selectedVariant.material_systems[0] ??
        "",
    );
    setParameters(
      (state.geometry as Record<string, unknown> | undefined) ??
        initialValues(family, selected.variant_id),
    );
    setLoadCases(
      (restoredLoads ? currentLoadCases(restoredLoads) : undefined) ??
        copiedLoadCases(family, selectedVariant, graphFor(family, selectedVariant)),
    );
    const selectedGraph = graphFor(family, selectedVariant);
    const storedFoundationType = state.foundation_type as string | undefined;
    const storedTypeIsSupported = selectedGraph.nodes.some(
      (node) =>
        (storedFoundationType === "独立基础" &&
          node.calculation_module === "spread_footing") ||
        (storedFoundationType === "条形基础" &&
          node.calculation_module === "strip_footing"),
    );
    setFoundationType(
      storedTypeIsSupported
        ? storedFoundationType!
        : foundationTypeForGraph(selectedGraph),
    );
    setBearingCapacity(
      (state.allowable_bearing_kpa as number | "" | undefined) ?? "",
    );
    setGroundwaterCondition(
      (state.groundwater_condition as GroundwaterCondition | undefined) ??
        (state.groundwater_known ? "no_influence" : "unknown"),
    );
    setWaterTableDepth(
      (state.water_table_depth_m as number | "" | undefined) ?? "",
    );
    setGroundwaterSource(
      (state.groundwater_source as string | undefined) ?? "",
    );
    setSnowExposure(
      (state.snow_exposure as SnowExposure | undefined) ?? "exposed",
    );
    setSnowExemptionReason(
      (state.snow_exemption_reason as string | undefined) ?? "",
    );
    setOptionalWindEnabled(
      (state.optional_wind_enabled as boolean | undefined) ?? false,
    );
    setDesignStage((state.design_stage as DesignStage | undefined) ?? "scheme_estimate");
    setMemberSpecifications((state.member_specifications as MemberSpecification[] | undefined) ?? []);
    setFoundationSpecifications(normalizedFoundations((state.foundation_specifications as FoundationDesignSpecification[] | undefined) ?? []));
    const exposure = state.surface_exposure as SceneStructuralProfile["exposure"] | undefined;
    if (exposure) {
      setVerticalEnclosure(exposure.vertical_enclosure);
      setTopCover(exposure.top_cover);
      setVerticalOpenRatio(exposure.vertical_open_ratio ?? "");
      setTopOpenRatio(exposure.top_open_ratio ?? "");
    }
    const guidedGrid = state.guided_grid as { layoutMode?: "preset" | "custom_grid"; xBaySpans?: string; yBaySpans?: string; columnHeights?: string; omittedColumns?: string; roofGeometry?: "flat" | "single_slope" | "double_slope" | "custom_heights"; roofSlopeDeg?: number; roofDirectionDeg?: number } | undefined;
    if (guidedGrid) {
      setLayoutMode(guidedGrid.layoutMode ?? "custom_grid");
      setXBaySpans(guidedGrid.xBaySpans ?? "4");
      setYBaySpans(guidedGrid.yBaySpans ?? "3,3");
      setColumnHeights(guidedGrid.columnHeights ?? "3");
      setOmittedColumns(guidedGrid.omittedColumns ?? "");
      setRoofGeometry(guidedGrid.roofGeometry ?? "flat");
      setRoofSlopeDeg(guidedGrid.roofSlopeDeg ?? 8);
      setRoofDirectionDeg(guidedGrid.roofDirectionDeg ?? 0);
    }
    setGeometryOverride((state.geometry_profile as SceneGeometryProfile | undefined) ?? null);
    const structural = state.structural_profile as SceneStructuralProfile | undefined;
    setMemberGroupSections(Object.fromEntries((structural?.member_groups ?? []).map((item) => [item.group_id, item.section_catalog_id ?? item.custom_section_id ?? ""])));
    setMemberSectionOverrides(Object.fromEntries((structural?.member_overrides ?? []).map((item) => [item.member_id, item.section_id])));
    const latest = revisions[0] ?? null;
    setRevision(latest);
    setInputVersion(0);
    setCalculatedVersion(latest ? 0 : -1);
    setChangedNodeIds([]);
    setTab(state.workspace_tab === "results" && latest ? "results" : "settings");
  }

  async function loadProjectWorkspace(
    projectId: number,
    preferredInstanceId?: number,
  ) {
    const sequence = ++projectLoadSequence.current;
    try {
      const allInstances = await api<SceneInstance[]>(
        `/api/v2/projects/${projectId}/scene-instances`,
      );
      const matching = allInstances.filter((item) => item.family_id === family.id);
      const histories = await Promise.all(
        matching.map(async (item) => [
          item.id,
          await api<SceneRevision[]>(
            `/api/v2/projects/${projectId}/scene-revisions?scene_instance_id=${item.id}`,
          ),
        ] as const),
      );
      if (sequence !== projectLoadSequence.current) return;
      const historyMap = Object.fromEntries(histories) as Record<number, SceneRevision[]>;
      setProjectInstances(matching);
      setInstanceRevisions(historyMap);
      const selected =
        matching.find((item) => item.id === preferredInstanceId) ?? matching[0];
      if (selected) {
        hydrateFromInstance(selected, historyMap[selected.id] ?? []);
      } else {
        setInstance(null);
        setRevision(null);
        setCalculatedVersion(-1);
      }
    } catch (caught) {
      if (sequence === projectLoadSequence.current) setError(errorMessage(caught));
    }
  }

  function markChanged(nodeIds: string[]) {
    setInputVersion((current) => current + 1);
    setChangedNodeIds((current) => Array.from(new Set([...current, ...nodeIds])));
    setError("");
  }

  function selectVariant(nextVariantId: string) {
    const next = family.variants.find((item) => item.id === nextVariantId);
    if (!next || next.availability === "development") return;
    const nextGraph = graphFor(family, next);
    setVariantId(nextVariantId);
    setMaterial(next.material_systems[0] ?? "");
    setParameters(initialValues(family, nextVariantId));
    setLoadCases(copiedLoadCases(family, next, nextGraph));
    setFoundationType(foundationTypeForGraph(nextGraph));
    setBearingCapacity("");
    setGroundwaterCondition("unknown");
    setWaterTableDepth("");
    setGroundwaterSource("");
    setInputVersion((current) => current + 1);
    setChangedNodeIds(nextGraph.nodes.map((node) => node.id));
    setError("");
  }

  function updateLoadCase(index: number, patch: Partial<SceneLoadCase>) {
    setLoadCases((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    );
    const loadNodeIds = visibleNodes
      .filter((node) => node.role === "load" || node.role === "surface")
      .map((node) => node.id);
    markChanged(loadNodeIds.length ? loadNodeIds : visibleNodes.map((node) => node.id));
  }

  function addCustomLoad() {
    const target = visibleNodes.find((node) => node.role !== "foundation");
    setLoadCases((current) => [
      ...current,
      {
        id: `custom-${Date.now()}`,
        label: "项目资料荷载",
        kind: "dead",
        value_type: "project_defined",
        adopted_value: 0,
        unit: "kN/m2",
        source_reference: "",
        applicable_when: family.title,
        distribution: "area",
        direction: "gravity",
        application_target: target?.id ?? "scene",
        project_source: "",
        project_reference: "",
        notes: "",
      },
    ]);
    markChanged(visibleNodes.map((node) => node.id));
  }

  function currentSiteProfile(): ProjectSiteProfile | null {
    const existing = selectedProject === "new"
      ? null
      : projects.find((item) => item.id === selectedProject)?.site_profile ?? null;
    if (!hasConditions) return existing;

    const completed = new Set(existing?.completed_conditions ?? []);
    const profile: ProjectSiteProfile = {
      ...(existing ?? {}),
      profile_version: "1.1",
      recurrence_period_years: Number(recurrence) as 10 | 50 | 100,
      terrain_category: terrainCategory,
      structure_shape: semanticFactors.structureShape as NonNullable<ProjectSiteProfile["structure_shape"]>,
      roof_form: semanticFactors.roofForm as NonNullable<ProjectSiteProfile["roof_form"]>,
      catalog_versions: {
        ...(existing?.catalog_versions ?? {}),
        climate_regions: climateCatalog?.version ?? "unknown",
        seismic: seismicCatalog?.version ?? "unknown",
        standards: "CN-2026.6",
      },
    };

    if (needsWind || needsSnow) {
      const location = selectedClimate;
      if (!location) {
        setError("请选择项目地区档。 ");
        return null;
      }
      const isManual = climateLocationId === "manual";
      const wind = isManual ? Number(manualWind) : location.wind_kpa[recurrence];
      const snow = isManual ? Number(manualSnow) : location.snow_kpa[recurrence];
      if (needsWind && (!Number.isFinite(wind) || wind <= 0)) {
        setError("请填写有效的基本风压。");
        return null;
      }
      if (needsSnow && (!Number.isFinite(snow) || snow < 0)) {
        setError("请填写有效的基本雪压。");
        return null;
      }
      if (isManual && manualClimateSource.trim().length < 4) {
        setError("其他地区必须填写项目资料来源。 ");
        return null;
      }
      if (needsSnow && snowExposure === "not_applicable" && snowExemptionReason.trim().length < 4) {
        setError("不计露天积雪时，请填写项目依据。 ");
        return null;
      }
      profile.region_preset = climateLocationId;
      profile.climate_source_reference = isManual
        ? manualClimateSource.trim()
        : location.source_reference;
      if (needsWind) {
        profile.basic_wind_pressure_kpa = wind;
        completed.add("wind");
      }
      if (needsSnow) {
        profile.basic_snow_pressure_kpa = snow;
        completed.add("snow");
      }
    }
    if (needsSeismic) {
      if (!seismicLevel) {
        setError("请选择地震烈度与设计基本加速度；软件不会代填默认值。 ");
        return null;
      }
      profile.seismic_level = seismicLevel;
      completed.add("seismic");
    }
    const changedWindFactor = needsWind && (heightFactorOverride !== "" || shapeFactorOverride !== "");
    const changedSnowFactor = needsSnow && snowFactorOverride !== "";
    if ((changedWindFactor || changedSnowFactor) && !factorOverrideReason.trim()) {
      setError("修改高级系数时必须填写覆盖原因。 ");
      return null;
    }
    if (needsWind) {
      profile.height_factor_override = heightFactorOverride === "" ? null : heightFactorOverride;
      profile.wind_shape_factor_override = shapeFactorOverride === "" ? null : shapeFactorOverride;
    }
    if (needsSnow) {
      profile.snow_shape_factor_override = snowFactorOverride === "" ? null : snowFactorOverride;
    }
    if (changedWindFactor || changedSnowFactor) {
      profile.override_reason = factorOverrideReason.trim();
    }
    profile.completed_conditions = Array.from(completed);
    return profile;
  }

  function draftState() {
    return {
      workspace_tab: tab,
      material_system: material,
      geometry: parameters,
      load_package_id: variant?.load_package?.id,
      load_cases: loadCases,
      foundation_type: hasGenericFoundation ? foundationType : null,
      allowable_bearing_kpa: hasGenericFoundation ? bearingCapacity : null,
      groundwater_condition: hasGenericFoundation ? groundwaterCondition : null,
      water_table_depth_m:
        hasGenericFoundation && groundwaterCondition === "known_water_table"
          ? waterTableDepth
          : null,
      groundwater_source: hasGenericFoundation ? groundwaterSource : null,
      snow_exposure: needsSnow ? snowExposure : null,
      snow_exemption_reason:
        needsSnow && snowExposure === "not_applicable" ? snowExemptionReason : null,
      optional_wind_enabled:
        conditionProfile.wind === "optional" ? optionalWindEnabled : null,
      design_stage: designStage,
      member_specifications: memberSpecifications,
      foundation_specifications: foundationSpecifications,
      surface_exposure: needsWind
        ? { vertical_enclosure: verticalEnclosure, top_cover: topCover }
        : null,
      geometry_profile: geometryProfile,
      structural_profile: currentStructuralProfile(),
      guided_grid: { layoutMode, xBaySpans, yBaySpans, columnHeights, omittedColumns, roofGeometry, roofSlopeDeg, roofDirectionDeg },
    };
  }

  function currentGeotechnicalProfile(): ProjectGeotechnicalProfile | null {
    if (!hasGenericFoundation) {
      return selectedProject === "new"
        ? null
        : projects.find((item) => item.id === selectedProject)?.geotechnical_profile ?? null;
    }
    if (!bearingCapacity || !soilClass.trim() || !bearingSource.trim()) {
      setError("请确认土质类别、地基承载力和资料来源；软件不再代填 120 kPa。");
      return null;
    }
    if (!groundwaterSource.trim() || groundwaterCondition === "unknown") {
      setError("请明确地下水边界及资料来源；未知水位不能作为基础计算输入。");
      return null;
    }
    if (
      groundwaterCondition === "known_water_table" &&
      [constructionWaterLevel, serviceWaterLevel, antifloatWaterLevel].some(
        (value) => value === "",
      )
    ) {
      setError("已知地下水时必须填写施工期、正常使用和抗浮设计水位标高。");
      return null;
    }
    if (
      designStage === "project_check" &&
      (!geotechnicalReportName.trim() || !geotechnicalReportDate || !deformationModulus)
    ) {
      setError("工程校核需要勘察报告名称、日期及沉降计算参数；资料不足时请选择方案测算。");
      return null;
    }
    return {
      profile_version: "1.0",
      stage: designStage,
      regional_hint_id: designStage === "scheme_estimate" ? soilHintId : null,
      confirmed_soil_class: soilClass.trim(),
      bearing_capacity_kpa: Number(bearingCapacity),
      bearing_capacity_source: bearingSource.trim(),
      deformation_modulus_mpa:
        deformationModulus === "" ? null : Number(deformationModulus),
      groundwater: {
        condition:
          groundwaterCondition === "known_water_table"
            ? "known_levels"
            : groundwaterCondition,
        construction_level_m:
          constructionWaterLevel === "" ? null : Number(constructionWaterLevel),
        service_level_m:
          serviceWaterLevel === "" ? null : Number(serviceWaterLevel),
        antifloat_level_m:
          antifloatWaterLevel === "" ? null : Number(antifloatWaterLevel),
        source: groundwaterSource.trim(),
      },
      report_name: geotechnicalReportName.trim() || null,
      report_date: geotechnicalReportDate || null,
      catalog_versions: { geotechnical_hints: "zhejiang-geotech-2026.1-unverified" },
    };
  }

  function currentStructuralProfile(): SceneStructuralProfile | null {
    const steelNodeIds = new Set(
      visibleNodes
        .filter((node) => ["steel_beam", "steel_column", "portal_frame"].includes(node.calculation_module ?? ""))
        .map((node) => node.id),
    );
    const foundationNodeIds = new Set(
      visibleNodes
        .filter((node) => node.role === "foundation" && ["spread_footing", "strip_footing"].includes(node.calculation_module ?? ""))
        .map((node) => node.id),
    );
    const members = memberSpecifications.filter((item) => steelNodeIds.has(item.node_id));
    const foundations = foundationSpecifications
      .filter((item) => foundationNodeIds.has(item.node_id))
      .map((item) => ({
        ...item,
        concrete_grade: item.concrete_grade ?? "C30",
        rebar_grade: item.rebar_grade ?? "HRB400",
        bar_diameter_mm: item.bar_diameter_mm ?? 14,
        bar_spacing_mm: item.bar_spacing_mm ?? 150,
        section_shape: item.section_shape ?? "stepped" as const,
        steps: item.section_shape === "tapered" || item.section_shape === "prismatic"
          ? (item.steps ?? [])
          : (item.steps?.length ? item.steps : [{ length_m: Math.max(0.5, item.length_m - 0.6), width_m: Math.max(0.5, item.width_m - 0.6), height_mm: 250 }]),
        reinforcement: item.reinforcement ?? {
          bottom_x_diameter_mm: item.bar_diameter_mm ?? 14,
          bottom_x_spacing_mm: item.bar_spacing_mm ?? 150,
          bottom_y_diameter_mm: item.bar_diameter_mm ?? 14,
          bottom_y_spacing_mm: item.bar_spacing_mm ?? 150,
        },
      }));
    if ((steelNodeIds.size && !members.length) || (foundationNodeIds.size && !foundations.length)) {
      setError("请先明确所有钢构件截面和基础尺寸。");
      return null;
    }
    return {
      profile_version: "3.0",
      stage: designStage,
      exposure: needsWind
        ? {
            vertical_enclosure: verticalEnclosure,
            top_cover: topCover,
            vertical_open_ratio:
              verticalOpenRatio === "" ? null : Number(verticalOpenRatio),
            top_open_ratio: topOpenRatio === "" ? null : Number(topOpenRatio),
            roof_form:
              topCover === "solid_roof"
                ? (semanticFactors.roofForm as "flat" | "single_slope" | "double_slope" | "other")
                : null,
            source: "场景几何与用户确认的围护/顶部覆盖",
          }
        : null,
      members,
      member_groups: Array.from(new Set((geometryProfile?.members ?? []).map((item) => item.group_id))).map((groupId) => {
        const representative = geometryProfile?.members.find((item) => item.group_id === groupId);
        const legacy = members.find((item) => item.member_role === (representative?.role === "column" ? "column" : "beam"));
        const sectionId = memberGroupSections[groupId] || legacy?.section_catalog_id || availableSections[0]?.id || null;
        return {
          group_id: groupId,
          role: representative?.role ?? "beam",
          material_grade: legacy?.material_grade ?? "Q355B",
          section_catalog_id: customSections.some((item) => item.id === sectionId) ? null : sectionId,
          custom_section_id: customSections.some((item) => item.id === sectionId) ? sectionId : null,
          strong_axis_unbraced_length_m: legacy?.unbraced_length_m ?? 3,
          weak_axis_unbraced_length_m: legacy?.unbraced_length_m ?? 3,
          effective_length_factor_y: 1,
          effective_length_factor_z: 1,
        };
      }),
      member_overrides: Object.entries(memberSectionOverrides).map(([memberId, sectionId]) => ({
        member_id: memberId,
        material_grade: "Q355B",
        section_id: sectionId,
        orientation: "strong_axis" as const,
        source: "用户仅应用到选中构件",
      })),
      foundations,
      geometry: geometryProfile,
      roof_assembly: conditionProfile.wind_semantics === "roof"
        ? roofAssemblies.find((item) => item.id === (topCover === "none" ? "none" : roofAssemblyId)) ?? null
        : null,
      catalog_versions: {
        steel_sections: "steel-sections-2026.2-unverified",
        foundation_systems: "foundation-systems-2026.2-unverified",
        roof_assemblies: "roof-assemblies-2026.1-unverified",
      },
    };
  }

  async function createCustomSection() {
    setWorking(true);
    setError("");
    try {
      const id = `custom-${Date.now().toString(36)}`;
      const created = await api<CustomSectionDefinition>("/api/v2/catalogs/custom-section-properties", {
        method: "POST",
        body: JSON.stringify({
          id,
          name: customSectionName.trim(),
          family: customSectionFamily,
          dimensions: customSectionDimensions,
          corner_radius_mm: customCornerRadius === "" ? null : customCornerRadius,
          source_reference: "用户按厂家资料或实测尺寸输入；截面性质由软件根据几何计算",
        }),
      });
      setCustomSections((current) => [...current.filter((item) => item.id !== created.id), created]);
      setCustomSectionOpen(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  async function persistCustomSections(projectId: number) {
    if (!customSections.length) return;
    await api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${projectId}/custom-sections`, {
      method: "PUT",
      body: JSON.stringify({ items: customSections }),
    });
  }

  async function ensureProject(): Promise<number> {
    const profile = currentSiteProfile();
    const geotechnicalProfile = currentGeotechnicalProfile();
    if (hasConditions && !profile) throw new Error("项目条件尚未完成");
    if (hasGenericFoundation && !geotechnicalProfile) throw new Error("项目地勘条件尚未完成");
    if (selectedProject !== "new") {
      if (profile) {
        const savedProfile = await api<ProjectSiteProfile>(`/api/v2/projects/${selectedProject}/site-profile`, {
          method: "PUT",
          body: JSON.stringify(profile),
        });
        onProjectsChange(
          projects.map((item) =>
            item.id === selectedProject
              ? { ...item, site_profile: savedProfile }
              : item,
          ),
        );
      }
      if (geotechnicalProfile) {
        const savedGeotechnical = await api<ProjectGeotechnicalProfile>(`/api/v2/projects/${selectedProject}/geotechnical-profile`, {
          method: "PUT",
          body: JSON.stringify(geotechnicalProfile),
        });
        onProjectsChange(
          projects.map((item) =>
            item.id === selectedProject
              ? { ...item, geotechnical_profile: savedGeotechnical }
              : item,
          ),
        );
      }
      await persistCustomSections(selectedProject);
      return selectedProject;
    }
    const created = await api<Project>("/api/v2/projects", {
      method: "POST",
      body: JSON.stringify({ name: sceneTitle, description: family.description, ...(profile ? { site_profile: profile } : {}), ...(geotechnicalProfile ? { geotechnical_profile: geotechnicalProfile } : {}) }),
    });
    suppressNextProjectLoad.current = true;
    setSelectedProject(created.id);
    onProjectsChange([created, ...projects]);
    await persistCustomSections(created.id);
    return created.id;
  }

  async function saveDraft(): Promise<SceneInstance> {
    const projectId = await ensureProject();
    if (instance && instance.project_id === projectId) {
      const updated = await api<SceneInstance>(
        `/api/v2/projects/${projectId}/scene-instances/${instance.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            variant_id: variantId,
            title: sceneTitle,
            mode: "quick",
            draft_state: draftState(),
            changed_node_ids: changedNodeIds,
          }),
        },
      );
      setInstance(updated);
      setProjectInstances((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      return updated;
    }
    const created = await api<SceneInstance>(
      `/api/v2/projects/${projectId}/scene-instances`,
      {
        method: "POST",
        body: JSON.stringify({
          family_id: family.id,
          variant_id: variantId,
          title: sceneTitle,
          mode: "quick",
          draft_state: draftState(),
        }),
      },
    );
    setInstance(created);
    setProjectInstances((current) => [created, ...current]);
    return created;
  }

  function calculationLoads(nodeId: string) {
    const calculationModule = visibleNodes.find(
      (node) => node.id === nodeId,
    )?.calculation_module as Module | undefined;
    const acceptedUnits = new Set<string>(
      calculationModule &&
      [
        "steel_beam",
        "portal_frame",
        "concrete_beam",
        "concrete_slab",
        "timber_beam",
        "timber_deck_panel",
        "masonry_wall",
        "rc_wall",
        "steel_cantilever_post",
      ].includes(calculationModule)
        ? ["kN/m", "kN/m2"]
        : ["kN"],
    );
    const roofLoadsDisabled = conditionProfile.wind_semantics === "roof" && topCover === "none";
    const targeted = loadCases.filter(
      (item) =>
        !(roofLoadsDisabled && ["roof-finish", "roof-maintenance", "roof-snow"].includes(item.id)) &&
        (item.application_target === nodeId ||
          item.application_target === "scene" ||
          item.application_target === "all"),
    );
    const incomingReaction = graph.connections.find(
      (connection) =>
        connection.target_node_id === nodeId &&
        (connection.transfer === "reaction" ||
          connection.transfer === "reaction_envelope" ||
          connection.transfer === "combination_package" ||
          connection.transfer === "reaction_package" ||
          connection.transfer === "reaction_to_line"),
    );
    if (!targeted.length && incomingReaction) {
      return [];
    }
    if (!targeted.length) return [];
    return targeted.map<LoadItem>((item) => {
      let value = item.adopted_value;
      let unit = item.unit as LoadItem["unit"];
      let direction = item.direction;
      if (!acceptedUnits.has(item.unit)) {
        unit = calculationModule === "strip_footing" ? "kN/m" : "kN";
        if (
          calculationModule === "steel_column" &&
          item.kind === "dead" &&
          item.unit === "kN/m2"
        ) {
          value =
            item.adopted_value *
            Number(parameters.panel_width_m ?? 1) *
            Number(parameters.panel_height_m ?? 1);
          direction = "gravity";
        } else {
          throw new Error(
            `荷载“${item.label}”的单位 ${item.unit} 与节点 ${nodeId} 不兼容，请调整作用节点或分布形式。`,
          );
        }
      }
      return {
        // Structural calculation requests use the narrower LoadItem enum;
        // scene-only provenance kinds (soil/water/custom) target manual nodes.
        kind: item.kind as LoadItem["kind"],
        value,
        unit,
        source: item.project_source || item.label,
        direction,
        preset_id: item.id,
        source_reference: `scene-load:${item.id}`,
        override_reason: item.override_reason,
      };
    });
  }

  function nodeCalculationPayload(nodeId: string, calculationModule: Module) {
    const definition = MODULE_MAP[calculationModule];
    const node = visibleNodes.find((item) => item.id === nodeId);
    const boundInputs = Object.fromEntries(
      Object.entries(node?.input_bindings ?? {}).flatMap(
        ([targetInput, sceneParameter]) =>
          parameters[sceneParameter] === undefined
            ? []
            : [[targetInput, parameters[sceneParameter]]],
      ),
    );
    const geometryDrivenInputs = isParametricPergola && geometryProfile
      ? {
          span_m: Math.max(
            ...geometryProfile.axes
              .filter((axis) => axis.direction === "x")
              .flatMap((axis) => axis.positions_m.slice(1).map((value, index) => value - axis.positions_m[index])),
            0.1,
          ),
          frame_spacing_m: Math.max(
            ...geometryProfile.axes
              .filter((axis) => axis.direction === "y")
              .flatMap((axis) => axis.positions_m.slice(1).map((value, index) => value - axis.positions_m[index])),
            0.1,
          ),
          height_m: Math.max(...geometryProfile.nodes.map((item) => item.z_m), 0.1),
          column_height_m: Math.max(...geometryProfile.nodes.map((item) => item.z_m), 0.1),
          roof_slope_deg: roofGeometry === "flat" || roofGeometry === "custom_heights" ? 0 : roofSlopeDeg,
        }
      : {};
    const nextInputs: Record<string, unknown> = {
      ...definition.defaults,
      ...Object.fromEntries(
        Object.entries(parameters).filter(([key]) => key in definition.defaults),
      ),
      ...boundInputs,
      ...geometryDrivenInputs,
    };
    const hiddenCriticalInputs: Record<string, string[]> = {
      steel_beam: ["steel_grade", "section_type", "h_mm", "b_mm", "t_mm", "diameter_mm", "tw_mm", "tf_mm", "effective_length_m", "unbraced_length_m"],
      steel_column: ["steel_grade", "section_type", "h_mm", "b_mm", "t_mm", "diameter_mm", "tw_mm", "tf_mm", "effective_length_m", "unbraced_length_m"],
      portal_frame: ["steel_grade", "beam_h_mm", "beam_b_mm", "beam_t_mm", "column_b_mm", "column_t_mm", "beam_section", "column_section"],
      spread_footing: ["length_m", "width_m", "thickness_mm", "embedment_m", "soil_capacity_kpa", "groundwater_depth_m", "water_table_depth_m"],
      strip_footing: ["length_m", "width_m", "thickness_mm", "embedment_m", "soil_capacity_kpa", "groundwater_depth_m", "water_table_depth_m"],
    };
    hiddenCriticalInputs[calculationModule]?.forEach((key) => delete nextInputs[key]);
    const memberSpecs = memberSpecifications.filter((item) => item.node_id === nodeId);
    if (calculationModule === "steel_beam" || calculationModule === "steel_column") {
      const specification = memberSpecs[0];
      const section = availableSections.find((item) => item.id === specification?.section_catalog_id);
      if (specification && section) {
        Object.assign(nextInputs, section.dimensions, {
          steel_grade: specification.material_grade,
          section_type: section.family,
          effective_length_m: specification.effective_length_m,
          unbraced_length_m: specification.unbraced_length_m,
        });
      }
    }
    if (calculationModule === "portal_frame") {
      const beam = memberSpecs.find((item) => item.member_role === "beam");
      const column = memberSpecs.find((item) => item.member_role === "column");
      const beamSection = availableSections.find((item) => item.id === beam?.section_catalog_id);
      const columnSection = availableSections.find((item) => item.id === column?.section_catalog_id);
      if (beam && column && beamSection && columnSection) {
        Object.assign(nextInputs, {
          steel_grade: beam.material_grade,
          beam_section: beamSection.family,
          column_section: columnSection.family,
          beam_h_mm: beamSection.dimensions.h_mm ?? beamSection.dimensions.b_mm,
          beam_b_mm: beamSection.dimensions.b_mm,
          beam_t_mm: beamSection.dimensions.t_mm ?? beamSection.dimensions.tw_mm,
          column_b_mm: columnSection.dimensions.b_mm,
          column_t_mm: columnSection.dimensions.t_mm ?? columnSection.dimensions.tw_mm,
        });
      }
    }
    if (calculationModule === "spread_footing" || calculationModule === "strip_footing") {
      const foundation = foundationSpecifications.find((item) => item.node_id === nodeId);
      if (foundation) {
        Object.assign(nextInputs, {
          length_m: foundation.length_m,
          width_m: foundation.width_m,
          thickness_mm: foundation.thickness_mm,
          embedment_m: foundation.embedment_m,
          soil_capacity_kpa: Number(bearingCapacity),
          bar_dia_x_mm: foundation.reinforcement?.bottom_x_diameter_mm ?? foundation.bar_diameter_mm ?? 14,
          bar_spacing_x_mm: foundation.reinforcement?.bottom_x_spacing_mm ?? foundation.bar_spacing_mm ?? 150,
          bar_dia_y_mm: foundation.reinforcement?.bottom_y_diameter_mm ?? foundation.bar_diameter_mm ?? 14,
          bar_spacing_y_mm: foundation.reinforcement?.bottom_y_spacing_mm ?? foundation.bar_spacing_mm ?? 150,
        });
      }
    }
    if (
      conditionProfile.geotechnical_mode === "variant_owned" &&
      calculationModule === "pile_group_cap" &&
      parameters.allowable_bearing_kpa !== undefined
    ) {
      // Pool/bridge variants own their geotechnical inputs.  Do not add the
      // generic foundation panel, while preserving the existing parameter for
      // older graph bindings and revision replays.
      nextInputs.capacity_source = "场景地基/桩基资料";
    }
    const targetLoads = loadCases.filter(
      (item) => item.application_target === nodeId,
    );
    if (calculationModule === "steel_column") {
      const panelArea =
        Number(parameters.panel_width_m ?? 1) *
        Number(parameters.panel_height_m ?? 1);
      const leverArm = Number(parameters.post_height_m ?? 1);
      const windMoment = Math.max(
        0,
        ...targetLoads
          .filter((item) => item.kind === "wind")
          .map((item) => item.adopted_value * panelArea * leverArm),
      );
      const eccentricMoment = targetLoads
        .filter((item) => item.unit === "kN.m" || item.unit === "kN·m")
        .reduce((sum, item) => sum + item.adopted_value, 0);
      nextInputs.design_moment_kn_m = windMoment + eccentricMoment;
    }
    if (calculationModule === "strip_footing") {
      const wallHeight = Number(parameters.height_m ?? 1);
      const windPressure = Math.max(
        0,
        ...targetLoads
          .filter((item) => item.kind === "wind" && item.unit === "kN/m2")
          .map((item) => item.adopted_value),
      );
      nextInputs.horizontal_load_kn_m = windPressure * wallHeight;
      nextInputs.moment_kn_m_per_m = windPressure * wallHeight ** 2 / 2;
    }
    const inputUnits = Object.fromEntries(
      definition.fields.map((field) => [field.key, field.unit ?? "1"]),
    );
    const typedValues: Record<string, unknown> = {};
    Object.entries(nextInputs).forEach(([key, value]) => {
      if (typeof value === "number" && Number.isFinite(value)) {
        typedValues[key] = { value, unit: inputUnits[key] ?? "1" };
      } else if (typeof value === "string" || typeof value === "boolean") {
        typedValues[key] = value;
      }
    });
    return {
      node_id: nodeId,
      calculation: {
        schema_version: "3.3",
        mode,
        module: calculationModule,
        project_name: `${sceneTitle} · ${nodeId}`,
        standard_profile: "CN-2026.6",
        typed_inputs: {
          module: calculationModule,
          values: typedValues,
        },
        inputs: normalizeInputs(calculationModule, nextInputs),
        loads: calculationLoads(nodeId),
      },
    };
  }

  function validateSettings() {
    if (geometryProfile && (geometryProfile.nodes.length > 200 || geometryProfile.members.length > 400)) {
      return "当前三维轴网超过 200 个节点或 400 根杆件，请拆分为多个场景。";
    }
    if (!loadCases.length) return "当前场景没有可用荷载包。";
    const invalidCustom = loadCases.find(
      (item) =>
        item.value_type === "project_defined" &&
        (!Number.isFinite(item.adopted_value) ||
          !item.project_source?.trim() ||
          !item.source_reference.trim()),
    );
    if (invalidCustom) {
      return `“${invalidCustom.label}”需要填写数值、资料名称和来源页码/条款。`;
    }
    const missingCalculatedValue = loadCases.find(
      (item) => item.value_type === "calculated" && item.adopted_value <= 0,
    );
    if (missingCalculatedValue) {
      return `“${missingCalculatedValue.label}”需要通过风雪向导或项目资料填写最终采用值。`;
    }
    const missingOverride = loadCases.find(
      (item) =>
        item.value_type !== "project_defined" &&
        item.recommended_default !== undefined &&
        item.adopted_value !== item.recommended_default &&
        !item.override_reason?.trim(),
    );
    if (missingOverride) {
      return `“${missingOverride.label}”覆盖了建议值，请填写调整原因。`;
    }
    if (hasGenericFoundation && mode === "professional") {
      if (!bearingCapacity) {
        return "专业模式需要填写勘察承载力。";
      }
    }
    return "";
  }

  async function evaluateScene() {
    const validationError = validateSettings();
    if (validationError) {
      setError(validationError);
      setTab("settings");
      return;
    }
    setWorking(true);
    setError("");
    try {
      const structuralProfile = currentStructuralProfile();
      if (!structuralProfile) throw new Error("构件与基础选型尚未完成");
      const saved = await saveDraft();
      const nodeCalculations = visibleNodes.flatMap((node) => {
        const calculationModule = node.calculation_module as Module | undefined;
        return calculationModule && calculationModule in MODULE_MAP
          ? [nodeCalculationPayload(node.id, calculationModule)]
          : [];
      });
      const calculated = await api<SceneRevision>(
        `/api/v2/projects/${saved.project_id}/scene-revisions`,
        {
          method: "POST",
          body: JSON.stringify({
            scene_instance_id: saved.id,
            node_calculations: nodeCalculations,
            load_cases: loadCases,
            structural_profile: structuralProfile,
          }),
        },
      );
      setRevision(calculated);
      setInstanceRevisions((current) => ({
        ...current,
        [saved.id]: [calculated, ...(current[saved.id] ?? [])],
      }));
      setCalculatedVersion(inputVersion);
      setChangedNodeIds([]);
      setTab("results");
      const refreshed = await api<Project[]>("/api/v2/projects");
      onProjectsChange(refreshed);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  async function saveOnly() {
    setWorking(true);
    setError("");
    try {
      await saveDraft();
      const refreshed = await api<Project[]>("/api/v2/projects");
      onProjectsChange(refreshed);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  async function duplicateAlternative() {
    if (!instance || !revision || stale || selectedProject === "new") return;
    setWorking(true);
    setError("");
    try {
      const copied = await api<SceneInstance>(
        `/api/v2/projects/${selectedProject}/scene-instances/${instance.id}/duplicate`,
        { method: "POST" },
      );
      await loadProjectWorkspace(selectedProject, copied.id);
      setTab("results");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  async function renameInstance(target: SceneInstance) {
    const title = window.prompt("方案名称", target.title)?.trim();
    if (!title || title === target.title) return;
    try {
      const updated = await api<SceneInstance>(
        `/api/v2/projects/${target.project_id}/scene-instances/${target.id}`,
        { method: "PATCH", body: JSON.stringify({ title }) },
      );
      setProjectInstances((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      if (instance?.id === updated.id) {
        setInstance(updated);
        setSceneTitle(updated.title);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function archiveInstance(target: SceneInstance) {
    if (selectedProject === "new") return;
    try {
      await api<SceneInstance>(
        `/api/v2/projects/${target.project_id}/scene-instances/${target.id}`,
        { method: "PATCH", body: JSON.stringify({ archived: true }) },
      );
      await loadProjectWorkspace(
        selectedProject,
        target.id === instance?.id ? undefined : instance?.id,
      );
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  function resultTitle() {
    if (!revision) return "尚未计算";
    if (stale) return "输入已修改，结果已过期";
    const status =
      revision.scene_result.engineering_status ?? revision.scene_result.status;
    if (["quick_estimate", "scheme_estimate"].includes(revision.scene_result.result_class ?? "")) {
      return revision.scene_result.quick_outcome === "screening_failed"
        ? "方案筛查需调整"
        : "方案筛查已完成";
    }
    if (status === "passed") return "当前输入和适用范围内通过";
    if (status === "failed") return "存在不满足项";
    return "专业检查待补齐";
  }

  function renderLoadPath(compact = false) {
    return (
      <div className={compact ? "load-path compact" : "load-path"}>
        {visibleNodes.map((node, index) => {
          const result = revision?.scene_result.node_results[node.id];
          return (
            <div className="load-path-item" key={node.id}>
              <span className={`path-dot ${result?.status ?? node.maturity}`}>
                {result?.status === "passed" || result?.status === "completed" ? (
                  <Check size={13} />
                ) : (
                  <CircleDot size={13} />
                )}
              </span>
              <div>
                <strong>{node.label}</strong>
                <span>
                  {result
                    ? STATUS_LABELS[result.status]
                    : node.quick_assumption
                      ? "快算假定待确认"
                      : "待计算"}
                  {stale || result?.stale ? " · 已过期" : ""}
                </span>
                {node.quick_assumption && !result && <small>{node.quick_assumption}</small>}
                {result?.message && <small>{result.message}</small>}
              </div>
              {index < visibleNodes.length - 1 && <span className="path-line" />}
            </div>
          );
        })}
      </div>
    );
  }

  if (family.availability === "development") {
    return (
      <div className="scene-workspace">
        <section className="development-scene-card">
          <span className="maturity-badge planned">开发中</span>
          <h1>{family.title}</h1>
          <p>该场景尚未形成可复核的完整传力链，当前不开放计算。</p>
        </section>
      </div>
    );
  }

  return (
    <div className="scene-workspace">
      <section className="scene-hero compact-hero">
        <div>
          <span className="eyebrow">COMPLETE LANDSCAPE SCENE</span>
          <h1>{family.title}</h1>
          <p>{family.description}</p>
        </div>
      </section>

      <nav className="scene-tabs" aria-label="场景工作台">
        <button
          className={tab === "settings" ? "active" : ""}
          onClick={() => setTab("settings")}
        >
          <span>1</span> 设置
        </button>
        <button
          className={tab === "results" ? "active" : ""}
          onClick={() => setTab("results")}
        >
          <span>2</span> 结果与对比
          {stale && <em>已过期</em>}
        </button>
      </nav>

      {stale && (
        <div className="stale-banner" role="status">
          <RotateCcw size={17} />
          <div>
            <strong>输入已修改，旧结果不再代表当前方案</strong>
            <span>旧修订仍保留；重新计算会生成新版本。</span>
          </div>
          <button onClick={evaluateScene}>重新计算</button>
        </div>
      )}

      <div className={`scene-layout workbench-layout ${tab === "settings" && isParametricPergola ? "free-model-layout" : ""}`}>
        <section className="scene-workbench">
          {tab === "settings" ? (
            <div className="settings-stack">
              <details className="settings-section" open>
                <summary>
                  <span><strong>方案与结构体系</strong><small>变体、材料和方案名称</small></span>
                  <ChevronDown size={17} />
                </summary>
                <div className="settings-section-body">
                  {isParametricPergola ? (
                    <div className="parametric-scene-intro">
                      <strong>参数化亭廊模型</strong>
                      <span>不再区分“平顶单跨、单坡、双坡、多跨”。轴网、柱高和屋面分区共同决定实际形态。</span>
                    </div>
                  ) : <div className="variant-grid compact-grid">
                    {family.variants.map((item) => {
                      const disabled = item.availability === "development";
                      return (
                        <button
                          key={item.id}
                          disabled={disabled}
                          className={variantId === item.id ? "active" : ""}
                          onClick={() => selectVariant(item.id)}
                        >
                          <strong>{item.title}</strong>
                          <span>{item.description}</span>
                          <small>{disabled ? "开发中" : item.material_systems.join(" / ")}</small>
                        </button>
                      );
                    })}
                  </div>}
                  {variant && (
                    <div className="parameter-grid compact-parameters">
                      <label>
                        <span>材料体系</span>
                        <select
                          value={material}
                          onChange={(event) => {
                            setMaterial(event.target.value);
                            markChanged(visibleNodes.map((node) => node.id));
                          }}
                        >
                          {variant.material_systems.map((item) => (
                            <option key={item}>{item}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>方案名称</span>
                        <input
                          value={sceneTitle}
                          onChange={(event) => setSceneTitle(event.target.value)}
                        />
                      </label>
                    </div>
                  )}
                </div>
              </details>

              {(memberSpecifications.length > 0 || foundationSpecifications.length > 0) && (
                <details className="settings-section" open>
                  <summary><span><strong>构件与基础选型</strong><small>所有关键规格均显式保存</small></span><ChevronDown size={17} /></summary>
                  <div className="settings-section-body">
                    {memberSpecifications.length > 0 && (
                      <div className="custom-section-toolbar">
                        <div><strong>截面目录</strong><span>标准规格与项目自定义截面统一用于自重、刚度和验算。</span></div>
                        <button type="button" onClick={() => setCustomSectionOpen((value) => !value)}><Plus size={16} /> 新建自定义截面</button>
                      </div>
                    )}
                    {customSectionOpen && (
                      <div className="custom-section-editor">
                        <div className="parameter-grid compact-parameters">
                          <label><span>截面名称</span><input value={customSectionName} onChange={(event) => setCustomSectionName(event.target.value)} /></label>
                          <label><span>截面类型</span><select value={customSectionFamily} onChange={(event) => { const next = event.target.value as "SHS" | "RHS" | "CHS" | "H" | "I"; setCustomSectionFamily(next); setCustomSectionDimensions(defaultCustomSectionDimensions(next)); }}><option value="SHS">方管 SHS</option><option value="RHS">矩形管 RHS</option><option value="CHS">圆管 CHS</option><option value="H">H型钢</option><option value="I">工字钢</option></select></label>
                          {Object.entries(customSectionDimensions).map(([key, value]) => <label key={key}><span>{CUSTOM_SECTION_DIMENSION_LABELS[key] ?? key}</span><div className="input-with-unit"><input type="number" min="1" step="1" value={value} onChange={(event) => setCustomSectionDimensions((current) => ({ ...current, [key]: Number(event.target.value) }))} /><span>mm</span></div></label>)}
                          {(customSectionFamily === "SHS" || customSectionFamily === "RHS") && <label><span>外圆角半径（可选）</span><div className="input-with-unit"><input type="number" min="0" step="0.5" value={customCornerRadius} placeholder="方案测算可留空" onChange={(event) => setCustomCornerRadius(event.target.value === "" ? "" : Number(event.target.value))} /><span>mm</span></div><small>留空按锐角理论截面；工程校核应采用产品或厂家截面性质。</small></label>}
                        </div>
                        {customSectionPreview ? <div className="custom-section-preview"><strong>实时计算结果</strong><span>A = {customSectionPreview.area_mm2.toFixed(2)} mm²</span><span>理论质量 = {customSectionPreview.theoretical_mass_kg_m?.toFixed(3)} kg/m</span><span>理论线重 = {customSectionPreview.self_weight_kn_m.toFixed(5)} kN/m</span><span>Iy / Iz = {customSectionPreview.iy_mm4.toExponential(3)} / {customSectionPreview.iz_mm4.toExponential(3)} mm⁴</span>{customSectionPreview.property_trace?.map((line) => <small key={line}>{line}</small>)}</div> : <div className="inline-error">尺寸组合无效，请检查外形尺寸与厚度。</div>}
                        <div className="custom-section-actions"><span>面积、惯性矩、扭转常数和自重由后端按几何计算，不能手工伪造。</span><button type="button" disabled={working || !customSectionName.trim()} onClick={createCustomSection}>计算并加入项目截面库</button></div>
                      </div>
                    )}
                    {memberSpecifications.map((specification, index) => (
                      <div className="scene-climate-guide" key={`${specification.node_id}-${specification.member_role}`}>
                        <div><strong>{visibleNodes.find((node) => node.id === specification.node_id)?.label} · {specification.member_role === "beam" ? "梁" : "柱"}</strong><span>目录推荐仅作为起始候选，利用率与控制项以计算结果为准。</span></div>
                        <div className="parameter-grid compact-parameters">
                          <label><span>钢材牌号</span><select value={specification.material_grade} onChange={(event) => setMemberSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, material_grade: event.target.value, selection_source: "user_locked", override_reason: "用户调整钢材牌号" } : item))}><option>Q235B</option><option>Q355B</option></select></label>
                          <label><span>截面规格</span><select value={specification.section_catalog_id} onChange={(event) => { if (event.target.value === "__custom__") { setCustomSectionOpen(true); return; } const selected = availableSections.find((item) => item.id === event.target.value); if (!selected) return; setMemberSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, section_catalog_id: selected.id, section_type: selected.family as MemberSpecification["section_type"], section_name: selected.designation, selection_source: "user_locked", override_reason: "用户锁定截面规格" } : item)); }}><option value="">请选择</option>{availableSections.map((item) => <option key={item.id} value={item.id}>{item.designation} · {item.self_weight_kn_m} kN/m</option>)}<option value="__custom__">＋ 输入自定义尺寸与厚度</option></select><small>目录截面和自定义几何都会参与自重、刚度、位移及基础反力计算。</small></label>
                          <label><span>计算长度</span><div className="input-with-unit"><input type="number" min="0.1" step="0.1" value={specification.effective_length_m} onChange={(event) => setMemberSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, effective_length_m: Number(event.target.value) } : item))} /><span>m</span></div></label>
                          <label><span>无侧向支撑长度</span><div className="input-with-unit"><input type="number" min="0.1" step="0.1" value={specification.unbraced_length_m} onChange={(event) => setMemberSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, unbraced_length_m: Number(event.target.value) } : item))} /><span>m</span></div></label>
                        </div>
                        {customSections.find((item) => item.id === specification.section_catalog_id) && (() => { const section = customSections.find((item) => item.id === specification.section_catalog_id)!; return <details className="section-property-trace"><summary>查看截面计算依据</summary><dl><div><dt>面积 A</dt><dd>{section.area_mm2.toFixed(2)} mm²</dd></div><div><dt>理论质量</dt><dd>{section.theoretical_mass_kg_m?.toFixed(3) ?? "—"} kg/m</dd></div><div><dt>理论线重</dt><dd>{section.self_weight_kn_m.toFixed(5)} kN/m</dd></div><div><dt>Iy / Iz</dt><dd>{section.iy_mm4.toExponential(3)} / {section.iz_mm4.toExponential(3)} mm⁴</dd></div><div><dt>J</dt><dd>{section.torsion_mm4.toExponential(3)} mm⁴</dd></div><div><dt>iy / iz</dt><dd>{section.radius_y_mm?.toFixed(2) ?? "—"} / {section.radius_z_mm?.toFixed(2) ?? "—"} mm</dd></div></dl>{section.property_trace?.map((line) => <p key={line}>{line}</p>)}<small>{section.assumptions?.join("；")}</small></details>; })()}
                      </div>
                    ))}
                    {foundationSpecifications.map((specification, index) => (
                      <div className="scene-climate-guide" key={specification.node_id}>
                        <div><strong>{visibleNodes.find((node) => node.id === specification.node_id)?.label} · {specification.foundation_system_id === "spread" ? "独立基础" : "条形基础"}</strong><span>尺寸为显式起始候选；不满足时返回失败，不自动切换桩基。</span></div>
                        <div className="parameter-grid compact-parameters">
                          {specification.foundation_system_id === "spread" && <label><span>基础形式</span><select value={specification.section_shape ?? "stepped"} onChange={(event) => { const shape = event.target.value as "prismatic" | "stepped" | "tapered"; setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, section_shape: shape, steps: shape === "stepped" ? (item.steps?.length ? item.steps : [{ length_m: Math.max(0.5, item.length_m - 0.6), width_m: Math.max(0.5, item.width_m - 0.6), height_mm: 250 }]) : [], tapered_top_length_m: shape === "tapered" ? (item.tapered_top_length_m ?? 0.6) : null, tapered_top_width_m: shape === "tapered" ? (item.tapered_top_width_m ?? 0.6) : null } : item)); }}><option value="stepped">阶形独立基础</option><option value="tapered">锥形独立基础</option><option value="prismatic">等厚独立基础</option></select></label>}
                          <label><span>基础长</span><div className="input-with-unit"><input type="number" min="0.5" step="0.1" value={specification.length_m} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, length_m: Number(event.target.value), selection_source: "user_locked", override_reason: "用户调整基础尺寸" } : item))} /><span>m</span></div></label>
                          <label><span>基础宽</span><div className="input-with-unit"><input type="number" min="0.5" step="0.1" value={specification.width_m} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, width_m: Number(event.target.value), selection_source: "user_locked", override_reason: "用户调整基础尺寸" } : item))} /><span>m</span></div></label>
                          <label><span>基础厚度</span><div className="input-with-unit"><input type="number" min="200" step="50" value={specification.thickness_mm} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, thickness_mm: Number(event.target.value), selection_source: "user_locked", override_reason: "用户调整基础尺寸" } : item))} /><span>mm</span></div></label>
                          <label><span>基础埋深</span><div className="input-with-unit"><input type="number" min="0" step="0.1" value={specification.embedment_m} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, embedment_m: Number(event.target.value), selection_source: "user_locked", override_reason: "用户调整基础埋深" } : item))} /><span>m</span></div></label>
                          <label><span>混凝土等级</span><select value={specification.concrete_grade} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, concrete_grade: event.target.value } : item))}><option>C25</option><option>C30</option><option>C35</option><option>C40</option></select></label>
                          <label><span>钢筋等级</span><select value={specification.rebar_grade} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, rebar_grade: event.target.value } : item))}><option>HRB400</option><option>HRB500</option></select></label>
                          <label><span>X向底筋直径</span><div className="input-with-unit"><input type="number" min="6" max="40" step="1" value={specification.reinforcement?.bottom_x_diameter_mm ?? specification.bar_diameter_mm} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, bar_diameter_mm: Number(event.target.value), reinforcement: { bottom_x_diameter_mm: Number(event.target.value), bottom_x_spacing_mm: item.reinforcement?.bottom_x_spacing_mm ?? item.bar_spacing_mm, bottom_y_diameter_mm: item.reinforcement?.bottom_y_diameter_mm ?? item.bar_diameter_mm, bottom_y_spacing_mm: item.reinforcement?.bottom_y_spacing_mm ?? item.bar_spacing_mm } } : item))} /><span>mm</span></div></label>
                          <label><span>X向底筋间距</span><div className="input-with-unit"><input type="number" min="50" max="400" step="10" value={specification.reinforcement?.bottom_x_spacing_mm ?? specification.bar_spacing_mm} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, bar_spacing_mm: Number(event.target.value), reinforcement: { bottom_x_diameter_mm: item.reinforcement?.bottom_x_diameter_mm ?? item.bar_diameter_mm, bottom_x_spacing_mm: Number(event.target.value), bottom_y_diameter_mm: item.reinforcement?.bottom_y_diameter_mm ?? item.bar_diameter_mm, bottom_y_spacing_mm: item.reinforcement?.bottom_y_spacing_mm ?? item.bar_spacing_mm } } : item))} /><span>mm</span></div></label>
                          <label><span>Y向底筋直径</span><div className="input-with-unit"><input type="number" min="6" max="40" step="1" value={specification.reinforcement?.bottom_y_diameter_mm ?? specification.bar_diameter_mm} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, reinforcement: { bottom_x_diameter_mm: item.reinforcement?.bottom_x_diameter_mm ?? item.bar_diameter_mm, bottom_x_spacing_mm: item.reinforcement?.bottom_x_spacing_mm ?? item.bar_spacing_mm, bottom_y_diameter_mm: Number(event.target.value), bottom_y_spacing_mm: item.reinforcement?.bottom_y_spacing_mm ?? item.bar_spacing_mm } } : item))} /><span>mm</span></div></label>
                          <label><span>Y向底筋间距</span><div className="input-with-unit"><input type="number" min="50" max="400" step="10" value={specification.reinforcement?.bottom_y_spacing_mm ?? specification.bar_spacing_mm} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, reinforcement: { bottom_x_diameter_mm: item.reinforcement?.bottom_x_diameter_mm ?? item.bar_diameter_mm, bottom_x_spacing_mm: item.reinforcement?.bottom_x_spacing_mm ?? item.bar_spacing_mm, bottom_y_diameter_mm: item.reinforcement?.bottom_y_diameter_mm ?? item.bar_diameter_mm, bottom_y_spacing_mm: Number(event.target.value) } } : item))} /><span>mm</span></div></label>
                          {specification.foundation_system_id === "spread" && <label className="toggle-field"><span>钢筋混凝土短柱</span><button type="button" className={specification.pedestal?.enabled ? "toggle active" : "toggle"} aria-pressed={Boolean(specification.pedestal?.enabled)} onClick={() => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, pedestal: item.pedestal?.enabled ? { enabled: false } : { enabled: true, length_mm: 500, width_mm: 500, height_mm: 600, longitudinal_bar_count: 8, longitudinal_bar_diameter_mm: 16, stirrup_diameter_mm: 8, stirrup_spacing_mm: 150 } } : item))}><span /></button></label>}
                          {specification.pedestal?.enabled && <><label><span>短柱截面</span><div className="input-with-unit"><input type="number" min="150" step="50" value={specification.pedestal.length_mm ?? 500} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, pedestal: { ...item.pedestal!, length_mm: Number(event.target.value), width_mm: Number(event.target.value) } } : item))} /><span>mm</span></div></label><label><span>短柱净高</span><div className="input-with-unit"><input type="number" min="100" step="50" value={specification.pedestal.height_mm ?? 600} onChange={(event) => setFoundationSpecifications((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, pedestal: { ...item.pedestal!, height_mm: Number(event.target.value) } } : item))} /><span>mm</span></div></label></>}
                        </div>
                      </div>
                    ))}
                    {hasGenericFoundation && <div className="boundary-note">联合基础、偏心基础＋拉梁为高级选型；整板/筏板仅面向规则池体或密集多柱。桩承台仅在有项目勘察和桩基资料时开放，当前不会自动切换。</div>}
                  </div>
                </details>
              )}

              <details className="settings-section" open>
                <summary>
                  <span><strong>尺寸、连接与支承</strong><small>几何参数和条件化地基</small></span>
                  <ChevronDown size={17} />
                </summary>
                <div className="settings-section-body">
                  {family.id === "pergola-pavilion" && <div className="scene-climate-guide">
                    <div><strong>亭廊几何生成器</strong><span>平顶、坡顶、多跨和不同柱高由同一组轴网与标高生成，不再切换场景分类。</span></div>
                    <div className="geometry-preset-row" aria-label="亭廊几何快速起点">
                      <button type="button" onClick={() => { setXBaySpans("4"); setYBaySpans("3"); setColumnHeights("3"); setOmittedColumns(""); setRoofGeometry("flat"); }}>规则单跨</button>
                      <button type="button" onClick={() => { setXBaySpans("4,4,4"); setYBaySpans("3"); setColumnHeights("3"); setOmittedColumns(""); setRoofGeometry("flat"); }}>长廊多跨</button>
                      <button type="button" onClick={() => { setXBaySpans("4,4"); setYBaySpans("3,3"); setColumnHeights("3"); setOmittedColumns("3-2,3-3"); setRoofGeometry("flat"); }}>L形平面</button>
                    </div>
                    <div className="parameter-grid compact-parameters">
                      <label><span>X向各跨</span><input value={xBaySpans} onChange={(event) => setXBaySpans(event.target.value)} placeholder="例如 4,4,3.5" /><small>单位 m，逗号分隔；数量决定跨数</small></label>
                      <label><span>Y向各跨</span><input value={yBaySpans} onChange={(event) => setYBaySpans(event.target.value)} placeholder="例如 3,3" /><small>单位 m，逗号分隔</small></label>
                      <label><span>屋面几何</span><select value={roofGeometry} onChange={(event) => setRoofGeometry(event.target.value as typeof roofGeometry)}><option value="flat">平面屋盖</option><option value="single_slope">单坡屋盖</option><option value="double_slope">双坡屋盖</option><option value="custom_heights">逐柱控制标高</option></select></label>
                      {(roofGeometry === "single_slope" || roofGeometry === "double_slope") && <label><span>屋面坡度</span><div className="input-with-unit"><input type="number" min="0.5" max="45" step="0.5" value={roofSlopeDeg} onChange={(event) => setRoofSlopeDeg(Number(event.target.value))} /><span>°</span></div></label>}
                      {(roofGeometry === "single_slope" || roofGeometry === "double_slope") && <label><span>出坡方向角</span><div className="input-with-unit"><input type="number" min="-360" max="360" step="5" value={roofDirectionDeg} onChange={(event) => setRoofDirectionDeg(Number(event.target.value))} /><span>°</span></div><small>0° 为 +X，90° 为 +Y；修改方向不改变平面边界和构件编号。</small></label>}
                      <label><span>{roofGeometry === "custom_heights" ? "各柱顶标高" : "檐口/基准柱高"}</span><input value={columnHeights} onChange={(event) => setColumnHeights(event.target.value)} placeholder={roofGeometry === "custom_heights" ? "例如 3,3.2,3.5" : "例如 3"} /><small>{roofGeometry === "custom_heights" ? "按 X 后 Y 顺序，不足时沿用最后一个值" : "单位 m；坡度由软件生成其他柱顶标高"}</small></label>
                      <label><span>移除柱位置</span><input value={omittedColumns} onChange={(event) => setOmittedColumns(event.target.value)} placeholder="例如 2-1,3-2" /><small>只移除柱、柱脚支承和基础；屋面节点与钢梁保持不变。</small></label>
                    </div>
                    {geometryProfile && <div className="boundary-note">当前模型：{geometryProfile.nodes.length} 个节点、{geometryProfile.members.length} 根杆件、{geometryProfile.roof_surfaces.length} 个屋面分区。上限为 200 节点 / 400 杆件。</div>}
                    {geometryProfile && <div className="boundary-note">二维编辑器与三维模型固定显示在工作台右侧；修改这里的轴网参数会重新生成起始模型。</div>}
                  </div>}
                  <div className="parameter-grid">
                    {visibleParameters.map((parameter) => (
                      <label key={parameter.key}>
                        <span>{parameter.label}</span>
                        {parameter.value_type === "choice" ? (
                          <select
                            value={String(parameters[parameter.key] ?? "")}
                            onChange={(event) => {
                              setParameters((current) => ({
                                ...current,
                                [parameter.key]: event.target.value,
                              }));
                              markChanged(visibleNodes.map((node) => node.id));
                            }}
                          >
                            {parameter.options.map((option) => (
                              <option key={option}>{option}</option>
                            ))}
                          </select>
                        ) : (
                          <div className="input-with-unit">
                            <input
                              type={parameter.value_type === "number" ? "number" : "text"}
                              value={String(parameters[parameter.key] ?? "")}
                              onChange={(event) => {
                                setParameters((current) => ({
                                  ...current,
                                  [parameter.key]:
                                    parameter.value_type === "number"
                                      ? Number(event.target.value)
                                      : event.target.value,
                                }));
                                markChanged(visibleNodes.map((node) => node.id));
                              }}
                            />
                            {parameter.unit && <span>{parameter.unit}</span>}
                          </div>
                        )}
                      </label>
                    ))}
                    {hasGenericFoundation && (
                      <>
                        <label><span>结果阶段</span><select value={designStage} onChange={(event) => setDesignStage(event.target.value as DesignStage)}><option value="scheme_estimate">方案测算（区域参考）</option><option value="project_check">工程校核（勘察资料）</option></select></label>
                        {designStage === "scheme_estimate" && <label><span>区域土质参考档</span><select value={soilHintId} onChange={(event) => { const value = event.target.value; setSoilHintId(value); const presets: Record<string, [string, number]> = { "zj-coastal-soft-clay": ["软塑至流塑黏性土", 60], "zj-inland-alluvial": ["可塑黏性土或中密粉土", 100], "zj-mountain-residual": ["可塑至硬塑残积土", 160] }; const preset = presets[value]; if (preset) { setSoilClass(preset[0]); setBearingCapacity(preset[1]); setBearingSource("浙江区域参考档，用户已确认现场土质类别"); } }}><option value="zj-coastal-soft-clay">浙江沿海平原—软黏土参考档</option><option value="zj-inland-alluvial">浙江内陆平原—一般黏性土参考档</option><option value="zj-mountain-residual">浙江山地丘陵—残积土参考档</option></select></label>}
                        <label><span>现场确认土质类型</span><input value={soilClass} onChange={(event) => setSoilClass(event.target.value)} /></label>
                        <label><span>地基承载力特征值<HelpTip term="地基承载力" what="地基在正常使用条件下允许采用的承载能力。" adopted="方案阶段采用已确认土质档的保守参考值；工程校核采用勘察值。" changeWhen="取得项目岩土勘察报告或现场土质与参考档不符时。" /></span><div className="input-with-unit"><input aria-label="地基承载力特征值" type="number" min="1" value={bearingCapacity} onChange={(event) => setBearingCapacity(event.target.value ? Number(event.target.value) : "")} /><span>kPa</span></div></label>
                        <label><span>承载力资料来源</span><input value={bearingSource} onChange={(event) => setBearingSource(event.target.value)} /></label>
                        <label><span>地下水条件<HelpTip term="地下水" what="影响基础有效自重、浮力和土压力的设计水位边界。" adopted="按相对场地 ±0.000 的标高分别记录施工、使用和抗浮水位。" changeWhen="取得勘察、季节最高水位或运营控制水位资料时。" /></span><select aria-label="地下水条件" value={groundwaterCondition} onChange={(event) => setGroundwaterCondition(event.target.value as GroundwaterCondition)}><option value="unknown">尚未确认</option><option value="no_influence">有资料证明无影响</option><option value="known_water_table">已知三个设计水位</option></select></label>
                        {groundwaterCondition === "known_water_table" && <><label><span>施工期水位标高</span><div className="input-with-unit"><input type="number" step="0.1" value={constructionWaterLevel} onChange={(event) => setConstructionWaterLevel(event.target.value === "" ? "" : Number(event.target.value))} /><span>m</span></div></label><label><span>正常使用水位标高</span><div className="input-with-unit"><input type="number" step="0.1" value={serviceWaterLevel} onChange={(event) => setServiceWaterLevel(event.target.value === "" ? "" : Number(event.target.value))} /><span>m</span></div></label><label><span>抗浮设计水位标高</span><div className="input-with-unit"><input type="number" step="0.1" value={antifloatWaterLevel} onChange={(event) => setAntifloatWaterLevel(event.target.value === "" ? "" : Number(event.target.value))} /><span>m</span></div></label></>}
                        <label><span>地下水资料来源</span><input value={groundwaterSource} placeholder="勘察报告、水位记录或无影响依据" onChange={(event) => setGroundwaterSource(event.target.value)} /></label>
                        {designStage === "project_check" && <><label><span>勘察报告名称</span><input value={geotechnicalReportName} onChange={(event) => setGeotechnicalReportName(event.target.value)} /></label><label><span>报告日期</span><input type="date" value={geotechnicalReportDate} onChange={(event) => setGeotechnicalReportDate(event.target.value)} /></label><label><span>变形模量</span><div className="input-with-unit"><input type="number" min="0.1" step="0.1" value={deformationModulus} onChange={(event) => setDeformationModulus(event.target.value === "" ? "" : Number(event.target.value))} /><span>MPa</span></div></label></>}
                      </>
                    )}
                  </div>
                  {!hasGenericFoundation && conditionProfile.geotechnical_mode === "generic" && (
                    <div className="boundary-note success-note">
                      当前变体通过墙体预埋件与锚筋支承，不需要基础或地勘输入。
                    </div>
                  )}
                  {conditionProfile.geotechnical_mode === "variant_owned" && (
                    <div className="boundary-note success-note">
                      当前场景的土、水、抗浮和地基参数已在本场景专属输入中设置，不重复显示通用基础面板。
                    </div>
                  )}
                </div>
              </details>

              <details className="settings-section" open>
                <summary>
                  <span><strong>荷载与环境</strong><small>{loadPackageTitle}</small></span>
                  <ChevronDown size={17} />
                </summary>
                <div className="settings-section-body">
                    {(hasConditions || conditionProfile.wind === "optional") && (
                      <div className="scene-climate-guide">
                        <div>
                          <strong>统一项目条件向导</strong>
                          <span>仅显示当前场景需要的地区、气象和地震条件；自动值会随修订一并留存。</span>
                        </div>
                        {needsWind && (
                          <div className="parameter-grid compact-parameters">
                            <label><span>竖向围护</span><select value={verticalEnclosure} onChange={(event) => setVerticalEnclosure(event.target.value as typeof verticalEnclosure)}><option value="none">无围护</option><option value="open_members">格栅/杆件</option><option value="perforated_panel">穿孔板</option><option value="solid_panel">实体面板</option></select></label>
                            {(verticalEnclosure === "open_members" || verticalEnclosure === "perforated_panel") && <label><span>竖向开孔率</span><div className="input-with-unit"><input type="number" min="0" max="1" step="0.05" value={verticalOpenRatio} onChange={(event) => setVerticalOpenRatio(event.target.value === "" ? "" : Number(event.target.value))} /><span>0–1</span></div></label>}
                            <label><span>顶部覆盖</span><select value={topCover} onChange={(event) => setTopCover(event.target.value as typeof topCover)}><option value="none">无顶部覆盖</option><option value="louver_grid">百叶/格栅</option><option value="permeable_cover">透水覆盖</option><option value="solid_roof">实体屋盖</option></select></label>
                            {topCover !== "none" && <label><span>屋面构造</span><select value={roofAssemblyId} onChange={(event) => setRoofAssemblyId(event.target.value)}>{roofAssemblies.filter((item) => item.id !== "none").map((item) => <option key={item.id} value={item.id}>{item.title} · {item.total_dead_load_kn_m2} kN/m²</option>)}</select><small>{roofAssemblies.find((item) => item.id === roofAssemblyId)?.source_reference}</small></label>}
                            {(topCover === "louver_grid" || topCover === "permeable_cover") && <label><span>顶部开孔率</span><div className="input-with-unit"><input type="number" min="0" max="1" step="0.05" value={topOpenRatio} onChange={(event) => setTopOpenRatio(event.target.value === "" ? "" : Number(event.target.value))} /><span>0–1</span></div></label>}
                          </div>
                        )}
                        {conditionProfile.wind === "optional" && (
                          <label className="toggle-field">
                            <span>施工阶段临时风工况</span>
                            <button
                              type="button"
                              className={optionalWindEnabled ? "toggle active" : "toggle"}
                              aria-pressed={optionalWindEnabled}
                              onClick={() => setOptionalWindEnabled((value) => !value)}
                            ><span /></button>
                          </label>
                        )}
                        <div className="climate-guide-grid">
                          {(needsWind || needsSnow) && <>
                            <label>
                              <span>地区档</span>
                              <select value={climateLocationId} onChange={(event) => setClimateLocationId(event.target.value as ClimateRegionId)}>
                                {(climateCatalog?.items ?? []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                              </select>
                              {selectedClimate && selectedClimate.station_scope.length > 0 && <small>站点范围：{selectedClimate.station_scope.join("、")}</small>}
                            </label>
                            <label>
                              <span>重现期<HelpTip term="重现期" what="统计意义上某一荷载水平平均再次出现的时间。" adopted="默认采用 50 年，并从所选地区档读取对应基本值。" changeWhen="项目任务书或当地资料明确要求 10 年或 100 年时。" /></span>
                              <select value={recurrence} onChange={(event) => setRecurrence(event.target.value as "10" | "50" | "100")}>
                                <option value="10">10 年</option><option value="50">50 年（默认）</option><option value="100">100 年</option>
                              </select>
                            </label>
                          </>}
                          {climateLocationId === "manual" && needsWind && <label><span>基本风压 (kPa)<HelpTip term="基本风压" what="项目所在地规范站点给出的基准风作用。" adopted="与环境和场景自动形态系数相乘。" changeWhen="使用项目所在地正式资料或专项风环境成果时。" /></span><input type="number" min="0.01" step="0.01" value={manualWind} onChange={(event) => setManualWind(event.target.value === "" ? "" : Number(event.target.value))} /></label>}
                          {climateLocationId === "manual" && needsSnow && <label><span>基本雪压 (kPa)</span><input type="number" min="0" step="0.01" value={manualSnow} onChange={(event) => setManualSnow(event.target.value === "" ? "" : Number(event.target.value))} /></label>}
                          {climateLocationId === "manual" && (needsWind || needsSnow) && <label><span>资料来源</span><input value={manualClimateSource} onChange={(event) => setManualClimateSource(event.target.value)} placeholder="资料名称、页码或条款" /></label>}
                          {needsWind && <label>
                            <span>环境类型<HelpTip term="地面粗糙度" what="周边地表对近地风速的影响类别。" adopted="转成自动高度/地形系数，不要求直接填写系数。" changeWhen="项目位于海岸、密集城区或地貌与默认值明显不同。" /></span>
                            <select value={terrainCategory} onChange={(event) => setTerrainCategory(event.target.value as "A" | "B" | "C" | "D")}><option value="A">开阔海岸</option><option value="B">乡村 / 郊野</option><option value="C">一般城市</option><option value="D">密集城区</option></select>
                          </label>}
                          {needsSnow && conditionProfile.snow_semantics === "exposed_horizontal" && <label>
                            <span>露天积雪是否适用</span>
                            <select value={snowExposure} onChange={(event) => setSnowExposure(event.target.value as SnowExposure)}><option value="exposed">适用露天积雪规则</option><option value="not_applicable">本项目不计积雪</option></select>
                          </label>}
                          {needsSnow && snowExposure === "not_applicable" && <label><span>不计积雪依据</span><input value={snowExemptionReason} onChange={(event) => setSnowExemptionReason(event.target.value)} placeholder="项目所在地资料、任务书或专项说明" /></label>}
                          {needsSeismic && <label>
                            <span>地震烈度 / 设计基本加速度<HelpTip term="设防烈度" what="项目所在地抗震设防要求，与设计基本加速度成对使用。" adopted="按所选档生成正负 X/Y 等效水平地震作用。" changeWhen="以项目抗震设防资料或当地主管部门要求为准。" /></span>
                            <select aria-label="地震烈度与设计基本加速度" value={seismicLevel} onChange={(event) => setSeismicLevel(event.target.value as SeismicLevel | "")}><option value="">请选择（必填）</option>{(seismicCatalog?.items ?? []).map((item) => <option key={item.level} value={item.level}>{item.intensity}度 / {item.design_acceleration_g.toFixed(2)}g</option>)}</select>
                          </label>}
                        </div>
                        {(needsWind || needsSnow) && <div className="boundary-note success-note">
                          基本值 {selectedClimate && climateLocationId !== "manual" ? `${needsWind ? `风 ${selectedClimate.wind_kpa[recurrence]} kPa` : ""}${needsWind && needsSnow ? " / " : ""}${needsSnow ? `雪 ${selectedClimate.snow_kpa[recurrence]} kPa` : ""}` : "待填写"}
                          {needsWind && ` → 风系数 ${semanticFactors.heightFactor}×${semanticFactors.windShape}`}
                          {needsSnow && snowExposure === "exposed" && ` → 积雪系数 ${semanticFactors.snowShape}`}
                          → 最终采用值写入下方荷载与报告
                        </div>}
                        {(needsWind || needsSnow) && <button type="button" className="secondary-button" onClick={() => setAdvancedClimateOpen((value) => !value)} aria-expanded={advancedClimateOpen}>高级参数</button>}
                        {advancedClimateOpen && (needsWind || needsSnow) && <div className="climate-guide-grid">
                          {needsWind && <label><span>高度系数覆盖值</span><input type="number" min="0.01" step="0.05" value={heightFactorOverride} onChange={(event) => setHeightFactorOverride(event.target.value === "" ? "" : Number(event.target.value))} /></label>}
                          {needsWind && <label><span>体型系数覆盖值<HelpTip term="体型系数" what="构筑物外形对局部风作用的放大或减小影响。" adopted="按当前场景的屋盖、面板或构架类型自动取值。" changeWhen="已有专项风洞、产品资料或明确规范取值时。" /></span><input type="number" min="0.01" step="0.05" value={shapeFactorOverride} onChange={(event) => setShapeFactorOverride(event.target.value === "" ? "" : Number(event.target.value))} /></label>}
                          {needsSnow && <label><span>积雪系数覆盖值<HelpTip term="积雪系数" what="屋面或露天水平面上积雪分布的换算系数。" adopted="按场景屋面形式或露天水平面规则自动取值。" changeWhen="屋面构造、积雪易堆积部位或专项资料明确不同取值时。" /></span><input type="number" min="0.01" step="0.05" value={snowFactorOverride} onChange={(event) => setSnowFactorOverride(event.target.value === "" ? "" : Number(event.target.value))} /></label>}
                          <label><span>覆盖原因</span><input value={factorOverrideReason} onChange={(event) => setFactorOverrideReason(event.target.value)} /></label>
                        </div>}
                        {(needsWind || needsSnow) && <div className="boundary-note success-note">{climateInputsReady ? "荷载已随地区、屋面、坡度和高度自动更新" : "待填写完整地区、屋面或气象资料后自动计算；未完成值不会作为零荷载参与计算"}</div>}
                      </div>
                    )}
                  <div className="scene-load-table">
                    {loadCases.map((item, index) => (
                      <article className="scene-load-card" key={item.id}>
                        <div className="load-card-heading">
                          <div>
                            <strong>{item.label}</strong>
                            <span>{loadRange(item)} · {item.application_target}</span>
                          </div>
                        </div>
                        <div className="load-card-fields">
                          <label>
                            <span>最终采用值</span>
                            <div className="input-with-unit">
                              <input type="number" step="any" value={item.value_type === "calculated" && (item.kind === "wind" || item.kind === "snow") && !climateInputsReady ? "" : item.adopted_value} placeholder={item.value_type === "calculated" && !climateInputsReady ? "待完成条件" : undefined} readOnly={item.value_type === "calculated"} onChange={(event) => { const adopted = Number(event.target.value); updateLoadCase(index, { adopted_value: adopted, override_reason: adopted !== item.recommended_default ? item.override_reason : undefined }); }} />
                              <span>{item.unit}</span>
                            </div>
                          </label>
                          {item.value_type === "project_defined" ? <label>
                            <span>方向</span>
                            <select
                              value={item.direction ?? "gravity"}
                              disabled={item.value_type !== "project_defined"}
                              onChange={(event) =>
                                updateLoadCase(index, {
                                  direction: event.target.value as SceneLoadCase["direction"],
                                })
                              }
                            >
                              {item.direction &&
                                ![
                                  "gravity",
                                  "uplift",
                                  "x_positive",
                                  "x_negative",
                                  "y_positive",
                                  "y_negative",
                                ].includes(item.direction) && (
                                  <option value={item.direction}>{item.direction}</option>
                                )}
                              <option value="gravity">向下/重力</option>
                              <option value="uplift">上拔/风吸</option>
                              <option value="x_positive">X 正向</option>
                              <option value="x_negative">X 负向</option>
                              <option value="y_positive">Y 正向</option>
                              <option value="y_negative">Y 负向</option>
                            </select>
                          </label> : <div className="boundary-note">方向工况由后台自动生成并取控制包络，普通界面无需选择。</div>}
                        </div>
                        <p>{item.source_reference || "来源待填写"} · {item.applicable_when}</p>
                        {item.value_type !== "project_defined" &&
                          item.recommended_default !== undefined &&
                          item.adopted_value !== item.recommended_default && (
                            <label className="override-reason-field">
                              <span>覆盖建议值的原因</span>
                              <input
                                value={item.override_reason ?? ""}
                                placeholder="例如：采用项目设备资料或专项复核值"
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    override_reason: event.target.value,
                                  })
                                }
                              />
                            </label>
                          )}
                        {item.value_type === "project_defined" && (
                          <div className="custom-load-fields">
                            <label>
                              <span>荷载类别</span>
                              <select
                                value={item.kind}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    kind: event.target.value as SceneLoadCase["kind"],
                                  })
                                }
                              >
                                <option value="dead">恒载</option>
                                <option value="live">活荷载</option>
                                <option value="wind">风荷载</option>
                                <option value="snow">雪荷载</option>
                                <option value="soil">土压力</option>
                                <option value="water">水压力</option>
                                <option value="buoyancy">浮力</option>
                                <option value="custom">项目资料 / 其他</option>
                              </select>
                            </label>
                            <label>
                              <span>单位</span>
                              <select
                                value={item.unit}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    unit: event.target.value,
                                    distribution:
                                      event.target.value === "kN"
                                        ? "point"
                                        : event.target.value === "kN/m"
                                          ? "line"
                                          : "area",
                                  })
                                }
                              >
                                <option value="kN/m2">kN/m²</option>
                                <option value="kN/m">kN/m</option>
                                <option value="kN">kN</option>
                              </select>
                            </label>
                            <label>
                              <span>作用目标</span>
                              <select
                                value={item.application_target}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    application_target: event.target.value,
                                  })
                                }
                              >
                                {visibleNodes.map((node) => (
                                  <option key={node.id} value={node.id}>{node.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              <span>分布形式</span>
                              <select
                                value={item.distribution}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    distribution: event.target.value as SceneLoadCase["distribution"],
                                  })
                                }
                              >
                                <option value="point">集中荷载</option>
                                <option value="line">线荷载</option>
                                <option value="area">面荷载</option>
                                <option value="pressure">压力</option>
                              </select>
                            </label>
                            <label>
                              <span>资料名称</span>
                              <input
                                value={item.project_source ?? ""}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    project_source: event.target.value,
                                  })
                                }
                              />
                            </label>
                            <label>
                              <span>页码 / 条款</span>
                              <input
                                value={item.source_reference}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    source_reference: event.target.value,
                                  })
                                }
                              />
                            </label>
                            <label>
                              <span>说明</span>
                              <input
                                value={item.notes ?? ""}
                                onChange={(event) =>
                                  updateLoadCase(index, {
                                    notes: event.target.value,
                                  })
                                }
                              />
                            </label>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                  <div className="load-table-actions">
                    <button className="secondary-button" onClick={addCustomLoad}>
                      添加项目资料荷载
                    </button>
                  </div>
                  <div className="boundary-note">
                    <AlertTriangle size={17} />
                    风雪基本值仍须结合高度、体型和方向系数转换；场景包不替代项目专项资料。
                  </div>
                </div>
              </details>

              <div className="project-strip scene-project-strip compact-project-strip">
                <label>
                  <span>保存位置</span>
                  <select
                    value={selectedProject}
                    onChange={(event) =>
                      setSelectedProject(
                        event.target.value === "new" ? "new" : Number(event.target.value),
                      )
                    }
                  >
                    <option value="new">新建项目</option>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>{project.name}</option>
                    ))}
                  </select>
                </label>
                {selectedProject !== "new" && projectInstances.length > 0 && (
                  <label>
                    <span>当前方案</span>
                    <select
                      value={instance?.id ?? ""}
                      onChange={(event) => {
                        const selected = projectInstances.find(
                          (item) => item.id === Number(event.target.value),
                        );
                        if (selected) hydrateFromInstance(
                          selected,
                          instanceRevisions[selected.id] ?? [],
                        );
                      }}
                    >
                      {projectInstances.map((item) => (
                        <option key={item.id} value={item.id}>{item.title}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            </div>
          ) : (
            <div className="results-workbench">
              <div className={`scene-summary ${revision?.scene_result.status ?? "empty"} ${stale ? "stale" : ""}`}>
                <div>
                  <strong>{resultTitle()}</strong>
                  <span>
                    {revision
                      ? `${revision.scene_result.completed_nodes}/${revision.scene_result.total_required_nodes} 个必选节点 · ${revision.scene_result.result_class === "professional_check" ? "历史专业记录" : "方案筛查"}`
                      : "完成设置后即可生成可追溯修订"}
                  </span>
                </div>
                {revision && (
                  <div>
                    <strong>
                      {controllingUtilization(revision)?.toFixed(3) ?? "—"}
                    </strong>
                    <span>控制利用率 · 报告号 {revision.report_number}</span>
                  </div>
                )}
              </div>

              {revision ? (
                <>
                  <div className="result-action-row">
                    <button className="secondary-button" onClick={() => setTab("settings")}>修改参数</button>
                    <a
                      className="secondary-button"
                      href={`/api/v2/projects/${revision.project_id}/revisions/${revision.id}/report.pdf`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      下载 PDF 报告
                    </a>
                    <button
                      className="secondary-button"
                      disabled={stale || comparisonInstances.length >= 3 || working}
                      onClick={duplicateAlternative}
                    >
                      <Copy size={16} /> 复制为方案 {String.fromCharCode(65 + comparisonInstances.length)}
                    </button>
                    <button className="primary-button" disabled={working} onClick={evaluateScene}>
                      {working ? "计算中…" : "重新计算"}
                    </button>
                  </div>
                  <div className="result-warning-list">
                    {revision.scene_result.warnings.map((warning) => (
                      <p key={warning}><AlertTriangle size={15} />{warning}</p>
                    ))}
                  </div>
                  {revision.scene_result.space_frame_analysis && (
                    <div className="space-frame-result-card">
                      <div><strong>三维杆系分析</strong><span>{revision.scene_result.space_frame_analysis.solver} · 未独立验证</span></div>
                      <dl>
                        <div><dt>模型规模</dt><dd>{revision.scene_result.space_frame_analysis.node_count} 节点 / {revision.scene_result.space_frame_analysis.member_count} 杆件</dd></div>
                        <div><dt>屋面面积</dt><dd>{revision.scene_result.space_frame_analysis.roof_area_m2.toFixed(2)} m²</dd></div>
                        <div><dt>最大空间位移</dt><dd>{revision.scene_result.space_frame_analysis.maximum_translation_mm.toFixed(3)} mm</dd></div>
                        <div><dt>支座反力组</dt><dd>{Object.keys(revision.scene_result.space_frame_analysis.support_reactions).length} 组</dd></div>
                      </dl>
                      <p>{revision.scene_result.space_frame_analysis.load_scope}</p>
                    </div>
                  )}
                  {instanceRevisions[instance?.id ?? -1]?.length > 1 && (
                    <label className="revision-selector">
                      <span>查看历史修订</span>
                      <select
                        value={revision.id}
                        onChange={(event) => {
                          const selected = instanceRevisions[instance?.id ?? -1]?.find(
                            (item) => item.id === Number(event.target.value),
                          );
                          if (selected) setRevision(selected);
                        }}
                      >
                        {instanceRevisions[instance?.id ?? -1]?.map((item) => (
                          <option key={item.id} value={item.id}>
                            修订 {item.revision_number} · {item.report_number}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <section className="result-detail-grid" aria-label="计算结果详情">
                    <article>
                      <h3>控制验算</h3>
                      {Object.entries(revision.result_bundle).flatMap(([nodeId, result]) =>
                        result.checks.map((check) => ({ nodeId, check })),
                      ).sort((a, b) => b.check.utilization - a.check.utilization).slice(0, 8).map(({ nodeId, check }) => (
                        <div className="result-data-row" key={`${nodeId}-${check.name}`}>
                          <span>{check.name}<small>{nodeId}</small></span>
                          <strong>{(check.utilization * 100).toFixed(1)}%</strong>
                        </div>
                      ))}
                    </article>
                    <article>
                      <h3>控制组合与反力</h3>
                      {revision.scene_result.seismic_action_package && <>
                        <div className="result-data-row"><span>地震设计状况 · G_eq</span><strong>{revision.scene_result.seismic_action_package.gravity_representative_value_kn.toFixed(3)} kN</strong></div>
                        <div className="result-data-row"><span>±X / ±Y 等效地震作用</span><strong>±{revision.scene_result.seismic_action_package.f_ek_kn.toFixed(3)} kN</strong></div>
                      </>}
                      {Object.entries(revision.result_bundle).flatMap(([nodeId, result]) => [
                        ...result.combinations.slice(0, 2).map((combination) => ({
                          key: `${nodeId}-${combination.name}`,
                          label: combination.name,
                          value: `${combination.total.value.toFixed(3)} ${combination.total.unit}`,
                        })),
                        ...Object.entries(result.reactions).slice(0, 4).map(([name, value]) => ({
                          key: `${nodeId}-${name}`,
                          label: `${nodeId} · ${name}`,
                          value: `${value.value.toFixed(3)} ${value.unit}`,
                        })),
                      ]).slice(0, 10).map((item) => (
                        <div className="result-data-row" key={item.key}>
                          <span>{item.label}</span><strong>{item.value}</strong>
                        </div>
                      ))}
                    </article>
                    <article>
                      <h3>覆盖范围与缺失资料</h3>
                      <p>{revision.scene_result.completed_nodes}/{revision.scene_result.total_required_nodes} 个必选节点已处理</p>
                      {Object.values(revision.scene_result.node_results).map((node) => (
                        <div className="result-data-row" key={node.node_id}>
                          <span>{node.label}</span>
                          <strong>{node.applicability === "not_applicable" ? "不适用" : STATUS_LABELS[node.status]}</strong>
                        </div>
                      ))}
                      {revision.scene_result.missing_nodes.map((item) => (
                        <p className="missing-data" key={item}>缺失：{item}</p>
                      ))}
                    </article>
                  </section>
                </>
              ) : (
                <div className="empty-result">
                  <GitCompare size={28} />
                  <strong>尚未生成场景结果</strong>
                  <span>设置和结果只有两个页面，不需要逐步退出或重新选择场景。</span>
                  <button className="primary-button" onClick={() => setTab("settings")}>返回设置</button>
                </div>
              )}

              <section className="comparison-section">
                <div className="panel-heading">
                  <div><span className="eyebrow">OPTION COMPARISON</span><h2>方案对比</h2></div>
                  <span>{comparisonInstances.length}/3</span>
                </div>
                {comparisonInstances.length ? (
                  <div className="comparison-grid">
                    {comparisonInstances.map((alternative) => {
                      const comparedRevision = instanceRevisions[alternative.id]?.[0];
                      const comparedMaterial = alternative.draft_state.material_system as string | undefined;
                      return (
                      <article key={alternative.id} className={alternative.id === instance?.id ? "active" : ""}>
                        <div className="comparison-card-heading">
                          <strong>{alternative.title}</strong>
                          <span>
                            <button aria-label={`重命名${alternative.title}`} onClick={() => renameInstance(alternative)}><Pencil size={14} /></button>
                            <button aria-label={`归档${alternative.title}`} onClick={() => archiveInstance(alternative)}><Archive size={14} /></button>
                          </span>
                        </div>
                        <span>{comparedRevision ? `修订 ${comparedRevision.revision_number}` : "尚未计算"}</span>
                        <dl>
                          <div><dt>控制利用率</dt><dd>{comparedRevision ? controllingUtilization(comparedRevision)?.toFixed(3) ?? "—" : "—"}</dd></div>
                          <div><dt>材料体系</dt><dd>{comparedMaterial ?? "—"}</dd></div>
                          <div><dt>结论</dt><dd>{comparedRevision ? resultStatus(comparedRevision) : "待计算"}</dd></div>
                        </dl>
                        <small>{comparedRevision?.report_number ?? "草稿"}</small>
                        <button
                          className="quiet-button"
                          onClick={() => hydrateFromInstance(alternative, instanceRevisions[alternative.id] ?? [])}
                        >打开方案</button>
                      </article>
                    )})}
                  </div>
                ) : (
                  <p className="panel-description">计算后可复制为方案 A/B/C，并排比较控制利用率和主要参数。</p>
                )}
              </section>
            </div>
          )}

          {error && <div className="inline-error" role="alert">{error}</div>}

          <div className="scene-sticky-actions">
            <button className="secondary-button" disabled={working} onClick={saveOnly}>
              <Save size={16} /> {instance ? "更新草稿" : "保存草稿"}
            </button>
            <button className="primary-button" disabled={working} onClick={evaluateScene}>
              {working ? "正在计算…" : revision ? "重新计算" : "计算当前方案"}
            </button>
          </div>
        </section>

        {tab === "settings" && isParametricPergola && geometryProfile && (
          <aside className="plan-editor-panel" aria-label="二维结构编辑器">
            <div className="model-panel-heading">
              <div><span className="eyebrow">PLAN EDITOR</span><h2>二维精确编辑</h2></div>
              <span>{geometryProfile.nodes.length} 节点 · {geometryProfile.members.length} 杆件</span>
            </div>
            <PlanModelEditor
              geometry={geometryProfile}
              selected={modelSelection}
              onSelectedChange={setModelSelection}
              onChange={(next) => { setGeometryOverride(next); markChanged(visibleNodes.map((node) => node.id)); }}
              onMessage={setModelMessage}
            />
            <p className="model-editor-message" role="status">{modelMessage}</p>
          </aside>
        )}

        <aside className="load-path-panel desktop-load-path">
          {tab === "settings" && isParametricPergola && geometryProfile && (
            <div className="model-inspector-stack">
              <div className="load-path-heading">
                <div><span className="eyebrow">LIVE MODEL</span><h2>三维模型与属性</h2></div>
              </div>
              <SceneModelPreview
                geometry={geometryProfile}
                foundation={foundationSpecifications[0] ?? null}
                selectedMemberId={selectedModelMember?.id ?? null}
                onSelectMember={(id) => setModelSelection(id ? { kind: "member", id } : null)}
              />
              {selectedModelMember ? (
                <div className="selected-member-card">
                  <strong>{selectedModelMember.id} · {selectedModelMember.role}</strong>
                  <dl>
                    <div><dt>连接节点</dt><dd>{selectedModelMember.start_node_id} → {selectedModelMember.end_node_id}</dd></div>
                    <div><dt>实际长度</dt><dd>{selectedMemberLength?.toFixed(3) ?? "—"} m</dd></div>
                    <div><dt>构件组</dt><dd>{selectedModelMember.group_id}</dd></div>
                  </dl>
                  <label>
                    <span>截面分配</span>
                    <select
                      value={memberSectionOverrides[selectedModelMember.id] || memberGroupSections[selectedModelMember.group_id] || ""}
                      onChange={(event) => {
                        if (event.target.value === "__custom__") { setCustomSectionOpen(true); return; }
                        setMemberSectionOverrides((current) => ({ ...current, [selectedModelMember.id]: event.target.value }));
                        markChanged(visibleNodes.map((node) => node.id));
                      }}
                    >
                      <option value="">继承构件组</option>
                      {availableSections.map((item) => <option key={item.id} value={item.id}>{item.designation}</option>)}
                      <option value="__custom__">＋ 输入自定义截面</option>
                    </select>
                  </label>
                  <div className="member-scope-actions">
                    <button type="button" onClick={() => setMemberSectionOverrides((current) => { const next = { ...current }; delete next[selectedModelMember.id]; return next; })}>继承构件组</button>
                    <button type="button" disabled={!memberSectionOverrides[selectedModelMember.id]} onClick={() => { const sectionId = memberSectionOverrides[selectedModelMember.id]; if (!sectionId) return; setMemberGroupSections((current) => ({ ...current, [selectedModelMember.group_id]: sectionId })); setMemberSectionOverrides((current) => { const next = { ...current }; delete next[selectedModelMember.id]; return next; }); }}>应用到构件组</button>
                  </div>
                </div>
              ) : <div className="boundary-note">在二维或三维图中选择梁柱，规格和选择状态会同步。</div>}
            </div>
          )}
          <div className="load-path-heading">
            <div><span className="eyebrow">LOAD PATH</span><h2>当前传力链</h2></div>
            <span>{visibleNodes.length}</span>
          </div>
          {renderLoadPath()}
          <div className="scene-boundaries">
            <strong>适用边界</strong>
            {family.boundaries.map((boundary) => <span key={boundary}>• {boundary}</span>)}
          </div>
          <div className="revision-note">
            <FileClock size={15} /> 输入修改后旧结果失效；重新计算生成新修订，不覆盖历史报告。
          </div>
        </aside>
      </div>

      <details className="mobile-load-path">
        <summary>查看传力链与节点状态 <ChevronDown size={16} /></summary>
        {renderLoadPath(true)}
      </details>
    </div>
  );
}
