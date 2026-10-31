"use client";

import dynamic from "next/dynamic";
import { BarChart3, Box, Building2, CloudSnow, GitBranch, Grid2X2, MapPin, PanelLeftClose, Ruler, Save, Settings2, Trees } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { PergolaPlanEditorV2, type OrthographicView, type WorkbenchSelection } from "@/components/pergola-plan-editor-v2";
import { FoundationPanel } from "@/components/pergola/foundation-panel";
import { ModelPanel } from "@/components/pergola/model-panel";
import { ResultsPanel } from "@/components/pergola/results-panel";
import { ConditionsPanel, LibraryPanel, LoadPanel } from "@/components/pergola/site-panels";
import { useWorkbenchProject } from "@/components/pergola/use-workbench-project";
import type { WorkbenchModel } from "@/components/pergola/workbench-model";
import { DEFAULT_SECTIONS, INITIAL_REPORT, INITIAL_SITE_PROFILE, SOIL_PRESETS, type SectionDraft } from "@/lib/pergola-catalog";
import { foundationsBySupportId as foundationSpecsBySupport } from "@/lib/pergola-edits";
import { initialGeometry } from "@/lib/pergola-geometry";
import type { GeoStage, MaintenanceCategory } from "@/lib/pergola-project";
import type { Project, ProjectSiteProfile, SceneGeometryProfile } from "@/lib/types";

const SceneModelPreview = dynamic(() => import("@/components/scene-model-preview").then((module) => module.SceneModelPreview), { ssr: false });

const QA_DRAFT_KEY = "steel-compass:qa:pergola-workbench-v2";
const SPLIT_KEY = "steel-compass:qa:workbench-split";

type Area = "library" | "conditions" | "model" | "loads" | "foundation" | "results";
type PergolaWorkbenchProps = {
  mode?: "qa" | "project";
  projects?: Project[];
  onProjectsChange?: (projects: Project[]) => void;
};

const NAVIGATION: Array<{ id: Area; label: string; icon: typeof Trees }> = [
  { id: "library", label: "场景库", icon: Trees },
  { id: "conditions", label: "项目条件", icon: MapPin },
  { id: "model", label: "模型", icon: Grid2X2 },
  { id: "loads", label: "荷载", icon: CloudSnow },
  { id: "foundation", label: "基础", icon: Building2 },
  { id: "results", label: "结果", icon: BarChart3 },
];

const PANEL_TITLES: Partial<Record<Area, string>> = { library: "场景库", conditions: "项目条件", results: "分析结果" };

const VIEWS: Array<[OrthographicView, string]> = [
  ["plan", "平面"],
  ["x_elevation", "X立面"],
  ["y_elevation", "Y立面"],
];

const MOBILE_PANES = [
  { id: "property", label: "属性", icon: Settings2 },
  { id: "2d", label: "二维", icon: Ruler },
  { id: "3d", label: "三维", icon: Box },
] as const;

function readStorage(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage blocked or full; the QA draft and splitter width are conveniences.
  }
}

