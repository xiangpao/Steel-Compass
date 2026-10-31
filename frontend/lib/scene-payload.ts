// Builds the per-node calculation requests a legacy scene sends to the
// scene-revision endpoint. Pure functions; the workspace passes its state in.

import { MODULE_MAP, normalizeInputs } from "@/lib/modules";
import { SCENE_ADAPTER_FIELDS } from "@/lib/scene-adapter-fields";
import type {
  FoundationDesignSpecification,
  LoadItem,
  MemberSpecification,
  Module,
  SceneConditionProfile,
  SceneGraphTemplate,
  SceneLoadCase,
  SectionCatalogEntry,
} from "@/lib/types";
import type { OptionalNumber, TopCover } from "@/lib/scene-profiles";

type GraphNode = SceneGraphTemplate["nodes"][number];

export type ScenePayloadContext = {
  graph: SceneGraphTemplate;
  visibleNodes: GraphNode[];
  loadCases: SceneLoadCase[];
  parameters: Record<string, unknown>;
  conditionProfile: SceneConditionProfile;
  topCover: TopCover;
  memberSpecifications: MemberSpecification[];
  foundationSpecifications: FoundationDesignSpecification[];
  availableSections: SectionCatalogEntry[];
  bearingCapacity: OptionalNumber;
  sceneTitle: string;
};

const LINE_OR_AREA_MODULES = [
  "steel_beam",
  "portal_frame",
  "concrete_beam",
  "concrete_slab",
  "timber_beam",
  "timber_deck_panel",
  "masonry_wall",
  "rc_wall",
  "steel_cantilever_post",
];

const ROOF_LOAD_IDS = ["roof-finish", "roof-maintenance", "roof-snow"];

const SECTION_KEYS = ["steel_grade", "section_type", "h_mm", "b_mm", "t_mm", "diameter_mm", "tw_mm", "tf_mm", "effective_length_m", "unbraced_length_m"];
const FOOTING_KEYS = ["length_m", "width_m", "thickness_mm", "embedment_m", "soil_capacity_kpa", "groundwater_depth_m", "water_table_depth_m"];

// Inputs that must come from explicit specifications, never module defaults.
const HIDDEN_CRITICAL_INPUTS: Record<string, string[]> = {
  steel_beam: SECTION_KEYS,
  steel_column: SECTION_KEYS,
  portal_frame: ["steel_grade", "beam_h_mm", "beam_b_mm", "beam_t_mm", "column_b_mm", "column_t_mm", "beam_section", "column_section"],
  spread_footing: FOOTING_KEYS,
  strip_footing: FOOTING_KEYS,
};

