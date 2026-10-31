"use client";

import { ChevronDown, FileClock, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, isAbortError } from "@/lib/api";
import { PergolaWorkbenchV2 } from "@/components/pergola-workbench-v2";
import { LoadPath } from "@/components/scene/load-path";
import { SceneResultsView } from "@/components/scene/scene-results-view";
import type { SceneSettingsModel } from "@/components/scene/scene-settings-model";
import { SceneSettingsView } from "@/components/scene/scene-settings-view";
import { useConditionDrivenLoads } from "@/components/scene/use-condition-driven-loads";
import { useLocalSceneDraft, type LocalSceneDraft } from "@/components/scene/use-local-scene-draft";
import { FOOTING_MODULES, STEEL_MEMBER_MODULES, useSceneSpecifications } from "@/components/scene/use-scene-specifications";
import { MODULE_MAP } from "@/lib/modules";
import {
  copiedLoadCases,
  currentLoadCases,
  foundationTypeForGraph,
  graphFor,
  initialValues,
  normalizedFoundations,
  sceneConditionProfile,
  validateLoadCases,
  type DesignStage,
  type GroundwaterCondition,
  type SnowExposure,
  type WorkspaceTab,
} from "@/lib/scene-model";
import { nodeCalculationPayload, type ScenePayloadContext } from "@/lib/scene-payload";
import {
  INITIAL_CONDITIONS,
  INITIAL_GEOTECH,
  buildGeotechnicalProfile,
  buildSiteProfile,
  buildStructuralProfile,
  conditionsFromSiteProfile,
  geotechFromProfile,
  semanticFactors as computeSemanticFactors,
  type SceneConditions,
  type SceneExposure,
  type SceneGeotech,
} from "@/lib/scene-profiles";
import type {
  ClimateRegionCatalog,
  FoundationDesignSpecification,
  MemberSpecification,
  Module,
  Project,
  ProjectGeotechnicalProfile,
  ProjectSiteProfile,
  RoofAssembly,
  SceneFamily,
  SceneGraphTemplate,
  SceneInstance,
  SceneLoadCase,
  SceneRevision,
  SceneStructuralProfile,
  SeismicDesignCatalog,
} from "@/lib/types";

type Props = {
  family: SceneFamily;
  projects: Project[];
  onProjectsChange: (projects: Project[]) => void;
  climateCatalog?: ClimateRegionCatalog | null;
  seismicCatalog?: SeismicDesignCatalog | null;
};

export function SceneWorkspace(props: Props) {
  if (props.family.id === "pergola-pavilion") {
    return <PergolaWorkbenchV2 mode="project" projects={props.projects} onProjectsChange={props.onProjectsChange} />;
  }
  return <LegacySceneWorkspace {...props} />;
}

function supportedFoundationType(graph: SceneGraphTemplate, stored: string | undefined) {
  const supported = graph.nodes.some(
    (node) =>
      (stored === "独立基础" && node.calculation_module === "spread_footing") ||
      (stored === "条形基础" && node.calculation_module === "strip_footing"),
  );
  return supported ? stored! : foundationTypeForGraph(graph);
}

function defaultExposure(windSemantics: string): Omit<SceneExposure, "roofAssemblyId"> {
  return {
    verticalEnclosure: windSemantics === "solid_panel" ? "solid_panel" : "none",
    topCover: windSemantics === "roof" ? "solid_roof" : "none",
    verticalOpenRatio: "",
    topOpenRatio: "",
  };
}

