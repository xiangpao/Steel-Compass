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
  RotateCcw,
  Save,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { MODULE_MAP, normalizeInputs } from "@/lib/modules";
import type {
  ClimateCatalog,
  LoadItem,
  Mode,
  Module,
  Project,
  SceneFamily,
  SceneGraphTemplate,
  SceneInstance,
  SceneLoadCase,
  SceneRevision,
  SceneVariant,
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
  climateCatalog?: ClimateCatalog | null;
};

type WorkspaceTab = "settings" | "results";
type GroundwaterCondition = "no_influence" | "known_water_table" | "unknown";

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
  if (revision.scene_result.result_class === "quick_estimate") {
    return revision.scene_result.quick_outcome === "screening_failed"
      ? "方案快算需调整"
      : "方案快算完成";
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

export function SceneWorkspace({
  family,
  projects,
  onProjectsChange,
  climateCatalog,
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
  const [climateLocationId, setClimateLocationId] = useState("");
  const [recurrence, setRecurrence] = useState<"10" | "50" | "100">("50");
  const [heightFactor, setHeightFactor] = useState(1);
  const [shapeFactor, setShapeFactor] = useState(1);
  const [snowRoofFactor, setSnowRoofFactor] = useState(1);
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

  const variant = useMemo(
    () =>
      family.variants.find((item) => item.id === variantId) ??
      family.variants[0],
    [family, variantId],
  );
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
  const stale = Boolean(revision && inputVersion !== calculatedVersion);
  const loadPackageTitle = variant?.load_package?.title ?? "场景荷载包";
  const comparisonInstances = projectInstances.slice(0, 3);

  useEffect(() => {
    if (!climateLocationId && climateCatalog?.items.length) {
      setClimateLocationId(climateCatalog.items[0].id);
    }
  }, [climateCatalog, climateLocationId]);

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
          // Legacy local draft compatibility.
          groundwaterKnown?: boolean;
          sceneTitle?: string;
          selectedProject?: number | "new";
        };
        if (family.variants.some((item) => item.id === draft.variantId)) {
          nextVariantId = draft.variantId!;
        }
        const nextVariant = family.variants.find(
          (item) => item.id === nextVariantId,
        );
        const nextGraph = graphFor(family, nextVariant);
        setVariantId(nextVariantId);
        setMode(draft.mode ?? "quick");
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
        sceneTitle,
        selectedProject,
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
    const selectedVariant = family.variants.find(
      (item) => item.id === selected.variant_id,
    );
    if (!selectedVariant) return;
    const state = selected.draft_state ?? {};
    const restoredLoads = state.load_cases as SceneLoadCase[] | undefined;
    setInstance(selected);
    setVariantId(selected.variant_id);
    setMode(selected.mode);
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

  function applyClimateGuide() {
    const location = climateCatalog?.items.find(
      (item) => item.id === climateLocationId,
    );
    if (!location) {
      setError("请选择已复核的城市或气象站数据。");
      return;
    }
    setLoadCases((current) =>
      current.map((item) => {
        if (item.value_type !== "calculated") return item;
        const isWind = item.kind === "wind";
        const isSnow = item.kind === "snow";
        if (!isWind && !isSnow) return item;
        const basic = isWind
          ? location.wind_kpa[recurrence]
          : location.snow_kpa[recurrence];
        if (basic === null) return item;
        const adopted = isWind
          ? basic * heightFactor * shapeFactor
          : basic * snowRoofFactor;
        return {
          ...item,
          adopted_value: Number(adopted.toFixed(3)),
          source_reference: `${climateCatalog?.version ?? "climate"} · ${location.province}${location.city}/${location.station} · ${recurrence}年 · ${isWind ? `高度系数${heightFactor}×体型系数${shapeFactor}` : `屋面积雪系数${snowRoofFactor}`}`,
          override_reason: "风雪向导计算值",
        };
      }),
    );
    markChanged(
      visibleNodes
        .filter((node) => node.role === "load" || node.role === "surface")
        .map((node) => node.id),
    );
  }

  function draftState() {
    return {
      workspace_tab: tab,
      material_system: material,
      geometry: parameters,
      load_package_id: variant?.load_package?.id,
      load_cases: loadCases,
      foundation_type: hasFoundation ? foundationType : null,
      allowable_bearing_kpa: hasFoundation ? bearingCapacity : null,
      groundwater_condition: hasFoundation ? groundwaterCondition : null,
      water_table_depth_m:
        hasFoundation && groundwaterCondition === "known_water_table"
          ? waterTableDepth
          : null,
      groundwater_source: hasFoundation ? groundwaterSource : null,
    };
  }

  async function ensureProject(): Promise<number> {
    if (selectedProject !== "new") return selectedProject;
    const created = await api<Project>("/api/v2/projects", {
      method: "POST",
      body: JSON.stringify({ name: sceneTitle, description: family.description }),
    });
    suppressNextProjectLoad.current = true;
    setSelectedProject(created.id);
    onProjectsChange([created, ...projects]);
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
            mode,
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
          mode,
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
    const targeted = loadCases.filter(
      (item) =>
        item.application_target === nodeId ||
          item.application_target === "scene" ||
          item.application_target === "all",
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
    const nextInputs = {
      ...definition.defaults,
      ...Object.fromEntries(
        Object.entries(parameters).filter(([key]) => key in definition.defaults),
      ),
      ...boundInputs,
    };
    if (calculationModule === "spread_footing" || calculationModule === "strip_footing") {
      Object.assign(nextInputs, {
        soil_capacity_kpa: bearingCapacity || 120,
        groundwater_condition: groundwaterCondition,
        groundwater_source: groundwaterSource,
        soil_source:
          mode === "professional" ? "项目勘察资料" : "方案快算显式假定",
      });
      if (
        groundwaterCondition === "known_water_table" &&
        waterTableDepth !== ""
      ) {
        nextInputs.water_table_depth_m = waterTableDepth;
      } else {
        delete nextInputs.water_table_depth_m;
      }
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
        schema_version: "3.2",
        mode,
        module: calculationModule,
        project_name: `${sceneTitle} · ${nodeId}`,
        standard_profile: "CN-2026.1",
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
    if (hasFoundation && mode === "professional") {
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
    if (revision.scene_result.result_class === "quick_estimate") {
      return revision.scene_result.quick_outcome === "screening_failed"
        ? "方案快算需调整"
        : "方案快算已完成";
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
        <div className="inline-mode-switch" aria-label="场景计算模式">
          <button
            className={mode === "quick" ? "active" : ""}
            onClick={() => {
              setMode("quick");
              markChanged(visibleNodes.map((node) => node.id));
            }}
          >
            <Sparkles size={16} /> 方案快算
          </button>
          <button
            className={mode === "professional" ? "active" : ""}
            onClick={() => {
              setMode("professional");
              markChanged(visibleNodes.map((node) => node.id));
            }}
          >
            专业计算
          </button>
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

      <div className="scene-layout workbench-layout">
        <section className="scene-workbench">
          {tab === "settings" ? (
            <div className="settings-stack">
              <details className="settings-section" open>
                <summary>
                  <span><strong>方案与结构体系</strong><small>变体、材料和方案名称</small></span>
                  <ChevronDown size={17} />
                </summary>
                <div className="settings-section-body">
                  <div className="variant-grid compact-grid">
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
                  </div>
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

              <details className="settings-section" open>
                <summary>
                  <span><strong>尺寸、连接与支承</strong><small>几何参数和条件化地基</small></span>
                  <ChevronDown size={17} />
                </summary>
                <div className="settings-section-body">
                  <div className="parameter-grid">
                    {variant?.parameters.map((parameter) => (
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
                    {hasFoundation && (
                      <>
                        <label>
                          <span>基础策略</span>
                          <select
                            value={foundationType}
                            onChange={(event) => {
                              setFoundationType(event.target.value);
                              markChanged(
                                visibleNodes
                                  .filter((node) => node.role === "foundation")
                                  .map((node) => node.id),
                              );
                            }}
                          >
                            {foundationModules.has("spread_footing") && (
                              <option>独立基础</option>
                            )}
                            {foundationModules.has("strip_footing") && (
                              <option>条形基础</option>
                            )}
                          </select>
                        </label>
                        <label>
                          <span>地基承载力特征值</span>
                          <div className="input-with-unit">
                            <input
                              type="number"
                              placeholder={mode === "quick" ? "快算可暂按 120" : "请输入勘察值"}
                              value={bearingCapacity}
                              onChange={(event) => {
                                setBearingCapacity(
                                  event.target.value ? Number(event.target.value) : "",
                                );
                                markChanged(
                                  visibleNodes
                                    .filter((node) => node.role === "foundation")
                                    .map((node) => node.id),
                                );
                              }}
                            />
                            <span>kPa</span>
                          </div>
                          {!bearingCapacity && mode === "quick" && (
                            <small>未填写时采用显式方案假定 120 kPa，并写入报告。</small>
                          )}
                        </label>
                        <label>
                          <span>地下水条件</span>
                          <select
                            value={groundwaterCondition}
                            onChange={(event) => {
                              setGroundwaterCondition(
                                event.target.value as GroundwaterCondition,
                              );
                              markChanged(
                                visibleNodes
                                  .filter((node) => node.role === "foundation")
                                  .map((node) => node.id),
                              );
                            }}
                          >
                            <option value="no_influence">无地下水影响</option>
                            <option value="known_water_table">已知水位</option>
                            <option value="unknown">水位未知</option>
                          </select>
                        </label>
                        {groundwaterCondition === "known_water_table" && (
                          <label>
                            <span>地下水位埋深</span>
                            <div className="input-with-unit">
                              <input
                                type="number"
                                min="0"
                                step="0.1"
                                value={waterTableDepth}
                                onChange={(event) => {
                                  setWaterTableDepth(
                                    event.target.value
                                      ? Number(event.target.value)
                                      : "",
                                  );
                                  markChanged(
                                    visibleNodes
                                      .filter((node) => node.role === "foundation")
                                      .map((node) => node.id),
                                  );
                                }}
                              />
                              <span>m</span>
                            </div>
                          </label>
                        )}
                        <label>
                          <span>地下水资料来源</span>
                          <input
                            value={groundwaterSource}
                            placeholder="勘察报告、水位记录或无影响依据"
                            onChange={(event) => {
                              setGroundwaterSource(event.target.value);
                              markChanged(
                                visibleNodes
                                  .filter((node) => node.role === "foundation")
                                  .map((node) => node.id),
                              );
                            }}
                          />
                        </label>
                      </>
                    )}
                  </div>
                  {!hasFoundation && (
                    <div className="boundary-note success-note">
                      当前变体通过墙体预埋件与锚筋支承，不需要基础或地勘输入。
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
                  {loadCases.some(
                    (item) =>
                      item.value_type === "calculated" &&
                      (item.kind === "wind" || item.kind === "snow"),
                  ) && (
                    <div className="scene-climate-guide">
                      <div>
                        <strong>风雪荷载向导</strong>
                        <span>基本值必须来自已复核目录，最终值仍需确认系数。</span>
                      </div>
                      <div className="climate-guide-grid">
                        <label>
                          <span>城市 / 气象站</span>
                          <select
                            value={climateLocationId}
                            onChange={(event) => setClimateLocationId(event.target.value)}
                          >
                            {(climateCatalog?.items ?? []).map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.province} · {item.city} · {item.station}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>重现期</span>
                          <select
                            value={recurrence}
                            onChange={(event) =>
                              setRecurrence(event.target.value as "10" | "50" | "100")
                            }
                          >
                            <option value="10">10 年</option>
                            <option value="50">50 年</option>
                            <option value="100">100 年</option>
                          </select>
                        </label>
                        <label>
                          <span>风压高度变化系数</span>
                          <input type="number" step="0.05" min="0" value={heightFactor} onChange={(event) => setHeightFactor(Number(event.target.value))} />
                        </label>
                        <label>
                          <span>风荷载体型系数</span>
                          <input type="number" step="0.05" value={shapeFactor} onChange={(event) => setShapeFactor(Number(event.target.value))} />
                        </label>
                        <label>
                          <span>屋面积雪分布系数</span>
                          <input type="number" step="0.05" min="0" value={snowRoofFactor} onChange={(event) => setSnowRoofFactor(Number(event.target.value))} />
                        </label>
                        <button className="secondary-button" onClick={applyClimateGuide}>
                          计算并写入采用值
                        </button>
                      </div>
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
                        {item.kind === "snow" && (
                          <button
                            type="button"
                            className="load-na-button"
                            aria-pressed={item.notes?.startsWith("不适用：") ?? false}
                            onClick={() =>
                              updateLoadCase(index, {
                                value_type: "project_defined",
                                adopted_value: 0,
                                project_source: "",
                                source_reference: "",
                                notes: "不适用：请填写项目所在地或专项资料依据",
                              })
                            }
                          >
                            本项目雪荷载不适用
                          </button>
                        )}
                        <div className="load-card-fields">
                          <label>
                            <span>最终采用值</span>
                            <div className="input-with-unit">
                              <input
                                type="number"
                                step="any"
                                value={item.adopted_value}
                                onChange={(event) => {
                                  const adopted = Number(event.target.value);
                                  updateLoadCase(index, {
                                    adopted_value: adopted,
                                    override_reason:
                                      adopted !== item.recommended_default
                                        ? item.override_reason
                                        : undefined,
                                  });
                                }}
                              />
                              <span>{item.unit}</span>
                            </div>
                          </label>
                          <label>
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
                          </label>
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
                      ? `${revision.scene_result.completed_nodes}/${revision.scene_result.total_required_nodes} 个必选节点 · ${revision.scene_result.result_class === "professional_check" ? "专业检查" : "方案快算"}`
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

        <aside className="load-path-panel desktop-load-path">
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