/** Load the QA draft, refusing legacy or inconsistent geometry; returns a message when refused. */
function readQaDraft(): { geometry?: SceneGeometryProfile; message?: string } {
  const saved = readStorage(QA_DRAFT_KEY);
  if (!saved) return {};
  try {
    const candidate = JSON.parse(saved) as SceneGeometryProfile;
    if (candidate.profile_version !== "2.3") {
      return { message: "检测到旧 Geometry 草稿；为避免升级孤立对象，本次使用干净 2.3 模型，可在场景库选择重建。" };
    }
    const connected = new Set(candidate.members.flatMap((item) => [item.start_node_id, item.end_node_id]));
    const isolated = candidate.nodes.some(
      (item) => !connected.has(item.id) && !(candidate.supports ?? []).some((support) => support.node_id === item.id),
    );
    if (isolated) return { message: "旧 QA 草稿含孤立节点，已阻止自动加载；请在场景库重建或先修复旧草稿。" };
    return { geometry: candidate };
  } catch {
    return { message: "QA 草稿无法读取，已使用干净初始模型。" };
  }
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
  const [geoStage, setGeoStage] = useState<GeoStage>("scheme_estimate");
  const [report, setReport] = useState(INITIAL_REPORT);
  const [mobilePane, setMobilePane] = useState<"property" | "2d" | "3d">("2d");
  const [splitPercent, setSplitPercent] = useState(55);
  const [draggingSplit, setDraggingSplit] = useState(false);
  const [roofAssemblyId, setRoofAssemblyId] = useState("steel");
  const [maintenanceCategory, setMaintenanceCategory] = useState<MaintenanceCategory>("maintenance");
  const [maintenanceLoad, setMaintenanceLoad] = useState(0.5);
  const [siteProfile, setSiteProfile] = useState<ProjectSiteProfile>(INITIAL_SITE_PROFILE);
  const [newProjectName, setNewProjectName] = useState("");

  const project = useWorkbenchProject({
    enabled: mode === "project",
    projects,
    onProjectsChange,
    inputs: {
      geometry,
      setGeometry,
      siteProfile,
      setSiteProfile,
      sectionDrafts,
      setSectionDrafts,
      soil: SOIL_PRESETS.find((item) => item.id === soilPresetId)!,
      soilPresetId,
      setSoilPresetId,
      geoStage,
      setGeoStage,
      report,
      setReport,
      roofAssemblyId,
      setRoofAssemblyId,
      maintenanceCategory,
      maintenanceLoad,
    },
    onMessage: setMessage,
    onAnalyzed: () => setArea("results"),
  });

  useEffect(() => {
    if (mode !== "qa") return;
    const draft = readQaDraft();
    if (draft.geometry) setGeometry(draft.geometry);
    if (draft.message) setMessage(draft.message);
  }, [mode]);

  useEffect(() => {
    const saved = Number(readStorage(SPLIT_KEY));
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
      setSplitPercent(Math.min(70, Math.max(30, ((event.clientX - contentLeft) / available) * 100)));
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
    writeStorage(SPLIT_KEY, String(splitPercent));
  }, [splitPercent]);

  useEffect(() => {
    if (mode === "qa") writeStorage(QA_DRAFT_KEY, JSON.stringify(geometry));
  }, [geometry, mode]);

  const foundationsBySupportId = useMemo(
    () => foundationSpecsBySupport(geometry),
    // Only foundations feed the preview specs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [geometry.foundation_instances, geometry.foundation_types],
  );

  function handleSelection(value: WorkbenchSelection) {
    setSelection(value);
    if (value?.kind === "foundation") setArea("foundation");
    else if (value) setArea("model");
  }

  async function saveWorkbench() {
    if (mode === "qa") {
      writeStorage(QA_DRAFT_KEY, JSON.stringify(geometry));
      setMessage("QA 草稿已保存，不影响现有项目和快照。");
      return;
    }
    await project.saveModel();
  }

  const model: WorkbenchModel = {
    mode,
    geometry,
    setGeometry,
    selection,
    setSelection,
    handleSelection,
    setMessage,
    sectionDrafts,
    setSectionDrafts,
    activeMemberTypeId,
    setActiveMemberTypeId,
    workElevation,
    setWorkElevation,
    siteProfile,
    setSiteProfile,
    roofAssemblyId,
    setRoofAssemblyId,
    maintenanceCategory,
    setMaintenanceCategory,
    maintenanceLoad,
    setMaintenanceLoad,
    soilPresetId,
    setSoilPresetId,
    geoStage,
    setGeoStage,
    report,
    setReport,
    project,
  };

  const panels: Record<Area, () => React.ReactNode> = {
    library: () => <LibraryPanel model={model} />,
    conditions: () => <ConditionsPanel model={model} />,
    model: () => <ModelPanel model={model} />,
    loads: () => <LoadPanel model={model} />,
    foundation: () => <FoundationPanel model={model} />,
    results: () => <ResultsPanel model={model} />,
  };

  return (
    <main
      ref={shellRef}
      className="qa-workbench-shell"
      style={{ "--qa-plan-fr": `${splitPercent}fr`, "--qa-3d-fr": `${100 - splitPercent}fr` } as React.CSSProperties}
    >
      <aside className="qa-icon-rail" aria-label="亭廊工作台一级入口">
        <div className="qa-brand-mark">SC</div>
        {NAVIGATION.map((item) => (
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
            <h1>{PANEL_TITLES[area] ?? "对象属性"}</h1>
          </div>
          <span className="qa-schema-badge">Geometry 2.3</span>
        </header>
        <div className="qa-property-scroll">{panels[area]()}</div>
        <footer>
          <small role="status">{message}</small>
          {mode === "project" && (
            <>
              <div className="qa-project-create">
                <input
                  aria-label="新项目名称"
                  placeholder="新项目名称"
                  value={newProjectName}
                  onChange={(event) => setNewProjectName(event.target.value)}
                />
                <button
                  type="button"
                  disabled={project.serverBusy}
                  onClick={async () => {
                    if (await project.createProject(newProjectName)) setNewProjectName("");
                  }}
                >
                  新建项目
                </button>
              </div>
              <select
                aria-label="保存到项目"
                value={project.selectedProjectId ?? ""}
                onChange={(event) => project.selectProject(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">选择项目</option>
                {projects.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </>
          )}
          <button type="button" disabled={project.serverBusy} onClick={saveWorkbench}>
            <Save size={16} />
            {project.serverBusy ? "处理中…" : mode === "qa" ? "保存 QA 草稿" : "保存项目模型"}
          </button>
          {mode === "project" && (
            <button type="button" disabled={project.serverBusy} onClick={project.analyze}>
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
            <strong>{VIEWS.find(([id]) => id === view)?.[1]}</strong>
          </div>
          <div className="qa-view-tabs" role="tablist" aria-label="二维视图">
            {VIEWS.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={view === id} className={view === id ? "active" : ""} onClick={() => setView(id)}>
                {label}
              </button>
            ))}
          </div>
        </header>
        <PergolaPlanEditorV2
          geometry={geometry}
          selection={selection}
          view={view}
          workElevation={workElevation}
          activeMemberTypeId={activeMemberTypeId}
          onSelectionChange={handleSelection}
          onGeometryChange={setGeometry}
          onMessage={setCanvasMessage}
        />
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
        <SceneModelPreview
          geometry={geometry}
          foundationsBySupportId={foundationsBySupportId}
          selectedMemberId={selection?.kind === "member" ? selection.id : null}
          selectedFoundationId={selection?.kind === "foundation" ? selection.id : null}
          onSelectMember={(id) => handleSelection({ kind: "member", id })}
          onSelectFoundation={(id) => handleSelection({ kind: "foundation", id })}
        />
        <div className="qa-3d-overlay">
          <Box size={16} />
          <span>拖动旋转 · 滚轮缩放 · 点击构件或基础定位</span>
        </div>
      </section>
      <nav className="qa-mobile-tabs" aria-label="移动端工作台视图">
        {MOBILE_PANES.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button" className={mobilePane === id ? "active" : ""} onClick={() => setMobilePane(id)}>
            <Icon size={17} />
            {label}
          </button>
        ))}
      </nav>
    </main>
  );
}
