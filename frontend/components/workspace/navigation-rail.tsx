"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Compass, Gauge, X } from "lucide-react";
import { MODULE_MAP, NEXTGEN_LIBRARY_ITEMS } from "@/lib/modules";
import type { CalculationLibrary, CalculationLibraryItem, Module, SceneFamily } from "@/lib/types";

export type WorkspaceKind = "scene" | "calculation";
type MaterialFilter = "" | "steel" | "concrete" | "timber";
type CalculationGroup = { task: string; title: string; items: CalculationLibraryItem[] };

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

const TASK_ORDER = ["superstructure", "connections_supports", "foundations_geotechnical", "retaining_pool"];

const MATERIAL_FILTERS: Array<[MaterialFilter, string]> = [
  ["", "全部"],
  ["steel", "钢"],
  ["concrete", "混凝土"],
  ["timber", "木"],
];

function calculationGroups(library: CalculationLibrary | null, materialFilter: MaterialFilter) {
  const merged = new Map((library?.items ?? []).map((item) => [item.module ?? item.id, item]));
  NEXTGEN_LIBRARY_ITEMS.forEach((item) => {
    const key = item.module ?? item.id;
    if (!merged.has(key)) merged.set(key, item);
  });
  const visibleItems = [...merged.values()].filter(
    (item) =>
      item.task !== "loads_environment" &&
      Boolean(item.module && item.module in MODULE_MAP) &&
      (!materialFilter || !item.material || item.material === materialFilter),
  );
  const groupsFor = (common: boolean): CalculationGroup[] =>
    TASK_ORDER.map((task) => ({
      task,
      title: visibleItems.find((item) => item.task === task)?.task_title ?? task,
      items: visibleItems.filter(
        (item) =>
          item.task === task &&
          Boolean(item.module && CORE_CALCULATION_MODULES.has(item.module)) === common,
      ),
    })).filter((group) => group.items.length > 0);
  return { common: groupsFor(true), more: groupsFor(false) };
}