export function calculationLoads(nodeId: string, ctx: ScenePayloadContext): LoadItem[] {
  const calculationModule = ctx.visibleNodes.find((node) => node.id === nodeId)?.calculation_module as Module | undefined;
  if (calculationModule && SCENE_ADAPTER_FIELDS[calculationModule]) return [];
  const acceptedUnits = new Set<string>(
    calculationModule && LINE_OR_AREA_MODULES.includes(calculationModule) ? ["kN/m", "kN/m2"] : ["kN"],
  );
  const roofLoadsDisabled = ctx.conditionProfile.wind_semantics === "roof" && ctx.topCover === "none";
  const targeted = ctx.loadCases.filter(
    (item) =>
      !(roofLoadsDisabled && ROOF_LOAD_IDS.includes(item.id)) &&
      (item.application_target === nodeId || item.application_target === "scene" || item.application_target === "all"),
  );
  return targeted.map<LoadItem>((item) => {
    let value = item.adopted_value;
    let unit = item.unit as LoadItem["unit"];
    let direction = item.direction;
    if (!acceptedUnits.has(item.unit)) {
      unit = calculationModule === "strip_footing" ? "kN/m" : "kN";
      if (calculationModule === "steel_column" && item.kind === "dead" && item.unit === "kN/m2") {
        value = item.adopted_value * Number(ctx.parameters.panel_width_m ?? 1) * Number(ctx.parameters.panel_height_m ?? 1);
        direction = "gravity";
      } else {
        throw new Error(`荷载“${item.label}”的单位 ${item.unit} 与节点 ${nodeId} 不兼容，请调整作用节点或分布形式。`);
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

function applySpecifications(nextInputs: Record<string, unknown>, nodeId: string, calculationModule: Module, ctx: ScenePayloadContext) {
  const memberSpecs = ctx.memberSpecifications.filter((item) => item.node_id === nodeId);
  const sectionOf = (spec?: MemberSpecification) => ctx.availableSections.find((item) => item.id === spec?.section_catalog_id);
  if (calculationModule === "steel_beam" || calculationModule === "steel_column") {
    const specification = memberSpecs[0];
    const section = sectionOf(specification);
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
    const beamSection = sectionOf(beam);
    const columnSection = sectionOf(column);
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
    const foundation = ctx.foundationSpecifications.find((item) => item.node_id === nodeId);
    if (foundation) {
      const bars = foundation.reinforcement;
      Object.assign(nextInputs, {
        length_m: foundation.length_m,
        width_m: foundation.width_m,
        thickness_mm: foundation.thickness_mm,
        embedment_m: foundation.embedment_m,
        soil_capacity_kpa: Number(ctx.bearingCapacity),
        bar_dia_x_mm: bars?.bottom_x_diameter_mm ?? foundation.bar_diameter_mm ?? 14,
        bar_spacing_x_mm: bars?.bottom_x_spacing_mm ?? foundation.bar_spacing_mm ?? 150,
        bar_dia_y_mm: bars?.bottom_y_diameter_mm ?? foundation.bar_diameter_mm ?? 14,
        bar_spacing_y_mm: bars?.bottom_y_spacing_mm ?? foundation.bar_spacing_mm ?? 150,
      });
    }
  }
}

function applyDerivedActions(nextInputs: Record<string, unknown>, nodeId: string, calculationModule: Module, ctx: ScenePayloadContext) {
  const { parameters } = ctx;
  const targetLoads = ctx.loadCases.filter((item) => item.application_target === nodeId);
  if (calculationModule === "steel_column") {
    const panelArea = Number(parameters.panel_width_m ?? 1) * Number(parameters.panel_height_m ?? 1);
    const leverArm = Number(parameters.post_height_m ?? 1);
    const windMoment = Math.max(
      0,
      ...targetLoads.filter((item) => item.kind === "wind").map((item) => item.adopted_value * panelArea * leverArm),
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
      ...targetLoads.filter((item) => item.kind === "wind" && item.unit === "kN/m2").map((item) => item.adopted_value),
    );
    nextInputs.horizontal_load_kn_m = windPressure * wallHeight;
    nextInputs.moment_kn_m_per_m = (windPressure * wallHeight ** 2) / 2;
  }
}

export function nodeCalculationPayload(nodeId: string, calculationModule: Module, ctx: ScenePayloadContext) {
  const { parameters } = ctx;
  const definition = MODULE_MAP[calculationModule];
  const node = ctx.visibleNodes.find((item) => item.id === nodeId);
  const adapter = Boolean(SCENE_ADAPTER_FIELDS[calculationModule]);
  const boundInputs = Object.fromEntries(
    Object.entries(node?.input_bindings ?? {}).flatMap(([targetInput, sceneParameter]) =>
      parameters[sceneParameter] === undefined ? [] : [[targetInput, parameters[sceneParameter]]],
    ),
  );
  const nextInputs: Record<string, unknown> = {
    ...(adapter ? {} : definition.defaults),
    ...Object.fromEntries(Object.entries(parameters).filter(([key]) => key in definition.defaults)),
    ...boundInputs,
    ...(adapter
      ? {
          ...parameters,
          ...((parameters.scene_node_inputs as Record<string, Record<string, unknown>> | undefined)?.[nodeId] ?? {}),
          scene_parameters: parameters,
        }
      : {}),
  };
  HIDDEN_CRITICAL_INPUTS[calculationModule]?.forEach((key) => delete nextInputs[key]);
  applySpecifications(nextInputs, nodeId, calculationModule, ctx);
  if (
    ctx.conditionProfile.geotechnical_mode === "variant_owned" &&
    calculationModule === "pile_group_cap" &&
    parameters.allowable_bearing_kpa !== undefined
  ) {
    // Pool/bridge variants own their geotechnical inputs. Do not add the
    // generic foundation panel, while preserving the existing parameter for
    // older graph bindings and revision replays.
    nextInputs.capacity_source = "场景地基/桩基资料";
  }
  applyDerivedActions(nextInputs, nodeId, calculationModule, ctx);
  const inputUnits = Object.fromEntries(definition.fields.map((field) => [field.key, field.unit ?? "1"]));
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
      mode: "quick",
      module: calculationModule,
      project_name: `${ctx.sceneTitle} · ${nodeId}`,
      standard_profile: "CN-2026.6",
      // Dedicated server adapters consume saved scene geometry, loads and
      // explicit specialist fields; never invoke single-tool default builders.
      typed_inputs: definition.buildTypedInputs ? undefined : { module: calculationModule, values: typedValues },
      inputs: normalizeInputs(calculationModule, nextInputs),
      loads: calculationLoads(nodeId, ctx),
    },
  };
}
