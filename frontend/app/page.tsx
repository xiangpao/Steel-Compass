"use client";

import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Compass,
  Download,
  FileClock,
  FolderPlus,
  Gauge,
  LogOut,
  Menu,
  Plus,
  Save,
  ShieldCheck,
  UserPlus,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, errorMessage } from "@/lib/api";
import { SceneWorkspace } from "@/components/scene-workspace";
import { HelpTip } from "@/components/help-tip";
import {
  MODULE_MAP,
  NEXTGEN_LIBRARY_ITEMS,
  FIELD_HELP,
  normalizeInputs,
  type FieldDefinition,
} from "@/lib/modules";
import type {
  CalculationResult,
  CalculationLibrary,
  CalculationLibraryItem,
  ClimateCatalog,
  ClimateRegionCatalog,
  LoadCatalog,
  LoadItem,
  LoadPreset,
  MaterialCatalog,
  Mode,
  Module,
  Project,
  ProjectVersion,
  SceneFamily,
  SeismicDesignCatalog,
  User,
} from "@/lib/types";

const LOAD_LABELS: Record<LoadItem["kind"], string> = {
  self_weight: "自重",
  dead: "恒载",
  live: "活载",
  wind: "风荷载",
  snow: "雪荷载",
  seismic: "地震作用",
};

const CORE_SCENE_IDS = new Set([
  "pergola-pavilion",
  "canopy",
  "signage-billboard",
  "landscape-wall-fence",
  "entrance-frame",
  "boardwalk-platform",
]);

const CORE_CALCULATION_MODULES = new Set<Module>([
  "steel_beam",
  "steel_column",
  "concrete_beam",
  "concrete_slab",
  "timber_beam",
  "timber_column",
  "steel_baseplate_anchor",
  "timber_connection",
  "wall_anchor",
  "spread_footing",
  "strip_footing",
  "retaining_wall",
  "pool_structure",
]);

function copyLoads(loads: LoadItem[], mode: Mode = "quick"): LoadItem[] {
  return loads.map((item) => {
    const { confirmed: _legacyConfirmation, ...current } = item as LoadItem & {
      confirmed?: boolean;
    };
    void _legacyConfirmation;
    return {
      ...current,
      source:
        mode === "quick" ? current.source || "场景建议值" : current.source,
    };
  });
}

