"use client";

import { AlertTriangle, ArrowRight, ChevronDown, Compass, FileClock, LogOut, Menu, ShieldCheck, UserPlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, errorMessage } from "@/lib/api";
import { SceneWorkspace } from "@/components/scene-workspace";
import { CalculationLoadsPanel } from "@/components/workspace/calculation-loads-panel";
import { InputField } from "@/components/workspace/input-field";
import { InviteDialog } from "@/components/workspace/invite-dialog";
import { NavigationRail, type WorkspaceKind } from "@/components/workspace/navigation-rail";
import { PanelHeader } from "@/components/workspace/panel-header";
import { ResultPanel, type SavedRevision } from "@/components/workspace/result-panel";
import { StructureSketch } from "@/components/workspace/structure-sketch";
import { MODULE_MAP, FIELD_HELP, normalizeInputs, type FieldDefinition } from "@/lib/modules";
import type {
  CalculationResult,
  CalculationLibrary,
  ClimateCatalog,
  ClimateRegionCatalog,
  LoadCatalog,
  LoadItem,
  MaterialCatalog,
  Module,
  Project,
  ProjectVersion,
  SceneFamily,
  SeismicDesignCatalog,
  User,
} from "@/lib/types";

// The single-calculation workspace only runs screening ("quick") checks.
const MODE = "quick";
const DESKTOP_QUERY = "(min-width: 1101px)";

function copyLoads(loads: LoadItem[]): LoadItem[] {
  return loads.map((item) => {
    const { confirmed: _legacyConfirmation, ...current } = item as LoadItem & { confirmed?: boolean };
    void _legacyConfirmation;
    return { ...current, source: current.source || "场景建议值" };
  });
}

function isDesktop() {
  return window.matchMedia(DESKTOP_QUERY).matches;
}

type Draft = { inputs: Record<string, unknown>; loads: LoadItem[]; projectName: string };