function LegacySceneWorkspace({ family, projects, onProjectsChange, climateCatalog, seismicCatalog }: Props) {
  const initialVariantId = family.default_variant_id ?? family.variants[0]?.id ?? "";
  const [variantId, setVariantId] = useState(initialVariantId);
  const [tab, setTab] = useState<WorkspaceTab>("settings");
  const [material, setMaterial] = useState(
    family.variants.find((item) => item.id === initialVariantId)?.material_systems[0] ?? "",
  );
  const [parameters, setParameters] = useState<Record<string, unknown>>(initialValues(family, initialVariantId));
  const [loadCases, setLoadCases] = useState<SceneLoadCase[]>([]);
  const [foundationType, setFoundationType] = useState("独立基础");
  const [geotech, setGeotech] = useState<SceneGeotech>(INITIAL_GEOTECH);
  const [conditions, setConditions] = useState<SceneConditions>(INITIAL_CONDITIONS);
  const [roofAssemblies, setRoofAssemblies] = useState<RoofAssembly[]>([]);
  const [exposure, setExposure] = useState<SceneExposure>({ ...defaultExposure("none"), roofAssemblyId: "steel-panel" });
  const [selectedProject, setSelectedProject] = useState<number | "new">("new");
  const [sceneTitle, setSceneTitle] = useState(family.title);
  const [instance, setInstance] = useState<SceneInstance | null>(null);
  const [revision, setRevision] = useState<SceneRevision | null>(null);
  const [projectInstances, setProjectInstances] = useState<SceneInstance[]>([]);
  const [instanceRevisions, setInstanceRevisions] = useState<Record<number, SceneRevision[]>>({});
  const [inputVersion, setInputVersion] = useState(0);
  const [calculatedVersion, setCalculatedVersion] = useState(-1);
  const [changedNodeIds, setChangedNodeIds] = useState<string[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const projectLoadSequence = useRef(0);
  const suppressNextProjectLoad = useRef(false);
  // Aborts the running evaluation when the workspace unmounts or the
  // project/family changes, so a late response is never shown as current.
  const evaluation = useRef<AbortController | null>(null);

  const variant = useMemo(() => family.variants.find((item) => item.id === variantId) ?? family.variants[0], [family, variantId]);
  const conditionProfile = useMemo(() => sceneConditionProfile(family, variant), [family, variant]);
  const needs = {
    wind: conditionProfile.wind === "required" || (conditionProfile.wind === "optional" && conditions.optionalWindEnabled),
    snow: conditionProfile.snow === "required",
    seismic: conditionProfile.seismic === "required",
  };
  const hasConditions = needs.wind || needs.snow || needs.seismic;
  const graph = useMemo(() => graphFor(family, variant), [family, variant]);
  const visibleNodes = useMemo(() => graph.nodes.filter((node) => node.applicability !== "not_applicable"), [graph]);
  const allNodeIds = visibleNodes.map((node) => node.id);
  const hasFoundation = visibleNodes.some((node) => node.role === "foundation" && node.calculation_module);
  const hasGenericFoundation = hasFoundation && conditionProfile.geotechnical_mode !== "variant_owned";
  const visibleParameters = (variant?.parameters ?? []).filter((parameter) => !parameter.hidden_when_condition_driven);
  const stale = Boolean(revision && inputVersion !== calculatedVersion);
  const comparisonInstances = projectInstances.slice(0, 3);

  const specs = useSceneSpecifications({ visibleNodes, parameters, selectedProject, onError: setError });
  const { memberSpecifications, foundationSpecifications, setMemberSpecifications, setFoundationSpecifications } = specs;

  useEffect(() => {
    api<{ items: RoofAssembly[] }>("/api/v2/catalogs/roof-assemblies")
      .then((catalog) => setRoofAssemblies(catalog.items))
      .catch(() => setRoofAssemblies([]));
  }, []);

  useEffect(() => {
    setExposure((current) => ({ ...current, ...defaultExposure(conditionProfile.wind_semantics) }));
  }, [conditionProfile.wind_semantics, variantId]);

  const factors = useMemo(
    () => computeSemanticFactors(conditionProfile, parameters, variant?.roof_form, conditions),
    [conditionProfile, parameters, variant?.roof_form, conditions],
  );
  const { selectedClimate, climateInputsReady } = useConditionDrivenLoads({
    needs,
    conditions,
    conditionProfile,
    exposure,
    factors,
    climateCatalog,
    roofAssemblies,
    variant,
    setLoadCases,
    setParameters,
    onLoadsChanged: () => setInputVersion((value) => value + 1),
  });

  useEffect(() => {
    if (selectedProject === "new") return;
    const project = projects.find((item) => item.id === selectedProject);
    if (project?.site_profile) {
      const restored = conditionsFromSiteProfile(project.site_profile);
      setConditions((current) => ({ ...current, ...restored }));
    }
    if (project?.geotechnical_profile) {
      const restored = geotechFromProfile(project.geotechnical_profile);
      setGeotech((current) => ({ ...current, ...restored }));
    }
  }, [projects, selectedProject]);

  function restoreLocalDraft(draft: LocalSceneDraft | null) {
    const defaultVariantId = family.default_variant_id ?? family.variants[0]?.id ?? "";
    const nextVariantId = draft && family.variants.some((item) => item.id === draft.variantId) ? draft.variantId! : defaultVariantId;
    const nextVariant = family.variants.find((item) => item.id === nextVariantId);
    const nextGraph = graphFor(family, nextVariant);
    const savedLoads = draft?.loadCases ? currentLoadCases(draft.loadCases) : undefined;
    // A draft without load cases is incomplete: keep its variant but start
    // from that variant's defaults, as earlier versions did.
    const fromDraft = savedLoads ? draft : null;
    setVariantId(nextVariantId);
    setMaterial(fromDraft?.material ?? nextVariant?.material_systems[0] ?? "");
    setParameters(fromDraft?.parameters ?? initialValues(family, nextVariantId));
    setLoadCases(savedLoads ?? copiedLoadCases(family, nextVariant, nextGraph));
    setSceneTitle(fromDraft?.sceneTitle ?? family.title);
    if (draft) {
      setFoundationType(supportedFoundationType(nextGraph, draft.foundationType));
      setGeotech((current) => ({
        ...current,
        bearingCapacity: draft.bearingCapacity ?? "",
        groundwaterCondition: draft.groundwaterCondition ?? (draft.groundwaterKnown ? "no_influence" : "unknown"),
        waterTableDepth: draft.waterTableDepth ?? "",
        groundwaterSource: draft.groundwaterSource ?? "",
        designStage: draft.designStage ?? "scheme_estimate",
      }));
      setConditions((current) => ({
        ...current,
        snowExposure: draft.snowExposure ?? "exposed",
        snowExemptionReason: draft.snowExemptionReason ?? "",
        optionalWindEnabled: draft.optionalWindEnabled ?? false,
      }));
      if (draft.memberSpecifications) setMemberSpecifications(draft.memberSpecifications);
      if (draft.foundationSpecifications) setFoundationSpecifications(normalizedFoundations(draft.foundationSpecifications));
      if (typeof draft.selectedProject === "number") setSelectedProject(draft.selectedProject);
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
  }

  useLocalSceneDraft(
    family.id,
    {
      variantId,
      mode: "quick",
      material,
      parameters,
      loadCases,
      foundationType,
      bearingCapacity: geotech.bearingCapacity,
      groundwaterCondition: geotech.groundwaterCondition,
      waterTableDepth: geotech.waterTableDepth,
      groundwaterSource: geotech.groundwaterSource,
      snowExposure: conditions.snowExposure,
      snowExemptionReason: conditions.snowExemptionReason,
      optionalWindEnabled: conditions.optionalWindEnabled,
      sceneTitle,
      selectedProject,
      designStage: geotech.designStage,
      memberSpecifications,
      foundationSpecifications,
    },
    restoreLocalDraft,
  );

  useEffect(() => {
    // Skipped for the project an evaluation has just created; any other
    // project switch cancels the running evaluation.
    if (suppressNextProjectLoad.current) {
      suppressNextProjectLoad.current = false;
      return;
    }
    evaluation.current?.abort();
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

  useEffect(() => () => evaluation.current?.abort(), []);

  // Specifications and geotechnical fields are edited in many places; mark the
  // result stale from their values instead of relying on each handler. The
  // fingerprint of the last calculated inputs is compared, so loading a
  // project or a revision does not count as an edit.
  const designInputFingerprint = JSON.stringify([memberSpecifications, foundationSpecifications, conditions.seismicLevel, geotech]);
  const calculatedFingerprint = useRef<string | null>(null);
  // Set when a revision is restored; the next render's values become the
  // baseline because the restored state is applied in the same batch.
  const captureFingerprint = useRef(false);
  useEffect(() => {
    if (captureFingerprint.current) {
      captureFingerprint.current = false;
      calculatedFingerprint.current = designInputFingerprint;
      return;
    }
    if (calculatedFingerprint.current === null || revision === null) return;
    if (calculatedFingerprint.current !== designInputFingerprint) {
      setInputVersion((current) => current + 1);
      calculatedFingerprint.current = designInputFingerprint;
    }
  }, [designInputFingerprint, revision]);

  function hydrateFromInstance(selected: SceneInstance, revisions: SceneRevision[]) {
    const selectedVariant = family.variants.find((item) => item.id === selected.variant_id);
    if (!selectedVariant) return;
    const state = selected.draft_state ?? {};
    const restoredLoads = state.load_cases as SceneLoadCase[] | undefined;
    const selectedGraph = graphFor(family, selectedVariant);
    setInstance(selected);
    setVariantId(selected.variant_id);
    setSceneTitle(selected.title);
    setMaterial((state.material_system as string | undefined) ?? selectedVariant.material_systems[0] ?? "");
    setParameters((state.geometry as Record<string, unknown> | undefined) ?? initialValues(family, selected.variant_id));
    setLoadCases(restoredLoads ? currentLoadCases(restoredLoads) : copiedLoadCases(family, selectedVariant, selectedGraph));
    setFoundationType(supportedFoundationType(selectedGraph, state.foundation_type as string | undefined));
    setGeotech((current) => ({
      ...current,
      bearingCapacity: (state.allowable_bearing_kpa as number | "" | undefined) ?? "",
      groundwaterCondition:
        (state.groundwater_condition as GroundwaterCondition | undefined) ?? (state.groundwater_known ? "no_influence" : "unknown"),
      waterTableDepth: (state.water_table_depth_m as number | "" | undefined) ?? "",
      groundwaterSource: (state.groundwater_source as string | undefined) ?? "",
      designStage: (state.design_stage as DesignStage | undefined) ?? "scheme_estimate",
    }));
    setConditions((current) => ({
      ...current,
      snowExposure: (state.snow_exposure as SnowExposure | undefined) ?? "exposed",
      snowExemptionReason: (state.snow_exemption_reason as string | undefined) ?? "",
      optionalWindEnabled: (state.optional_wind_enabled as boolean | undefined) ?? false,
    }));
    setMemberSpecifications((state.member_specifications as MemberSpecification[] | undefined) ?? []);
    setFoundationSpecifications(normalizedFoundations((state.foundation_specifications as FoundationDesignSpecification[] | undefined) ?? []));
    const savedExposure = state.surface_exposure as SceneStructuralProfile["exposure"] | undefined;
    if (savedExposure) {
      setExposure((current) => ({
        ...current,
        verticalEnclosure: savedExposure.vertical_enclosure,
        topCover: savedExposure.top_cover,
        verticalOpenRatio: savedExposure.vertical_open_ratio ?? "",
        topOpenRatio: savedExposure.top_open_ratio ?? "",
      }));
    }
    const latest = revisions[0] ?? null;
    setRevision(latest);
    setInputVersion(0);
    setCalculatedVersion(latest ? 0 : -1);
    captureFingerprint.current = Boolean(latest);
    if (!latest) calculatedFingerprint.current = null;
    setChangedNodeIds([]);
    setTab(state.workspace_tab === "results" && latest ? "results" : "settings");
  }

  async function loadProjectWorkspace(projectId: number, preferredInstanceId?: number) {
    const sequence = ++projectLoadSequence.current;
    try {
      const allInstances = await api<SceneInstance[]>(`/api/v2/projects/${projectId}/scene-instances`);
      const matching = allInstances.filter((item) => item.family_id === family.id);
      const histories = await Promise.all(
        matching.map(
          async (item) =>
            [item.id, await api<SceneRevision[]>(`/api/v2/projects/${projectId}/scene-revisions?scene_instance_id=${item.id}`)] as const,
        ),
      );
      if (sequence !== projectLoadSequence.current) return;
      const historyMap = Object.fromEntries(histories) as Record<number, SceneRevision[]>;
      setProjectInstances(matching);
      setInstanceRevisions(historyMap);
      const selected = matching.find((item) => item.id === preferredInstanceId) ?? matching[0];
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

  function markChanged(nodeIds: string[] = allNodeIds) {
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
    setGeotech((current) => ({ ...current, bearingCapacity: "", groundwaterCondition: "unknown", waterTableDepth: "", groundwaterSource: "" }));
    setInputVersion((current) => current + 1);
    setChangedNodeIds(nextGraph.nodes.map((node) => node.id));
    setError("");
  }

  function updateParameter(key: string, value: unknown) {
    setParameters((current) => ({ ...current, [key]: value }));
    markChanged();
  }

  function updateLoadCase(index: number, patch: Partial<SceneLoadCase>) {
    setLoadCases((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
    const loadNodeIds = visibleNodes.filter((node) => node.role === "load" || node.role === "surface").map((node) => node.id);
    markChanged(loadNodeIds.length ? loadNodeIds : allNodeIds);
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
    markChanged();
  }

  function existingProject() {
    return selectedProject === "new" ? null : projects.find((item) => item.id === selectedProject) ?? null;
  }

  // Each builder reports its own validation message; a null profile means
  // the user still has to complete that part of the settings.
  function withError<T>(result: { profile: T | null; error?: string }): T | null {
    if (result.error) setError(result.error);
    return result.profile;
  }

  function currentSiteProfile(): ProjectSiteProfile | null {
    return withError(
      buildSiteProfile({
        existing: existingProject()?.site_profile ?? null,
        conditions,
        factors,
        needs,
        selectedClimate,
        climateCatalog,
        seismicCatalog,
      }),
    );
  }

  function currentGeotechnicalProfile(): ProjectGeotechnicalProfile | null {
    if (!hasGenericFoundation) return existingProject()?.geotechnical_profile ?? null;
    return withError(buildGeotechnicalProfile(geotech));
  }

  function currentStructuralProfile(): SceneStructuralProfile | null {
    const nodeIds = (modules: string[], role?: string) =>
      new Set(
        visibleNodes
          .filter((node) => (!role || node.role === role) && modules.includes(node.calculation_module ?? ""))
          .map((node) => node.id),
      );
    return withError(
      buildStructuralProfile({
        steelNodeIds: nodeIds(STEEL_MEMBER_MODULES),
        foundationNodeIds: nodeIds(FOOTING_MODULES, "foundation"),
        memberSpecifications,
        foundationSpecifications,
        designStage: geotech.designStage,
        needsWind: needs.wind,
        exposure,
        roofForm: factors.roofForm,
        roofAssembly:
          conditionProfile.wind_semantics === "roof"
            ? roofAssemblies.find((item) => item.id === (exposure.topCover === "none" ? "none" : exposure.roofAssemblyId)) ?? null
            : null,
      }),
    );
  }

  function draftState() {
    const groundwater = hasGenericFoundation;
    return {
      workspace_tab: tab,
      material_system: material,
      geometry: parameters,
      load_package_id: variant?.load_package?.id,
      load_cases: loadCases,
      foundation_type: groundwater ? foundationType : null,
      allowable_bearing_kpa: groundwater ? geotech.bearingCapacity : null,
      groundwater_condition: groundwater ? geotech.groundwaterCondition : null,
      water_table_depth_m: groundwater && geotech.groundwaterCondition === "known_water_table" ? geotech.waterTableDepth : null,
      groundwater_source: groundwater ? geotech.groundwaterSource : null,
      snow_exposure: needs.snow ? conditions.snowExposure : null,
      snow_exemption_reason: needs.snow && conditions.snowExposure === "not_applicable" ? conditions.snowExemptionReason : null,
      optional_wind_enabled: conditionProfile.wind === "optional" ? conditions.optionalWindEnabled : null,
      design_stage: geotech.designStage,
      member_specifications: memberSpecifications,
      foundation_specifications: foundationSpecifications,
      surface_exposure: needs.wind ? { vertical_enclosure: exposure.verticalEnclosure, top_cover: exposure.topCover } : null,
      geometry_profile: null,
      structural_profile: currentStructuralProfile(),
    };
  }

  async function saveProjectProfile(projectId: number, path: "site-profile" | "geotechnical-profile", body: object) {
    const saved = await api<ProjectSiteProfile | ProjectGeotechnicalProfile>(`/api/v2/projects/${projectId}/${path}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const key = path === "site-profile" ? "site_profile" : "geotechnical_profile";
    onProjectsChange(projects.map((item) => (item.id === projectId ? { ...item, [key]: saved } : item)));
  }

  async function ensureProject(): Promise<number> {
    const profile = currentSiteProfile();
    const geotechnicalProfile = currentGeotechnicalProfile();
    if (hasConditions && !profile) throw new Error("项目条件尚未完成");
    if (hasGenericFoundation && !geotechnicalProfile) throw new Error("项目地勘条件尚未完成");
    if (selectedProject !== "new") {
      if (profile) await saveProjectProfile(selectedProject, "site-profile", profile);
      if (geotechnicalProfile) await saveProjectProfile(selectedProject, "geotechnical-profile", geotechnicalProfile);
      await specs.persistCustomSections(selectedProject);
      return selectedProject;
    }
    const created = await api<Project>("/api/v2/projects", {
      method: "POST",
      body: JSON.stringify({
        name: sceneTitle,
        description: family.description,
        ...(profile ? { site_profile: profile } : {}),
        ...(geotechnicalProfile ? { geotechnical_profile: geotechnicalProfile } : {}),
      }),
    });
    suppressNextProjectLoad.current = true;
    setSelectedProject(created.id);
    onProjectsChange([created, ...projects]);
    await specs.persistCustomSections(created.id);
    return created.id;
  }

  async function saveDraft(): Promise<SceneInstance> {
    const projectId = await ensureProject();
    if (instance && instance.project_id === projectId) {
      const updated = await api<SceneInstance>(`/api/v2/projects/${projectId}/scene-instances/${instance.id}`, {
        method: "PATCH",
        body: JSON.stringify({ variant_id: variantId, title: sceneTitle, mode: "quick", draft_state: draftState(), changed_node_ids: changedNodeIds }),
      });
      setInstance(updated);
      setProjectInstances((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      return updated;
    }
    const created = await api<SceneInstance>(`/api/v2/projects/${projectId}/scene-instances`, {
      method: "POST",
      body: JSON.stringify({ family_id: family.id, variant_id: variantId, title: sceneTitle, mode: "quick", draft_state: draftState() }),
    });
    setInstance(created);
    setProjectInstances((current) => [created, ...current]);
    return created;
  }

  async function runAction(action: () => Promise<void>) {
    setWorking(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      if (!isAbortError(caught)) setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  async function refreshProjects(signal?: AbortSignal) {
    onProjectsChange(await api<Project[]>("/api/v2/projects", { signal }));
  }

  function evaluateScene() {
    const validationError = validateLoadCases(loadCases);
    if (validationError) {
      setError(validationError);
      setTab("settings");
      return;
    }
    evaluation.current?.abort();
    const controller = new AbortController();
    evaluation.current = controller;
    const { signal } = controller;
    void runAction(async () => {
      const structuralProfile = currentStructuralProfile();
      if (!structuralProfile) throw new Error("构件与基础选型尚未完成");
      const saved = await saveDraft();
      const ctx: ScenePayloadContext = {
        graph,
        visibleNodes,
        loadCases,
        parameters,
        conditionProfile,
        topCover: exposure.topCover,
        memberSpecifications,
        foundationSpecifications,
        availableSections: specs.availableSections,
        bearingCapacity: geotech.bearingCapacity,
        sceneTitle,
      };
      const nodeCalculations = visibleNodes.flatMap((node) => {
        const calculationModule = node.calculation_module as Module | undefined;
        return calculationModule && calculationModule in MODULE_MAP ? [nodeCalculationPayload(node.id, calculationModule, ctx)] : [];
      });
      const calculated = await api<SceneRevision>(`/api/v2/projects/${saved.project_id}/scene-revisions`, {
        method: "POST",
        body: JSON.stringify({
          scene_instance_id: saved.id,
          node_calculations: nodeCalculations,
          load_cases: loadCases,
          structural_profile: structuralProfile,
        }),
        signal,
      });
      setRevision(calculated);
      setInstanceRevisions((current) => ({ ...current, [saved.id]: [calculated, ...(current[saved.id] ?? [])] }));
      setCalculatedVersion(inputVersion);
      calculatedFingerprint.current = designInputFingerprint;
      setChangedNodeIds([]);
      setTab("results");
      await refreshProjects(signal);
    });
  }

  function saveOnly() {
    void runAction(async () => {
      await saveDraft();
      await refreshProjects();
    });
  }

  function duplicateAlternative() {
    if (!instance || !revision || stale || selectedProject === "new") return;
    void runAction(async () => {
      const copied = await api<SceneInstance>(`/api/v2/projects/${selectedProject}/scene-instances/${instance.id}/duplicate`, { method: "POST" });
      await loadProjectWorkspace(selectedProject, copied.id);
      setTab("results");
    });
  }

  async function renameInstance(target: SceneInstance, title: string) {
    try {
      const updated = await api<SceneInstance>(`/api/v2/projects/${target.project_id}/scene-instances/${target.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      setProjectInstances((current) => current.map((item) => (item.id === updated.id ? updated : item)));
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
      await api<SceneInstance>(`/api/v2/projects/${target.project_id}/scene-instances/${target.id}`, {
        method: "PATCH",
        body: JSON.stringify({ archived: true }),
      });
      await loadProjectWorkspace(selectedProject, target.id === instance?.id ? undefined : instance?.id);
    } catch (caught) {
      setError(errorMessage(caught));
    }
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

  const nodeLabel = (nodeId: string) => visibleNodes.find((node) => node.id === nodeId)?.label;
  const settingsModel: SceneSettingsModel = {
    family,
    variant,
    variantId,
    selectVariant,
    material,
    setMaterial,
    sceneTitle,
    setSceneTitle,
    markChanged,
    visibleNodes,
    nodeLabel,
    visibleParameters,
    parameters,
    setParameters,
    updateParameter,
    specs,
    memberSpecifications,
    setMemberSpecifications,
    foundationSpecifications,
    setFoundationSpecifications,
    working,
    hasGenericFoundation,
    geotech,
    setGeotech,
    conditionProfile,
    hasConditions,
    needs,
    conditions,
    setConditions,
    exposure,
    setExposure,
    climateCatalog,
    seismicCatalog,
    selectedClimate,
    factors,
    climateInputsReady,
    roofAssemblies,
    loadCases,
    updateLoadCase,
    addCustomLoad,
    projects,
    selectedProject,
    setSelectedProject,
    projectInstances,
    instance,
    instanceRevisions,
    hydrateFromInstance,
  };

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
        <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
          <span>1</span> 设置
        </button>
        <button className={tab === "results" ? "active" : ""} onClick={() => setTab("results")}>
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
            <SceneSettingsView scene={settingsModel} />
          ) : (
            <SceneResultsView
              revision={revision}
              stale={stale}
              working={working}
              instance={instance}
              comparisonInstances={comparisonInstances}
              revisionsByInstance={instanceRevisions}
              onEditSettings={() => setTab("settings")}
              onDuplicate={duplicateAlternative}
              onRecalculate={evaluateScene}
              onSelectRevision={setRevision}
              onOpenInstance={(alternative) => hydrateFromInstance(alternative, instanceRevisions[alternative.id] ?? [])}
              onRenameInstance={renameInstance}
              onArchiveInstance={archiveInstance}
            />
          )}

          {error && (
            <div className="inline-error" role="alert">
              {error}
            </div>
          )}

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
            <div>
              <span className="eyebrow">LOAD PATH</span>
              <h2>当前传力链</h2>
            </div>
            <span>{visibleNodes.length}</span>
          </div>
          <LoadPath nodes={visibleNodes} revision={revision} stale={stale} />
          <div className="scene-boundaries">
            <strong>适用边界</strong>
            {family.boundaries.map((boundary) => (
              <span key={boundary}>• {boundary}</span>
            ))}
          </div>
          <div className="revision-note">
            <FileClock size={15} /> 输入修改后旧结果失效；重新计算生成新修订，不覆盖历史报告。
          </div>
        </aside>
      </div>

      <details className="mobile-load-path">
        <summary>
          查看传力链与节点状态 <ChevronDown size={16} />
        </summary>
        <LoadPath nodes={visibleNodes} revision={revision} stale={stale} compact />
      </details>
    </div>
  );
}