export default function WorkspacePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [mode] = useState<Mode>("quick");
  const [module, setModule] = useState<Module>("steel_beam");
  const [inputs, setInputs] = useState<Record<string, unknown>>({
    ...MODULE_MAP.steel_beam.defaults,
  });
  const [loads, setLoads] = useState<LoadItem[]>(
    copyLoads(MODULE_MAP.steel_beam.defaultLoads),
  );
  const [workspaceKind, setWorkspaceKind] = useState<
    "scene" | "calculation"
  >("scene");
  const [pendingWorkspaceKind, setPendingWorkspaceKind] = useState<
    "scene" | "calculation"
  >("scene");
  const [sceneFamilies, setSceneFamilies] = useState<SceneFamily[]>([]);
  const [selectedSceneFamilyId, setSelectedSceneFamilyId] = useState("");
  const [pendingSceneFamilyId, setPendingSceneFamilyId] = useState("");
  const [calculationLibrary, setCalculationLibrary] =
    useState<CalculationLibrary | null>(null);
  const [expandedTask, setExpandedTask] = useState("common:superstructure");
  const [materialFilter, setMaterialFilter] = useState<
    "" | "steel" | "concrete" | "timber"
  >("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | "new">("new");
  const [projectName, setProjectName] = useState("未命名结构方案");
  const [result, setResult] = useState<CalculationResult | null>(null);
  const [savedVersion, setSavedVersion] = useState<ProjectVersion | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [adminOpen, setAdminOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [moreScenesOpen, setMoreScenesOpen] = useState(false);
  const [moreCalculationsOpen, setMoreCalculationsOpen] = useState(false);
  const [pendingModule, setPendingModule] = useState<Module>("steel_beam");
  const drafts = useRef(
    new Map<
      string,
      {
        inputs: Record<string, unknown>;
        loads: LoadItem[];
        projectName: string;
      }
    >(),
  );
  const [materialCatalog, setMaterialCatalog] =
    useState<MaterialCatalog | null>(null);
  const [loadCatalog, setLoadCatalog] = useState<LoadCatalog | null>(null);
  const [climateCatalog, setClimateCatalog] =
    useState<ClimateCatalog | null>(null);
  const [siteClimateCatalog, setSiteClimateCatalog] =
    useState<ClimateRegionCatalog | null>(null);
  const [seismicCatalog, setSeismicCatalog] =
    useState<SeismicDesignCatalog | null>(null);
  const [loadPickerOpen, setLoadPickerOpen] = useState(false);
  const [climateOpen, setClimateOpen] = useState(false);
  const [climateLocationId, setClimateLocationId] = useState("");
  const [climateKind, setClimateKind] = useState<"wind" | "snow">("wind");
  const [recurrence, setRecurrence] = useState<"10" | "50" | "100">("50");
  const [heightFactor, setHeightFactor] = useState(1);
  const [shapeFactor, setShapeFactor] = useState(1);
  const [linkedSource, setLinkedSource] = useState<{
    calculation: Record<string, unknown>;
    result: CalculationResult;
  } | null>(null);
  const [savedRevision, setSavedRevision] = useState<{
    id: number;
    project_id: number;
    revision_number: number;
    report_number: string;
  } | null>(null);

  useEffect(() => {
    Promise.all([
      api<User>("/api/v1/auth/me"),
      api<SceneFamily[]>("/api/v2/scenario-families"),
      api<CalculationLibrary>("/api/v2/calculation-library"),
      api<Project[]>("/api/v2/projects"),
      api<MaterialCatalog>("/api/v2/catalogs/materials"),
      api<LoadCatalog>("/api/v2/catalogs/load-presets"),
      api<ClimateCatalog>("/api/v2/catalogs/climate-locations"),
      api<ClimateRegionCatalog>("/api/v2/catalogs/climate-regions"),
      api<SeismicDesignCatalog>("/api/v2/catalogs/seismic-design-profiles"),
    ])
      .then(
        ([
          currentUser,
          familyList,
          library,
          projectList,
          materials,
          loadPresets,
          climateLocations,
          climateRegions,
          seismicProfiles,
        ]) => {
        if (currentUser.must_change_password) {
          router.replace("/change-password");
          return;
        }
        setUser(currentUser);
        setSceneFamilies(familyList);
        setCalculationLibrary(library);
        setProjects(projectList);
        setMaterialCatalog(materials);
        setLoadCatalog(loadPresets);
        setClimateCatalog(climateLocations);
        setSiteClimateCatalog(climateRegions);
        setSeismicCatalog(seismicProfiles);
        setClimateLocationId(climateLocations.items[0]?.id ?? "");
        const first =
          familyList.find((item) => item.availability !== "development") ??
          familyList[0];
        if (first) {
          setSelectedSceneFamilyId(first.id);
          setPendingSceneFamilyId(first.id);
        }
      },
      )
      .catch((caught) => {
        // Only an authentication failure goes back to login; a failing catalog
        // must not bounce between "/" and "/login" forever.
        if (caught instanceof ApiError && caught.status === 401) {
          router.replace("/login");
          return;
        }
        setError(`工作台数据加载失败：${errorMessage(caught)}`);
      });
  }, [router]);

  const definition = MODULE_MAP[module];
  const visibleFields = definition.fields.filter(
    (field) => !field.visible || field.visible(inputs),
  );
  const basicFields = visibleFields.filter((field) => field.level !== "advanced");
  const advancedFields = visibleFields.filter((field) => field.level === "advanced");
  const calculationGroups = useMemo(() => {
    const order = [
      "loads_environment",
      "superstructure",
      "connections_supports",
      "foundations_geotechnical",
      "retaining_pool",
    ];
    const mergedItems = new Map(
      (calculationLibrary?.items ?? []).map((item) => [item.module ?? item.id, item]),
    );
    NEXTGEN_LIBRARY_ITEMS.forEach((item) => {
      const key = item.module ?? item.id;
      if (!mergedItems.has(key)) mergedItems.set(key, item);
    });
    const items = [...mergedItems.values()];
    const visibleItems = items.filter(
      (item) =>
        item.task !== "loads_environment" &&
        Boolean(item.module && item.module in MODULE_MAP) &&
        (!materialFilter || !item.material || item.material === materialFilter),
    );
    const groupsFor = (tier: "common" | "more") =>
      order
        .filter((task) => task !== "loads_environment")
        .map((task) => ({
          task,
          title:
            visibleItems.find((item) => item.task === task)?.task_title ?? task,
          items: visibleItems.filter((item) => {
            const isCommon = Boolean(
              item.module && CORE_CALCULATION_MODULES.has(item.module),
            );
            return item.task === task && (tier === "common" ? isCommon : !isCommon);
          }),
        }))
        .filter((group) => group.items.length > 0);
    return { common: groupsFor("common"), more: groupsFor("more") };
  }, [calculationLibrary, materialFilter]);

  useEffect(() => {
    if (!railOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPendingWorkspaceKind(workspaceKind);
        setPendingModule(module);
        setPendingSceneFamilyId(selectedSceneFamilyId);
        setRailOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [railOpen, module, selectedSceneFamilyId, workspaceKind]);

  function draftKey(nextMode: Mode, nextModule: Module) {
    return `${nextMode}:module:${nextModule}`;
  }

  function saveCurrentDraft() {
    drafts.current.set(draftKey(mode, module), {
      inputs: { ...inputs },
      loads: copyLoads(loads, mode),
      projectName,
    });
  }

  function selectModule(nextModule: Module) {
    setPendingModule(nextModule);
    if (window.matchMedia("(min-width: 1101px)").matches) {
      activateCalculation(nextModule);
    }
  }

  function activateCalculation(targetModule: Module) {
    saveCurrentDraft();
    const key = draftKey(mode, targetModule);
    const saved = drafts.current.get(key);
    const targetDefinition = MODULE_MAP[targetModule];
    setWorkspaceKind("calculation");
    setPendingWorkspaceKind("calculation");
    setModule(targetModule);
    setInputs(saved?.inputs ?? { ...targetDefinition.defaults });
    setLoads(saved?.loads ?? copyLoads(targetDefinition.defaultLoads, mode));
    setProjectName(saved?.projectName ?? projectName);
    setResult(null);
    setSavedVersion(null);
    setSavedRevision(null);
    setLinkedSource(null);
    setError("");
    setRailOpen(false);
  }

  function selectWorkspaceKind(nextKind: "scene" | "calculation") {
    setPendingWorkspaceKind(nextKind);
    if (!window.matchMedia("(min-width: 1101px)").matches) return;
    if (nextKind === "calculation") {
      activateCalculation(pendingModule);
      return;
    }
    const nextFamily =
      sceneFamilies.find((item) => item.id === pendingSceneFamilyId) ??
      sceneFamilies.find((item) => item.availability !== "development");
    if (!nextFamily || nextFamily.availability === "development") return;
    setWorkspaceKind("scene");
    setSelectedSceneFamilyId(nextFamily.id);
    setPendingSceneFamilyId(nextFamily.id);
    setError("");
  }

  function selectSceneFamily(family: SceneFamily) {
    if (family.availability === "development") return;
    setPendingSceneFamilyId(family.id);
    if (!window.matchMedia("(min-width: 1101px)").matches) return;
    setWorkspaceKind("scene");
    setPendingWorkspaceKind("scene");
    setSelectedSceneFamilyId(family.id);
    setError("");
  }

  function openNavigation() {
    setPendingWorkspaceKind(workspaceKind);
    setPendingModule(module);
    setPendingSceneFamilyId(selectedSceneFamilyId);
    setRailOpen(true);
  }

  function cancelNavigation() {
    setPendingWorkspaceKind(workspaceKind);
    setPendingModule(module);
    setPendingSceneFamilyId(selectedSceneFamilyId);
    setRailOpen(false);
  }

  function applyNavigation() {
    if (pendingWorkspaceKind === "scene") {
      const selected = sceneFamilies.find(
        (item) => item.id === pendingSceneFamilyId,
      );
      if (!selected || selected.availability === "development") return;
      setWorkspaceKind("scene");
      setSelectedSceneFamilyId(selected.id);
      setRailOpen(false);
      setError("");
      return;
    }
    activateCalculation(pendingModule);
  }

  // Any input edit invalidates the shown result so a saved version or a
  // derived foundation never pairs new inputs with old conclusions.
  function invalidateResult() {
    setResult(null);
    setSavedVersion(null);
    setSavedRevision(null);
  }

  function updateInput(key: string, value: unknown) {
    setInputs((current) => ({ ...current, [key]: value }));
    invalidateResult();
  }

  function fieldWithCatalog(field: FieldDefinition): FieldDefinition {
    const enriched = field.help || !FIELD_HELP[field.key] ? field : { ...field, help: FIELD_HELP[field.key] };
    if (
      !materialCatalog ||
      !["rebar_grade", "stirrup_grade"].includes(field.key)
    ) {
      return enriched;
    }
    const role = field.key === "stirrup_grade" ? "stirrup" : "longitudinal";
    return {
      ...enriched,
      options: materialCatalog.items
        .filter(
          (item) =>
            ["active", "restricted"].includes(item.status) &&
            item.roles.includes(role),
        )
        .map((item) => ({
          value: item.id,
          label: `${item.id}${item.status === "restricted" ? " · 受限" : ""}`,
        })),
    };
  }

  function updateLoad(index: number, patch: Partial<LoadItem>) {
    invalidateResult();
    setLoads((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    );
  }

  function addLoadPreset(preset: LoadPreset) {
    if (!["kN/m", "kN/m2", "kN"].includes(preset.unit)) {
      setError(
        `${preset.label} 是体积重度，需先按实际厚度或体积换算后再添加。`,
      );
      return;
    }
    invalidateResult();
    setLoads((current) => [
      ...current,
      {
        kind: preset.kind,
        value: preset.value,
        unit: preset.unit as LoadItem["unit"],
        source: preset.label,
        preset_id: preset.id,
        source_reference: preset.source_reference,
      },
    ]);
    setLoadPickerOpen(false);
    setError("");
  }

  function addClimateLoad() {
    const location = climateCatalog?.items.find(
      (item) => item.id === climateLocationId,
    );
    const basic =
      climateKind === "wind"
        ? location?.wind_kpa[recurrence]
        : location?.snow_kpa[recurrence];
    if (!location || basic == null) {
      setError("该站点没有所选风压或雪压数据，请改为项目人工输入。");
      return;
    }
    const calculated = basic * heightFactor * shapeFactor;
    invalidateResult();
    setLoads((current) => [
      ...current,
      {
        kind: climateKind,
        value: Number(calculated.toFixed(4)),
        unit: "kN/m2",
        source: `${location.province} ${location.station} · ${recurrence}年重现期`,
        preset_id: `climate:${location.id}:${climateKind}:${recurrence}`,
        source_reference: `GB 50009-2012 表E.5；基本值 ${basic} kN/m²；系数 ${heightFactor}×${shapeFactor}`,
      },
    ]);
    setClimateOpen(false);
    setError("");
  }

  function payload() {
    const typedInputs = definition.buildTypedInputs?.(inputs);
    return {
      schema_version: "3.3",
      mode,
      module,
      project_name: projectName,
      standard_profile: "CN-2026.6",
      ...(typedInputs
        ? { typed_inputs: typedInputs, loads: [] }
        : { inputs: normalizeInputs(module, inputs), loads }),
    };
  }

  async function calculate() {
    if (
      ["pool_structure", "gravity_retaining_wall"].includes(module) &&
      inputs.groundwater_condition === "unknown"
    ) {
      setError("地下水位未知时不能运行验算；请选择“无地下水影响”或录入已知水位及资料来源。");
      return;
    }
    if (
      ["pool_structure", "gravity_retaining_wall"].includes(module) &&
      inputs.groundwater_condition === "known_water_table" &&
      !String(inputs.groundwater_source ?? "").trim()
    ) {
      setError("已知地下水位必须填写资料来源。");
      return;
    }
    setWorking(true);
    setError("");
    setSavedVersion(null);
    setSavedRevision(null);
    try {
      const calculated = await api<CalculationResult>("/api/v2/calculate", {
        method: "POST",
        body: JSON.stringify(payload()),
      });
      setResult(calculated);
      requestAnimationFrame(() =>
        document
          .getElementById("result-panel")
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (caught) {
      setResult(null);
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  async function saveVersion() {
    if (!result) return;
    setWorking(true);
    setError("");
    try {
      let projectId = selectedProject;
      if (projectId === "new") {
        const created = await api<Project>("/api/v1/projects", {
          method: "POST",
          body: JSON.stringify({ name: projectName, description: "" }),
        });
        projectId = created.id;
        setSelectedProject(created.id);
        setProjects((current) => [created, ...current]);
      }
      if (linkedSource && module === "spread_footing") {
        const revision = await api<{
          id: number;
          project_id: number;
          revision_number: number;
          report_number: string;
        }>(`/api/v2/projects/${projectId}/revisions`, {
          method: "POST",
          body: JSON.stringify({
            calculations: [
              {
                node_id: "superstructure",
                label: "上部结构",
                calculation: linkedSource.calculation,
              },
              {
                node_id: "foundation",
                label: "柱下独立基础",
                calculation: payload(),
              },
            ],
            connections: [
              {
                source_node_id: "superstructure",
                target_node_id: "foundation",
                support:
                  ["portal_frame", "steel_beam"].includes(
                    linkedSource.result.module,
                  )
                    ? "left"
                    : "base",
              },
            ],
          }),
        });
        setSavedRevision(revision);
        setSavedVersion(null);
      } else {
        const version = await api<ProjectVersion>(
          `/api/v2/projects/${projectId}/versions`,
          {
            method: "POST",
            body: JSON.stringify({ calculation: payload() }),
          },
        );
        setSavedVersion(version);
        setSavedRevision(null);
      }
      const refreshed = await api<Project[]>("/api/v2/projects");
      setProjects(refreshed);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  function createFoundationFromResult(source: CalculationResult) {
    const reaction = (keys: string[]) => {
      for (const key of keys) {
        const quantity = source.reactions[key];
        if (quantity) return quantity.value;
      }
      return 0;
    };
    const vertical = reaction([
      "base_vertical",
      "left_vertical",
      "right_vertical",
    ]);
    if (vertical === 0) {
      setError("当前结果没有可传递给基础的竖向反力。");
      return;
    }
    saveCurrentDraft();
    setLinkedSource({
      calculation: payload(),
      result: source,
    });
    setWorkspaceKind("calculation");
    setPendingWorkspaceKind("calculation");
    setModule("spread_footing");
    setPendingModule("spread_footing");
    setInputs({
      ...MODULE_MAP.spread_footing.defaults,
      horizontal_x_kn: reaction([
        "base_horizontal",
        "left_horizontal",
        "right_horizontal",
      ]),
      moment_y_kn_m: reaction([
        "base_moment",
        "left_moment",
        "right_moment",
      ]),
      uplift_kn: vertical < 0 ? Math.abs(vertical) : 0,
      reaction_source_trace_id: source.trace_id,
    });
    setLoads([
      {
        kind: "dead",
        value: Math.max(vertical, 0),
        unit: "kN",
        source: `${source.project_name} · 上部结构反力`,
        source_reference: `trace:${source.trace_id}`,
      },
    ]);
    setProjectName(`${source.project_name} · 基础`);
    setResult(null);
    setSavedVersion(null);
    setSavedRevision(null);
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function logout() {
    try {
      await api<void>("/api/v1/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
    }
  }

  if (!user) {
    return (
      <main className="loading-screen" role={error ? "alert" : undefined}>
        <Compass className={error ? undefined : "spin-slow"} size={32} />
        <span>{error || "正在载入结构工作台…"}</span>
        {error && (
          <button type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
        )}
      </main>
    );
  }

  return (
    <div className="workspace-shell">
      <header className="topbar">
        <button
          className="mobile-nav-button"
          aria-label="打开导航"
          aria-expanded={railOpen}
          onClick={openNavigation}
        >
          <Menu size={20} />
        </button>
        <div className="brand-lockup dark">
          <span className="brand-mark">
            <Compass size={22} />
          </span>
          <span>STEEL—COMPASS</span>
          <span className="version-tag">V2 BETA</span>
        </div>
        <div className="topbar-meta">
          <span className="standard-pill">
            <ShieldCheck size={15} /> CN-2026.6 规范基线
          </span>
          <span className="user-name">{user.display_name}</span>
          {user.is_admin && (
            <button className="icon-button" onClick={() => setAdminOpen(true)}>
              <UserPlus size={18} />
              <span>邀请成员</span>
            </button>
          )}
          <button className="icon-button" onClick={logout} title="退出">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {railOpen && (
        <div
          className="mobile-rail-backdrop"
          aria-hidden="true"
          onClick={cancelNavigation}
        />
      )}

      <aside className={`left-rail ${railOpen ? "open" : ""}`}>
        <button
          className="rail-close"
          aria-label="关闭导航"
          onClick={cancelNavigation}
        >
          <X size={20} />
        </button>
        <div className="rail-section">
          <span className="rail-label">一级入口</span>
          <div className="mode-switch entry-switch">
            <button
              className={pendingWorkspaceKind === "scene" ? "active" : ""}
              onClick={() => selectWorkspaceKind("scene")}
            >
              <Compass size={17} />
              <span>完整场景</span>
            </button>
            <button
              className={
                pendingWorkspaceKind === "calculation" ? "active" : ""
              }
              onClick={() => selectWorkspaceKind("calculation")}
            >
              <Gauge size={17} />
              <span>单项计算</span>
            </button>
          </div>
        </div>

        {pendingWorkspaceKind === "scene" ? (
          <div className="rail-section scenario-list">
            <span className="rail-label">完整景观场景</span>
            {sceneFamilies.filter((family) => CORE_SCENE_IDS.has(family.id)).map((family) => (
              <button
                key={family.id}
                disabled={family.availability === "development"}
                className={
                  pendingSceneFamilyId === family.id ? "active" : ""
                }
                onClick={() => selectSceneFamily(family)}
              >
                <span>
                  {family.title}
                  <em className={`maturity-dot ${family.maturity}`} />
                </span>
                <small>
                  {family.availability === "development"
                    ? "开发中 · 暂不开放计算"
                    : family.description}
                </small>
              </button>
            ))}
            {!moreScenesOpen ? (
              <button
                className="library-group-toggle"
                aria-expanded={false}
                onClick={() => setMoreScenesOpen(true)}
              >
                <span>更多场景</span><ChevronDown size={15} />
              </button>
            ) : (
              <>
                {sceneFamilies.filter((family) => !CORE_SCENE_IDS.has(family.id)).map((family) => (
                  <button key={family.id} disabled={family.availability === "development"} className={pendingSceneFamilyId === family.id ? "active" : ""} onClick={() => selectSceneFamily(family)}>
                    <span>{family.title}<em className={`maturity-dot ${family.maturity}`} /></span>
                    <small>{family.availability === "development" ? "开发中 · 暂不开放计算" : family.description}</small>
                  </button>
                ))}
                <button
                  className="library-collapse-icon"
                  aria-label="收起更多场景"
                  title="收起更多场景"
                  onClick={() => setMoreScenesOpen(false)}
                >
                  <ChevronUp size={17} />
                </button>
              </>
            )}
          </div>
        ) : (
          <>
            <div className="rail-section material-filter">
              <span className="rail-label">材料筛选</span>
              <div>
                {[
                  ["", "全部"],
                  ["steel", "钢"],
                  ["concrete", "混凝土"],
                  ["timber", "木"],
                ].map(([value, label]) => (
                  <button
                    key={value || "all"}
                    className={materialFilter === value ? "active" : ""}
                    onClick={() =>
                      setMaterialFilter(
                        value as "" | "steel" | "concrete" | "timber",
                      )
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="rail-section calculation-library">
              <span className="rail-label">常用单项</span>
              <CalculationGroupList
                tier="common"
                groups={calculationGroups.common}
                expandedTask={expandedTask}
                onToggle={setExpandedTask}
                pendingModule={pendingModule}
                onSelect={selectModule}
              />
              {calculationGroups.more.length > 0 && (
                !moreCalculationsOpen ? (
                  <button
                    className="library-group-toggle"
                    aria-expanded={false}
                    onClick={() => setMoreCalculationsOpen(true)}
                  >
                    <span>更多单项</span><ChevronDown size={15} />
                  </button>
                ) : (
                  <>
                    <CalculationGroupList
                      tier="more"
                      groups={calculationGroups.more}
                      expandedTask={expandedTask}
                      onToggle={setExpandedTask}
                      pendingModule={pendingModule}
                      onSelect={selectModule}
                    />
                    <button
                      className="library-collapse-icon"
                      aria-label="收起更多单项"
                      title="收起更多单项"
                      onClick={() => setMoreCalculationsOpen(false)}
                    >
                      <ChevronUp size={17} />
                    </button>
                  </>
                )
              )}
            </div>
          </>
        )}
        <div className="rail-selection-summary">
          <small>待应用</small>
          <strong>
            {pendingWorkspaceKind === "scene"
              ? `完整场景 · ${
                  sceneFamilies.find(
                    (item) => item.id === pendingSceneFamilyId,
                  )?.title ?? "请选择"
                }`
              : `单项计算 · ${MODULE_MAP[pendingModule].title}`}
          </strong>
          <span>选择期间菜单保持打开，现有输入不会被重置。</span>
        </div>
        <div className="rail-actions">
          <button className="secondary-button" onClick={cancelNavigation}>
            取消
          </button>
          <button className="primary-button" onClick={applyNavigation}>
            应用并关闭
          </button>
        </div>
      </aside>

      {workspaceKind === "scene" &&
      sceneFamilies.find((item) => item.id === selectedSceneFamilyId) ? (
        <main className="workspace-main scene-main">
          <SceneWorkspace
            family={
              sceneFamilies.find(
                (item) => item.id === selectedSceneFamilyId,
              )!
            }
            projects={projects}
            onProjectsChange={setProjects}
            climateCatalog={siteClimateCatalog}
            seismicCatalog={seismicCatalog}
          />
        </main>
      ) : (
      <main className="workspace-main">
        <section className="workspace-intro">
          <div>
            <span className="eyebrow">SCENARIO SCREENING CALCULATION</span>
            <h1>{definition.title}</h1>
            <p>
              单项工具用于补充方案筛查；完整场景的风雪与地震条件请在统一项目条件向导中填写。
            </p>
          </div>
          <StructureSketch module={module} inputs={inputs} />
        </section>

        <div className="project-strip">
          <label className="project-title-input">
            <span>项目 / 方案名称</span>
            <input
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
            />
          </label>
          <label>
            <span>保存位置</span>
            <div className="select-wrap">
              <select
                value={selectedProject}
                onChange={(event) => {
                  const value =
                    event.target.value === "new"
                      ? "new"
                      : Number(event.target.value);
                  setSelectedProject(value);
                  const selected = projects.find(
                    (project) => project.id === value,
                  );
                  if (selected) setProjectName(selected.name);
                }}
              >
                <option value="new">新建项目</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name} · {project.version_count} 个版本
                  </option>
                ))}
              </select>
              <ChevronDown size={16} />
            </div>
          </label>
          <span className="version-note">
            <FileClock size={16} />
            重新计算将创建新版本，不覆盖历史
          </span>
        </div>
        {linkedSource && module === "spread_footing" && (
          <div className="reaction-link-banner">
            <ArrowRight size={18} />
            <span>
              <strong>已连接上部结构反力</strong>
              <small>
                来源 {linkedSource.result.project_name} · Trace{" "}
                {linkedSource.result.trace_id}
              </small>
            </span>
          </div>
        )}

        <div className={definition.buildTypedInputs ? "input-layout typed-input-layout" : "input-layout"}>
          <section className="panel input-panel">
            <PanelHeader
              number="01"
              title="结构与材料"
              subtitle="Geometry & material"
            />
            <div className="field-grid">
              {basicFields.map((field) => (
                  <InputField
                    key={field.key}
                    field={fieldWithCatalog(field)}
                    value={inputs[field.key]}
                    onChange={(value) => updateInput(field.key, value)}
                  />
                ))}
            </div>
            {advancedFields.length > 0 && (
              <details className="advanced-fields">
                <summary>高级参数</summary>
                <p>默认采用当前目录或模块默认值；仅在已有明确依据时修改。</p>
                <div className="field-grid">
                  {advancedFields.map((field) => (
                    <InputField
                      key={field.key}
                      field={fieldWithCatalog(field)}
                      value={inputs[field.key]}
                      onChange={(value) => updateInput(field.key, value)}
                    />
                  ))}
                </div>
              </details>
            )}
          </section>

          {!definition.buildTypedInputs && (
          <section className="panel load-panel">
            <PanelHeader
              number="02"
              title="荷载与来源"
              subtitle="Load cases & provenance"
            />
            <div className="load-tools">
              <button
                className="secondary-button"
                onClick={() => setLoadPickerOpen((current) => !current)}
              >
                <Plus size={16} /> 常用荷载库
              </button>
              <button
                className="secondary-button"
                onClick={() => setClimateOpen((current) => !current)}
              >
                <Compass size={16} /> 城市风雪向导
              </button>
              <small>
                目录 {loadCatalog?.version ?? "加载中"} · 采用值直接进入计算
              </small>
            </div>
            {loadPickerOpen && loadCatalog && (
              <div className="catalog-picker">
                {loadCatalog.items.map((preset) => (
                  <button key={preset.id} onClick={() => addLoadPreset(preset)}>
                    <span>
                      <strong>{preset.label}</strong>
                      <small>{preset.source_reference}</small>
                    </span>
                    <b>
                      {preset.value}
                      {preset.value_max ? `–${preset.value_max}` : ""}{" "}
                      {preset.unit}
                    </b>
                    <p>{preset.notes}</p>
                  </button>
                ))}
              </div>
            )}
            {climateOpen && climateCatalog && (
              <div className="climate-wizard">
                <header>
                  <strong>城市风雪荷载向导</strong>
                  <small>
                    当前为已复核首批站点；未列地点禁止自动借用邻近城市。
                  </small>
                </header>
                <label>
                  <span>气象站</span>
                  <select
                    value={climateLocationId}
                    onChange={(event) =>
                      setClimateLocationId(event.target.value)
                    }
                  >
                    {climateCatalog.items.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.province} · {location.station}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>作用</span>
                  <select
                    value={climateKind}
                    onChange={(event) =>
                      setClimateKind(event.target.value as "wind" | "snow")
                    }
                  >
                    <option value="wind">风荷载</option>
                    <option value="snow">雪荷载</option>
                  </select>
                </label>
                <label>
                  <span>重现期</span>
                  <select
                    value={recurrence}
                    onChange={(event) =>
                      setRecurrence(
                        event.target.value as "10" | "50" | "100",
                      )
                    }
                  >
                    <option value="10">10 年</option>
                    <option value="50">50 年</option>
                    <option value="100">100 年</option>
                  </select>
                </label>
                <label>
                  <span>
                    {climateKind === "wind"
                      ? "高度/地面粗糙度系数"
                      : "积雪分布系数"}
                  </span>
                  <input
                    type="number"
                    min={0}
                    step="0.05"
                    value={heightFactor}
                    onChange={(event) =>
                      setHeightFactor(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  <span>
                    {climateKind === "wind" ? "体型系数" : "屋面积雪系数"}
                  </span>
                  <input
                    type="number"
                    step="0.05"
                    value={shapeFactor}
                    onChange={(event) =>
                      setShapeFactor(Number(event.target.value))
                    }
                  />
                </label>
                <button className="primary-button" onClick={addClimateLoad}>
                  计算并添加
                </button>
              </div>
            )}
            <div className="load-table">
              <div className="load-row load-head">
                <span>类型</span>
                <span>数值</span>
                <span>单位</span>
                <span>来源</span>
                <span />
              </div>
              {loads.map((load, index) => (
                <div className="load-entry" key={`${load.kind}-${index}`}>
                <div className="load-row">
                  <select
                    value={load.kind}
                    onChange={(event) =>
                      updateLoad(index, {
                        kind: event.target.value as LoadItem["kind"],
                      })
                    }
                  >
                    {Object.entries(LOAD_LABELS).map(([value, label]) => (
                      <option value={value} key={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={load.value}
                    onChange={(event) =>
                      updateLoad(index, {
                        value: Number(event.target.value),
                      })
                    }
                  />
                  <select
                    value={load.unit}
                    onChange={(event) =>
                      updateLoad(index, {
                        unit: event.target.value as LoadItem["unit"],
                      })
                    }
                  >
                    <option value="kN/m">kN/m</option>
                    <option value="kN/m2">kN/m²</option>
                    <option value="kN">kN</option>
                  </select>
                  <input
                    value={load.source}
                    placeholder={
                      mode === "professional"
                        ? "图纸、规范或计算依据"
                        : "场景建议值"
                    }
                    onChange={(event) =>
                      updateLoad(index, { source: event.target.value })
                    }
                  />
                  <button
                    className="remove-button"
                    onClick={() => {
                      invalidateResult();
                      setLoads((current) =>
                        current.filter((_, itemIndex) => itemIndex !== index),
                      );
                    }}
                    title="删除荷载"
                  >
                    <X size={15} />
                  </button>
                </div>
                {(load.source_reference || load.preset_id) && (
                  <div className="load-provenance">
                    <span>{load.source_reference}</span>
                    {load.preset_id &&
                      loadCatalog?.items.some(
                        (preset) =>
                          preset.id === load.preset_id && preset.value !== load.value,
                      ) && (
                      <input
                        value={load.override_reason ?? ""}
                        placeholder="已修改目录建议值，请填写覆盖原因"
                        onChange={(event) =>
                          updateLoad(index, {
                            override_reason: event.target.value,
                          })
                        }
                      />
                    )}
                  </div>
                )}
                </div>
              ))}
            </div>
            <button
              className="text-button"
              onClick={() => {
                invalidateResult();
                setLoads((current) => [
                  ...current,
                  { kind: "live", value: 0, unit: "kN/m", source: "" },
                ]);
              }}
            >
              <Plus size={16} /> 添加荷载工况
            </button>
          </section>
          )}
        </div>

        {error && (
          <div className="error-banner">
            <AlertTriangle size={20} />
            <span>{error}</span>
          </div>
        )}

        <div className="action-bar">
          <span>
            计算引擎与 PDF 共用同一结果对象
            <small>任何输入异常都会阻止生成通过结论</small>
          </span>
          <button
            className="calculate-button"
            onClick={calculate}
            disabled={working}
          >
            {working ? "正在计算…" : "运行验算"}
            <ArrowRight size={19} />
          </button>
        </div>

        {result && (
          <ResultPanel
            result={result}
            onSave={saveVersion}
            saving={working}
            savedVersion={savedVersion}
            savedRevision={savedRevision}
            onCreateFoundation={
              !["spread_footing", "strip_footing"].includes(module) &&
              Object.keys(result.reactions).length > 0
                ? () => createFoundationFromResult(result)
                : undefined
            }
            projectId={
              selectedProject === "new" ? undefined : selectedProject
            }
          />
        )}
      </main>
      )}

      {adminOpen && (
        <InviteDialog onClose={() => setAdminOpen(false)} />
      )}
    </div>
  );
}

function PanelHeader({
  number,
  title,
  subtitle,
}: {
  number: string;
  title: string;
  subtitle: string;
}) {
  return (
    <header className="panel-header">
      <span>{number}</span>
      <div>
        <h2>{title}</h2>
        <small>{subtitle}</small>
      </div>
    </header>
  );
}

function CalculationGroupList({
  tier,
  groups,
  expandedTask,
  onToggle,
  pendingModule,
  onSelect,
}: {
  tier: "common" | "more";
  groups: Array<{ task: string; title: string; items: CalculationLibraryItem[] }>;
  expandedTask: string;
  onToggle: (next: string | ((current: string) => string)) => void;
  pendingModule: Module;
  onSelect: (module: Module) => void;
}) {
  return groups.map((group) => {
    const taskKey = `${tier}:${group.task}`;
    return (
      <div className="library-group" key={taskKey}>
        <button
          className="library-group-toggle"
          aria-expanded={expandedTask === taskKey}
          onClick={() =>
            onToggle((current) => current === taskKey ? "" : taskKey)
          }
        >
          <span>{group.title}</span>
          <ChevronDown size={15} />
        </button>
        {expandedTask === taskKey && (
          <div className="library-items">
            {group.items.map((item) => {
              const available = Boolean(item.module && item.module in MODULE_MAP);
              const moduleDefinition = available ? MODULE_MAP[item.module!] : null;
              return (
                <button
                  key={item.id}
                  disabled={!available}
                  className={moduleDefinition?.id === pendingModule ? "active" : ""}
                  onClick={() => moduleDefinition && onSelect(moduleDefinition.id)}
                >
                  <span className={`module-code ${moduleDefinition?.material ?? "planned"}`}>
                    {moduleDefinition?.short ?? "·"}
                  </span>
                  <span>
                    <strong>{item.title}</strong>
                    <small>{available ? item.description : "计划开发"}</small>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  });
}

function InputField({
  field,
  value,
  onChange,
}: {
  field: FieldDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  if (field.type === "boolean") {
    return (
      <label className="toggle-field">
        <span>{field.label}{field.help && <HelpTip term={field.label} {...field.help} />}</span>
        <button
          type="button"
          className={value ? "toggle active" : "toggle"}
          onClick={() => onChange(!value)}
          aria-pressed={Boolean(value)}
        >
          <span />
        </button>
      </label>
    );
  }
  return (
    <label className="input-field">
      <span>{field.label}{field.help && <HelpTip term={field.label} {...field.help} />}</span>
      <div className="input-with-unit">
        {field.type === "select" ? (
          <select
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
          >
            {field.options?.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : field.type === "text" ? (
          <input
            type="text"
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
          />
        ) : (
          <input
            type="number"
            min={field.min}
            step={field.step ?? "any"}
            value={typeof value === "number" ? value : ""}
            onChange={(event) => onChange(Number(event.target.value))}
          />
        )}
        {field.unit && <small>{field.unit}</small>}
      </div>
    </label>
  );
}

function StructureSketch({
  module,
  inputs,
}: {
  module: Module;
  inputs: Record<string, unknown>;
}) {
  const span = Number(inputs.span_m ?? 3);
  const height = Number(inputs.height_m ?? 3);
  const isColumn = module.endsWith("column");
  const isFrame = ["portal_frame", "planar_frame"].includes(module);
  const isFoundation = module.endsWith("footing");
  return (
    <div className="structure-sketch" aria-label="结构模型示意">
      <svg viewBox="0 0 280 130" role="img">
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="5"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>
        {isFoundation ? (
          <>
            <path className="member" d="M124 18 L156 18 L156 62 L228 92 L52 92 L124 62 Z" />
            <path className="support-line" d="M35 94 L245 94" />
            {[55, 90, 125, 160, 195, 230].map((x) => (
              <path
                className="load-arrow"
                d={`M${x} 112 L${x} 99`}
                key={x}
                markerEnd="url(#arrow)"
              />
            ))}
            <text x="140" y="126">基底压力示意</text>
          </>
        ) : isFrame ? (
          <>
            <path className="member" d="M45 108 L45 32 L235 32 L235 108" />
            {[70, 105, 140, 175, 210].map((x) => (
              <path
                className="load-arrow"
                d={`M${x} 8 L${x} 25`}
                key={x}
                markerEnd="url(#arrow)"
              />
            ))}
            <path className="dimension" d="M45 120 L235 120" />
            <text x="140" y="128">
              L = {span} m
            </text>
            <text x="11" y="72" transform="rotate(-90 11 72)">
              H = {height} m
            </text>
          </>
        ) : isColumn ? (
          <>
            <path className="member" d="M140 18 L140 104" />
            <path
              className="load-arrow"
              d="M140 2 L140 14"
              markerEnd="url(#arrow)"
            />
            <path className="support-line" d="M112 106 L168 106" />
            <text x="154" y="62">
              H = {height} m
            </text>
          </>
        ) : (
          <>
            <path className="member" d="M35 76 L245 76" />
            {[55, 90, 125, 160, 195, 230].map((x) => (
              <path
                className="load-arrow"
                d={`M${x} 38 L${x} 67`}
                key={x}
                markerEnd="url(#arrow)"
              />
            ))}
            <path className="support" d="M35 80 L25 100 L45 100 Z" />
            <path className="support" d="M245 80 L235 100 L255 100 Z" />
            <path className="dimension" d="M35 116 L245 116" />
            <text x="140" y="126">
              L = {span} m
            </text>
          </>
        )}
      </svg>
      <span>结构模型示意 · 非施工图</span>
    </div>
  );
}

function ResultPanel({
  result,
  onSave,
  saving,
  savedVersion,
  savedRevision,
  onCreateFoundation,
  projectId,
}: {
  result: CalculationResult;
  onSave: () => void;
  saving: boolean;
  savedVersion: ProjectVersion | null;
  savedRevision: {
    id: number;
    project_id: number;
    revision_number: number;
    report_number: string;
  } | null;
  onCreateFoundation?: () => void;
  projectId?: number;
}) {
  const displayedStatus =
    result.mode === "professional" &&
    result.verification_status !== "independently_verified"
      ? "incomplete"
      : result.mode === "professional" && result.engineering_status
        ? result.engineering_status
        : result.status;
  const governing = result.checks.find(
    (item) => item.name === result.governing_check,
  );
  const sortedChecks = useMemo(
    () => [...result.checks].sort((a, b) => b.utilization - a.utilization),
    [result.checks],
  );
  const finalProjectId =
    savedRevision?.project_id ?? savedVersion?.project_id ?? projectId;
  const [resultView, setResultView] = useState<"overview" | "details">(
    "overview",
  );
  return (
    <section className="result-section" id="result-panel">
      <header className="result-header">
        <div
          className={`result-status ${
            displayedStatus === "passed"
              ? "passed"
              : displayedStatus === "incomplete"
                ? "incomplete"
                : "failed"
          }`}
        >
          {displayedStatus === "passed" ? (
            <Check size={24} />
          ) : displayedStatus === "incomplete" ? (
            <AlertTriangle size={24} />
          ) : (
            <X size={24} />
          )}
          <span>
            <small>
              控制结论 ·{" "}
              {result.mode === "quick" ? "方案筛查" : "专业校核"}
              {result.verification_status === "independently_verified" ? "" : " · 未独立验证"}
            </small>
            <strong>
              当前输入与适用范围内
              {displayedStatus === "passed"
                ? result.mode === "quick" ? "筛查通过" : "通过"
                : displayedStatus === "incomplete"
                  ? "资料不完整"
                  : result.mode === "quick" ? "筛查不通过" : "不通过"}
            </strong>
          </span>
        </div>
        <div className="result-summary">
          <span>
            <small>控制验算</small>
            <strong>{result.governing_check}</strong>
          </span>
          <span>
            <small>最大利用率</small>
            <strong>{((governing?.utilization ?? 0) * 100).toFixed(1)}%</strong>
          </span>
          <span>
            <small>引擎版本</small>
            <strong>{result.engine_version}</strong>
          </span>
        </div>
        <div className="report-actions">
          {onCreateFoundation && (
            <button className="secondary-button" onClick={onCreateFoundation}>
              <ArrowRight size={17} />
              用反力创建独立基础
            </button>
          )}
          <button className="secondary-button" onClick={onSave} disabled={saving}>
            <Save size={17} />
            {savedRevision
              ? `已保存 R${savedRevision.revision_number}`
              : savedVersion
                ? `已保存 V${savedVersion.version_number}`
                : "保存版本"}
          </button>
          {savedRevision && finalProjectId ? (
            <a
              className="primary-button compact"
              href={`/api/v2/projects/${finalProjectId}/revisions/${savedRevision.id}/report.pdf`}
            >
              <Download size={17} /> 项目链 PDF
            </a>
          ) : savedVersion && finalProjectId ? (
            <a
              className="primary-button compact"
              href={`/api/v2/projects/${finalProjectId}/versions/${savedVersion.id}/report.pdf`}
            >
              <Download size={17} /> PDF 报告
            </a>
          ) : null}
        </div>
      </header>
      <div className="result-tabs" role="tablist" aria-label="结果显示层级">
        <button
          className={resultView === "overview" ? "active" : ""}
          onClick={() => setResultView("overview")}
        >
          速览
        </button>
        <button
          className={resultView === "details" ? "active" : ""}
          onClick={() => setResultView("details")}
        >
          详细计算
        </button>
      </div>

      <div className="result-grid">
        <section className="panel checks-panel">
          <PanelHeader
            number="03"
            title="验算结果"
            subtitle="Checks ranked by utilization"
          />
          <div className="check-list">
            {sortedChecks.map((check) => (
              <article className="check-item" key={check.name}>
                <div className="check-title">
                  <span className={check.passed ? "check-ok" : "check-fail"}>
                    {check.passed ? <Check size={15} /> : <X size={15} />}
                  </span>
                  <strong>{check.name}</strong>
                  <span>{(check.utilization * 100).toFixed(1)}%</span>
                </div>
                <div className="utilization-track">
                  <span
                    style={{
                      width: `${Math.min(check.utilization * 100, 100)}%`,
                    }}
                    className={check.passed ? "" : "over"}
                  />
                </div>
                <div className="check-values">
                  <span>
                    需求 {check.demand.value.toFixed(3)} {check.demand.unit}
                  </span>
                  <span>
                    能力/限值 {check.capacity.value.toFixed(3)}{" "}
                    {check.capacity.unit}
                  </span>
                </div>
                <small>{check.reference}</small>
                {check.note && <p>{check.note}</p>}
              </article>
            ))}
          </div>
        </section>

        {resultView === "details" ? (
        <section className="panel transparent-panel">
          <PanelHeader
            number="04"
            title="过程与图形"
            subtitle="Transparent calculation"
          />
          {result.diagrams.length > 0 ? (
            <DiagramChart series={result.diagrams[0]} />
          ) : (
            <div className="no-diagram">
              <Gauge size={30} />
              <span>该模块当前以验算步骤为主</span>
            </div>
          )}
          <div className="step-list">
            {result.steps.map((step, index) => (
              <details key={`${step.name}-${index}`} open={index === 0}>
                <summary>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{step.name}</strong>
                  <small>
                    {step.result.value.toFixed(4)} {step.result.unit}
                  </small>
                </summary>
                <div>
                  <code>{step.equation}</code>
                  <p>{step.substitution}</p>
                  <small>{step.reference}</small>
                </div>
              </details>
            ))}
          </div>
        </section>
        ) : (
          <section className="panel transparent-panel overview-panel">
            <PanelHeader
              number="04"
              title="控制信息"
              subtitle="At-a-glance"
            />
            {result.diagrams.length > 0 ? (
              <DiagramChart series={result.diagrams[0]} />
            ) : (
              <div className="no-diagram">
                <Gauge size={30} />
                <span>切换“详细计算”查看公式与条文</span>
              </div>
            )}
            <div className="scope-summary">
              <strong>适用范围</strong>
              {result.applicability.map((item) => (
                <span key={item}>{item}</span>
              ))}
              {result.catalog_versions &&
                Object.entries(result.catalog_versions).map(([key, value]) => (
                  <small key={key}>
                    {key} · {value}
                  </small>
                ))}
            </div>
          </section>
        )}
      </div>

      {resultView === "details" && <div className="combination-strip">
        {result.combinations.map((combination) => (
          <article key={combination.name}>
            <span>{combination.limit_state}</span>
            <strong>{combination.name}</strong>
            <small>
              {combination.total.value.toFixed(3)} {combination.total.unit}
            </small>
          </article>
        ))}
      </div>}

      {result.warnings.length > 0 && (
        <div className="warning-list">
          {result.warnings.map((warning) => (
            <div className={`warning ${warning.severity}`} key={warning.code}>
              <AlertTriangle size={17} />
              <span>{warning.message}</span>
            </div>
          ))}
        </div>
      )}

      <footer className="result-footer">
        <small>Trace ID · {result.trace_id}</small>
      </footer>
    </section>
  );
}

function DiagramChart({ series }: { series: CalculationResult["diagrams"][0] }) {
  const width = 520;
  const height = 190;
  const padding = 30;
  const xs = series.points.map((point) => point.x.value);
  const ys = series.points.map((point) => point.value.value);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const maxAbsY = Math.max(...ys.map(Math.abs), 1e-9);
  const points = series.points
    .map((point) => {
      const x =
        padding +
        ((point.x.value - minX) / Math.max(maxX - minX, 1e-9)) *
          (width - 2 * padding);
      const y =
        height / 2 -
        (point.value.value / maxAbsY) * (height / 2 - padding);
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className="diagram-chart">
      <div>
        <strong>{series.name}</strong>
        <small>{series.points[0]?.value.unit}</small>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`}>
        <line
          x1={padding}
          y1={height / 2}
          x2={width - padding}
          y2={height / 2}
        />
        <polyline points={points} />
        {series.points.map((point, index) => {
          const [x, y] = points.split(" ")[index].split(",").map(Number);
          return <circle cx={x} cy={y} r="3" key={index} />;
        })}
      </svg>
    </div>
  );
}

function InviteDialog({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api<User>("/api/v1/auth/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          display_name: displayName,
          temporary_password: password,
          is_admin: false,
        }),
      });
      setMessage(`已创建 ${displayName}，首次登录必须修改密码。`);
      setUsername("");
      setDisplayName("");
      setPassword("");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <form
        className="modal-card"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">INVITED TEAM ONLY</span>
            <h2>邀请团队成员</h2>
          </div>
          <button type="button" className="remove-button" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <label>
          用户名
          <input
            value={username}
            pattern="[A-Za-z0-9_.-]+"
            minLength={3}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </label>
        <label>
          显示名称
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
          />
        </label>
        <label>
          临时密码
          <input
            type="password"
            minLength={10}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && <div className="inline-error">{error}</div>}
        {message && <div className="inline-success">{message}</div>}
        <button className="primary-button">
          <FolderPlus size={17} /> 创建受邀账号
        </button>
      </form>
    </div>
  );
}