export default function WorkspacePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [module, setModule] = useState<Module>("steel_beam");
  const [inputs, setInputs] = useState<Record<string, unknown>>({ ...MODULE_MAP.steel_beam.defaults });
  const [loads, setLoads] = useState<LoadItem[]>(copyLoads(MODULE_MAP.steel_beam.defaultLoads));
  const [workspaceKind, setWorkspaceKind] = useState<WorkspaceKind>("scene");
  const [pendingWorkspaceKind, setPendingWorkspaceKind] = useState<WorkspaceKind>("scene");
  const [sceneFamilies, setSceneFamilies] = useState<SceneFamily[]>([]);
  const [selectedSceneFamilyId, setSelectedSceneFamilyId] = useState("");
  const [pendingSceneFamilyId, setPendingSceneFamilyId] = useState("");
  const [calculationLibrary, setCalculationLibrary] = useState<CalculationLibrary | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | "new">("new");
  const [projectName, setProjectName] = useState("未命名结构方案");
  const [result, setResult] = useState<CalculationResult | null>(null);
  const [savedVersion, setSavedVersion] = useState<ProjectVersion | null>(null);
  const [savedRevision, setSavedRevision] = useState<SavedRevision | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [adminOpen, setAdminOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [pendingModule, setPendingModule] = useState<Module>("steel_beam");
  const drafts = useRef(new Map<Module, Draft>());
  const [materialCatalog, setMaterialCatalog] = useState<MaterialCatalog | null>(null);
  const [loadCatalog, setLoadCatalog] = useState<LoadCatalog | null>(null);
  const [climateCatalog, setClimateCatalog] = useState<ClimateCatalog | null>(null);
  const [siteClimateCatalog, setSiteClimateCatalog] = useState<ClimateRegionCatalog | null>(null);
  const [seismicCatalog, setSeismicCatalog] = useState<SeismicDesignCatalog | null>(null);
  const [linkedSource, setLinkedSource] = useState<{
    calculation: Record<string, unknown>;
    result: CalculationResult;
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
      .then(([currentUser, familyList, library, projectList, materials, loadPresets, climateLocations, climateRegions, seismicProfiles]) => {
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
        const first = familyList.find((item) => item.availability !== "development") ?? familyList[0];
        if (first) {
          setSelectedSceneFamilyId(first.id);
          setPendingSceneFamilyId(first.id);
        }
      })
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
  const visibleFields = definition.fields.filter((field) => !field.visible || field.visible(inputs));
  const basicFields = visibleFields.filter((field) => field.level !== "advanced");
  const advancedFields = visibleFields.filter((field) => field.level === "advanced");
  const selectedSceneFamily = sceneFamilies.find((item) => item.id === selectedSceneFamilyId);

  function resetPendingNavigation() {
    setPendingWorkspaceKind(workspaceKind);
    setPendingModule(module);
    setPendingSceneFamilyId(selectedSceneFamilyId);
  }

  function cancelNavigation() {
    resetPendingNavigation();
    setRailOpen(false);
  }

  useEffect(() => {
    if (!railOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setPendingWorkspaceKind(workspaceKind);
      setPendingModule(module);
      setPendingSceneFamilyId(selectedSceneFamilyId);
      setRailOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [railOpen, module, selectedSceneFamilyId, workspaceKind]);

  function saveCurrentDraft() {
    drafts.current.set(module, { inputs: { ...inputs }, loads: copyLoads(loads), projectName });
  }

  // Any input edit invalidates the shown result so a saved version or a
  // derived foundation never pairs new inputs with old conclusions.
  function invalidateResult() {
    setResult(null);
    setSavedVersion(null);
    setSavedRevision(null);
  }

  function activateCalculation(targetModule: Module) {
    saveCurrentDraft();
    const saved = drafts.current.get(targetModule);
    const targetDefinition = MODULE_MAP[targetModule];
    setWorkspaceKind("calculation");
    setPendingWorkspaceKind("calculation");
    setModule(targetModule);
    setInputs(saved?.inputs ?? { ...targetDefinition.defaults });
    setLoads(saved?.loads ?? copyLoads(targetDefinition.defaultLoads));
    setProjectName(saved?.projectName ?? projectName);
    invalidateResult();
    setLinkedSource(null);
    setError("");
    setRailOpen(false);
  }

  function activateScene(family: SceneFamily) {
    setWorkspaceKind("scene");
    setPendingWorkspaceKind("scene");
    setSelectedSceneFamilyId(family.id);
    setPendingSceneFamilyId(family.id);
    setError("");
  }

  function selectModule(nextModule: Module) {
    setPendingModule(nextModule);
    if (isDesktop()) activateCalculation(nextModule);
  }

  function selectWorkspaceKind(nextKind: WorkspaceKind) {
    setPendingWorkspaceKind(nextKind);
    if (!isDesktop()) return;
    if (nextKind === "calculation") {
      activateCalculation(pendingModule);
      return;
    }
    const nextFamily =
      sceneFamilies.find((item) => item.id === pendingSceneFamilyId) ??
      sceneFamilies.find((item) => item.availability !== "development");
    if (nextFamily && nextFamily.availability !== "development") activateScene(nextFamily);
  }

  function selectSceneFamily(family: SceneFamily) {
    if (family.availability === "development") return;
    setPendingSceneFamilyId(family.id);
    if (isDesktop()) activateScene(family);
  }

  function openNavigation() {
    resetPendingNavigation();
    setRailOpen(true);
  }

  function applyNavigation() {
    if (pendingWorkspaceKind === "calculation") {
      activateCalculation(pendingModule);
      return;
    }
    const selected = sceneFamilies.find((item) => item.id === pendingSceneFamilyId);
    if (!selected || selected.availability === "development") return;
    activateScene(selected);
    setRailOpen(false);
  }

  function updateInput(key: string, value: unknown) {
    setInputs((current) => ({ ...current, [key]: value }));
    invalidateResult();
  }

  function updateLoads(update: (current: LoadItem[]) => LoadItem[]) {
    invalidateResult();
    setLoads(update);
  }

  function fieldWithCatalog(field: FieldDefinition): FieldDefinition {
    const enriched = field.help || !FIELD_HELP[field.key] ? field : { ...field, help: FIELD_HELP[field.key] };
    if (!materialCatalog || !["rebar_grade", "stirrup_grade"].includes(field.key)) return enriched;
    const role = field.key === "stirrup_grade" ? "stirrup" : "longitudinal";
    return {
      ...enriched,
      options: materialCatalog.items
        .filter((item) => ["active", "restricted"].includes(item.status) && item.roles.includes(role))
        .map((item) => ({ value: item.id, label: `${item.id}${item.status === "restricted" ? " · 受限" : ""}` })),
    };
  }

  function payload() {
    const typedInputs = definition.buildTypedInputs?.(inputs);
    return {
      schema_version: "3.3",
      mode: MODE,
      module,
      project_name: projectName,
      standard_profile: "CN-2026.6",
      ...(typedInputs
        ? { typed_inputs: typedInputs, loads: [] }
        : { inputs: normalizeInputs(module, inputs), loads }),
    };
  }

  async function calculate() {
    if (["pool_structure", "gravity_retaining_wall"].includes(module)) {
      if (inputs.groundwater_condition === "unknown") {
        setError("地下水位未知时不能运行验算；请选择“无地下水影响”或录入已知水位及资料来源。");
        return;
      }
      if (inputs.groundwater_condition === "known_water_table" && !String(inputs.groundwater_source ?? "").trim()) {
        setError("已知地下水位必须填写资料来源。");
        return;
      }
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
        document.getElementById("result-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }),
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
        const revision = await api<SavedRevision>(`/api/v2/projects/${projectId}/revisions`, {
          method: "POST",
          body: JSON.stringify({
            calculations: [
              { node_id: "superstructure", label: "上部结构", calculation: linkedSource.calculation },
              { node_id: "foundation", label: "柱下独立基础", calculation: payload() },
            ],
            connections: [
              {
                source_node_id: "superstructure",
                target_node_id: "foundation",
                support: ["portal_frame", "steel_beam"].includes(linkedSource.result.module) ? "left" : "base",
              },
            ],
          }),
        });
        setSavedRevision(revision);
        setSavedVersion(null);
      } else {
        const version = await api<ProjectVersion>(`/api/v2/projects/${projectId}/versions`, {
          method: "POST",
          body: JSON.stringify({ calculation: payload() }),
        });
        setSavedVersion(version);
        setSavedRevision(null);
      }
      setProjects(await api<Project[]>("/api/v2/projects"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  }

  function createFoundationFromResult(source: CalculationResult) {
    const reaction = (prefix: "vertical" | "horizontal" | "moment") => {
      for (const key of [`base_${prefix}`, `left_${prefix}`, `right_${prefix}`]) {
        const quantity = source.reactions[key];
        if (quantity) return quantity.value;
      }
      return 0;
    };
    const vertical = reaction("vertical");
    if (vertical === 0) {
      setError("当前结果没有可传递给基础的竖向反力。");
      return;
    }
    saveCurrentDraft();
    setLinkedSource({ calculation: payload(), result: source });
    setWorkspaceKind("calculation");
    setPendingWorkspaceKind("calculation");
    setModule("spread_footing");
    setPendingModule("spread_footing");
    setInputs({
      ...MODULE_MAP.spread_footing.defaults,
      horizontal_x_kn: reaction("horizontal"),
      moment_y_kn_m: reaction("moment"),
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
    invalidateResult();
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

  const fieldList = (fields: FieldDefinition[]) => (
    <div className="field-grid">
      {fields.map((field) => (
        <InputField
          key={field.key}
          field={fieldWithCatalog(field)}
          value={inputs[field.key]}
          onChange={(value) => updateInput(field.key, value)}
        />
      ))}
    </div>
  );

  return (
    <div className="workspace-shell">
      <header className="topbar">
        <button className="mobile-nav-button" aria-label="打开导航" aria-expanded={railOpen} onClick={openNavigation}>
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

      {railOpen && <div className="mobile-rail-backdrop" aria-hidden="true" onClick={cancelNavigation} />}

      <NavigationRail
        open={railOpen}
        sceneFamilies={sceneFamilies}
        calculationLibrary={calculationLibrary}
        pendingKind={pendingWorkspaceKind}
        pendingSceneFamilyId={pendingSceneFamilyId}
        pendingModule={pendingModule}
        onSelectKind={selectWorkspaceKind}
        onSelectSceneFamily={selectSceneFamily}
        onSelectModule={selectModule}
        onCancel={cancelNavigation}
        onApply={applyNavigation}
      />

      {workspaceKind === "scene" && selectedSceneFamily ? (
        <main className="workspace-main scene-main">
          <SceneWorkspace
            family={selectedSceneFamily}
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
              <p>单项工具用于补充方案筛查；完整场景的风雪与地震条件请在统一项目条件向导中填写。</p>
            </div>
            <StructureSketch module={module} inputs={inputs} />
          </section>

          <div className="project-strip">
            <label className="project-title-input">
              <span>项目 / 方案名称</span>
              <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
            </label>
            <label>
              <span>保存位置</span>
              <div className="select-wrap">
                <select
                  value={selectedProject}
                  onChange={(event) => {
                    const value = event.target.value === "new" ? "new" : Number(event.target.value);
                    setSelectedProject(value);
                    const selected = projects.find((project) => project.id === value);
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
                  来源 {linkedSource.result.project_name} · Trace {linkedSource.result.trace_id}
                </small>
              </span>
            </div>
          )}

          <div className={definition.buildTypedInputs ? "input-layout typed-input-layout" : "input-layout"}>
            <section className="panel input-panel">
              <PanelHeader number="01" title="结构与材料" subtitle="Geometry & material" />
              {fieldList(basicFields)}
              {advancedFields.length > 0 && (
                <details className="advanced-fields">
                  <summary>高级参数</summary>
                  <p>默认采用当前目录或模块默认值；仅在已有明确依据时修改。</p>
                  {fieldList(advancedFields)}
                </details>
              )}
            </section>

            {!definition.buildTypedInputs && (
              <CalculationLoadsPanel
                loads={loads}
                loadCatalog={loadCatalog}
                climateCatalog={climateCatalog}
                onLoadsChange={updateLoads}
                onError={setError}
              />
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
            <button className="calculate-button" onClick={calculate} disabled={working}>
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
                !["spread_footing", "strip_footing"].includes(module) && Object.keys(result.reactions).length > 0
                  ? () => createFoundationFromResult(result)
                  : undefined
              }
              projectId={selectedProject === "new" ? undefined : selectedProject}
            />
          )}
        </main>
      )}

      {adminOpen && <InviteDialog onClose={() => setAdminOpen(false)} />}
    </div>
  );
}