export function NavigationRail({
  open,
  sceneFamilies,
  calculationLibrary,
  pendingKind,
  pendingSceneFamilyId,
  pendingModule,
  onSelectKind,
  onSelectSceneFamily,
  onSelectModule,
  onCancel,
  onApply,
}: {
  open: boolean;
  sceneFamilies: SceneFamily[];
  calculationLibrary: CalculationLibrary | null;
  pendingKind: WorkspaceKind;
  pendingSceneFamilyId: string;
  pendingModule: Module;
  onSelectKind: (kind: WorkspaceKind) => void;
  onSelectSceneFamily: (family: SceneFamily) => void;
  onSelectModule: (module: Module) => void;
  onCancel: () => void;
  onApply: () => void;
}) {
  const [expandedTask, setExpandedTask] = useState("common:superstructure");
  const [materialFilter, setMaterialFilter] = useState<MaterialFilter>("");
  const [moreScenesOpen, setMoreScenesOpen] = useState(false);
  const [moreCalculationsOpen, setMoreCalculationsOpen] = useState(false);
  const groups = useMemo(
    () => calculationGroups(calculationLibrary, materialFilter),
    [calculationLibrary, materialFilter],
  );
  const sceneButton = (family: SceneFamily) => (
    <button
      key={family.id}
      disabled={family.availability === "development"}
      className={pendingSceneFamilyId === family.id ? "active" : ""}
      onClick={() => onSelectSceneFamily(family)}
    >
      <span>
        {family.title}
        <em className={`maturity-dot ${family.maturity}`} />
      </span>
      <small>{family.availability === "development" ? "开发中 · 暂不开放计算" : family.description}</small>
    </button>
  );
  const groupList = (tier: "common" | "more") => (
    <CalculationGroupList
      tier={tier}
      groups={groups[tier]}
      expandedTask={expandedTask}
      onToggle={(taskKey) => setExpandedTask((current) => (current === taskKey ? "" : taskKey))}
      pendingModule={pendingModule}
      onSelect={onSelectModule}
    />
  );

  return (
    <aside className={`left-rail ${open ? "open" : ""}`}>
      <button className="rail-close" aria-label="关闭导航" onClick={onCancel}>
        <X size={20} />
      </button>
      <div className="rail-section">
        <span className="rail-label">一级入口</span>
        <div className="mode-switch entry-switch">
          <button className={pendingKind === "scene" ? "active" : ""} onClick={() => onSelectKind("scene")}>
            <Compass size={17} />
            <span>完整场景</span>
          </button>
          <button className={pendingKind === "calculation" ? "active" : ""} onClick={() => onSelectKind("calculation")}>
            <Gauge size={17} />
            <span>单项计算</span>
          </button>
        </div>
      </div>

      {pendingKind === "scene" ? (
        <div className="rail-section scenario-list">
          <span className="rail-label">完整景观场景</span>
          {sceneFamilies.filter((family) => CORE_SCENE_IDS.has(family.id)).map(sceneButton)}
          <MoreToggle
            open={moreScenesOpen}
            label="更多场景"
            onOpenChange={setMoreScenesOpen}
          >
            {sceneFamilies.filter((family) => !CORE_SCENE_IDS.has(family.id)).map(sceneButton)}
          </MoreToggle>
        </div>
      ) : (
        <>
          <div className="rail-section material-filter">
            <span className="rail-label">材料筛选</span>
            <div>
              {MATERIAL_FILTERS.map(([value, label]) => (
                <button
                  key={value || "all"}
                  className={materialFilter === value ? "active" : ""}
                  onClick={() => setMaterialFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="rail-section calculation-library">
            <span className="rail-label">常用单项</span>
            {groupList("common")}
            {groups.more.length > 0 && (
              <MoreToggle
                open={moreCalculationsOpen}
                label="更多单项"
                onOpenChange={setMoreCalculationsOpen}
              >
                {groupList("more")}
              </MoreToggle>
            )}
          </div>
        </>
      )}
      <div className="rail-selection-summary">
        <small>待应用</small>
        <strong>
          {pendingKind === "scene"
            ? `完整场景 · ${sceneFamilies.find((item) => item.id === pendingSceneFamilyId)?.title ?? "请选择"}`
            : `单项计算 · ${MODULE_MAP[pendingModule].title}`}
        </strong>
        <span>选择期间菜单保持打开，现有输入不会被重置。</span>
      </div>
      <div className="rail-actions">
        <button className="secondary-button" onClick={onCancel}>
          取消
        </button>
        <button className="primary-button" onClick={onApply}>
          应用并关闭
        </button>
      </div>
    </aside>
  );
}

function MoreToggle({
  open,
  label,
  onOpenChange,
  children,
}: {
  open: boolean;
  label: string;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}) {
  if (!open) {
    return (
      <button className="library-group-toggle" aria-expanded={false} onClick={() => onOpenChange(true)}>
        <span>{label}</span>
        <ChevronDown size={15} />
      </button>
    );
  }
  return (
    <>
      {children}
      <button
        className="library-collapse-icon"
        aria-label={`收起${label}`}
        title={`收起${label}`}
        onClick={() => onOpenChange(false)}
      >
        <ChevronUp size={17} />
      </button>
    </>
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
  groups: CalculationGroup[];
  expandedTask: string;
  onToggle: (taskKey: string) => void;
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
          onClick={() => onToggle(taskKey)}
        >
          <span>{group.title}</span>
          <ChevronDown size={15} />
        </button>
        {expandedTask === taskKey && (
          <div className="library-items">
            {group.items.map((item) => {
              const moduleDefinition = item.module && item.module in MODULE_MAP ? MODULE_MAP[item.module] : null;
              return (
                <button
                  key={item.id}
                  disabled={!moduleDefinition}
                  className={moduleDefinition?.id === pendingModule ? "active" : ""}
                  onClick={() => moduleDefinition && onSelect(moduleDefinition.id)}
                >
                  <span className={`module-code ${moduleDefinition?.material ?? "planned"}`}>
                    {moduleDefinition?.short ?? "·"}
                  </span>
                  <span>
                    <strong>{item.title}</strong>
                    <small>{moduleDefinition ? item.description : "计划开发"}</small>
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
