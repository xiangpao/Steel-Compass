"use client";

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { api, errorMessage, isAbortError } from "@/lib/api";
import { checkStatusLabel } from "@/lib/evidence-status";
import { DEFAULT_SECTIONS, INITIAL_REPORT, INITIAL_SITE_PROFILE, roofAssemblyCatalogId, roofAssemblyUiId, type AnalysisResult, type SectionDraft } from "@/lib/pergola-catalog";
import { initialGeometry } from "@/lib/pergola-geometry";
import {
  buildGeotechnicalProfile,
  geotechnicalUiState,
  roofLoadSelection,
  sectionDimensions,
  sectionDraftFor,
  sectionDraftsFromCatalog,
  type GeoReport,
  type GeoStage,
  type MaintenanceCategory,
} from "@/lib/pergola-project";
import type { SoilPreset } from "@/lib/pergola-catalog";
import type { CustomSectionDefinition, Project, ProjectGeotechnicalProfile, ProjectSiteProfile, SceneGeometryProfile } from "@/lib/types";

type SceneInstanceSummary = { id: number; family_id: string; variant_id: string; archived: boolean };

/** Workbench inputs the project hook reads and restores. */
export type WorkbenchInputs = {
  geometry: SceneGeometryProfile;
  setGeometry: Dispatch<SetStateAction<SceneGeometryProfile>>;
  siteProfile: ProjectSiteProfile;
  setSiteProfile: Dispatch<SetStateAction<ProjectSiteProfile>>;
  sectionDrafts: Record<string, SectionDraft>;
  setSectionDrafts: Dispatch<SetStateAction<Record<string, SectionDraft>>>;
  soil: SoilPreset;
  soilPresetId: string;
  setSoilPresetId: (id: string) => void;
  geoStage: GeoStage;
  setGeoStage: (stage: GeoStage) => void;
  report: GeoReport;
  setReport: Dispatch<SetStateAction<GeoReport>>;
  roofAssemblyId: string;
  setRoofAssemblyId: (id: string) => void;
  maintenanceCategory: MaintenanceCategory;
  maintenanceLoad: number;
};

/**
 * Project-backed load, save and analysis of the pergola workbench. Results
 * are cleared whenever an input changes; an analysis response for older
 * inputs is discarded, and a running analysis is aborted on unmount or
 * project switch.
 */
export function useWorkbenchProject({
  enabled,
  projects,
  onProjectsChange,
  inputs,
  onMessage,
  onAnalyzed,
}: {
  enabled: boolean;
  projects: Project[];
  onProjectsChange?: (projects: Project[]) => void;
  inputs: WorkbenchInputs;
  onMessage: (message: string) => void;
  onAnalyzed: () => void;
}) {
  const [selectedProjectId, setSelectedProjectIdState] = useState<number | null>(projects[0]?.id ?? null);
  const [sceneInstanceId, setSceneInstanceId] = useState<number | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisSnapshotId, setAnalysisSnapshotId] = useState<number | null>(null);
  const [serverBusy, setServerBusy] = useState(false);
  const savedGeotechnical = useRef<{ profile: ProjectGeotechnicalProfile; ui: string } | null>(null);
  // Fingerprint of every analysis input. An analysis response is kept only if
  // the inputs still match the fingerprint taken when the request was sent;
  // comparing content (not object identity) means writing the saved,
  // normalized model back into state does not count as an edit.
  const inputFingerprint = useRef("");
  const analysis = useRef<AbortController | null>(null);
  const latest = useRef(inputs);
  const latestFingerprint = useRef("");
  useEffect(() => {
    latest.current = inputs;
  });

  const { geometry, siteProfile, sectionDrafts, soilPresetId, geoStage, report, roofAssemblyId, maintenanceCategory, maintenanceLoad } = inputs;
  const fingerprint = JSON.stringify([geometry, siteProfile, sectionDrafts, soilPresetId, geoStage, report, roofAssemblyId, maintenanceCategory, maintenanceLoad]);
  useEffect(() => {
    latestFingerprint.current = fingerprint;
    if (fingerprint === inputFingerprint.current) return;
    inputFingerprint.current = fingerprint;
    setAnalysisResult(null);
    setAnalysisSnapshotId(null);
  }, [fingerprint]);

  useEffect(() => () => analysis.current?.abort(), []);

  useEffect(() => {
    if (!enabled || selectedProjectId !== null || projects.length === 0) return;
    setSelectedProjectIdState(projects[0].id);
  }, [enabled, projects, selectedProjectId]);

  useEffect(() => {
    if (!enabled || selectedProjectId === null) return;
    const controller = new AbortController();
    const { signal } = controller;
    const base = `/api/v2/projects/${selectedProjectId}`;
    const ui = latest.current;
    Promise.all([
      api<SceneInstanceSummary[]>(`${base}/scene-instances`, { signal }),
      api<ProjectSiteProfile | null>(`${base}/site-profile`, { signal }),
      api<{ items: CustomSectionDefinition[] }>(`${base}/custom-sections`, { signal }),
      api<ProjectGeotechnicalProfile | null>(`${base}/geotechnical-profile`, { signal }),
    ])
      .then(async ([instances, profile, sectionCatalog, geotechnical]) => {
        // Reset first so a project without saved data never inherits the
        // previous project's conditions or model.
        ui.setSiteProfile(profile ?? INITIAL_SITE_PROFILE);
        ui.setReport(INITIAL_REPORT);
        ui.setGeoStage("scheme_estimate");
        ui.setSoilPresetId("plastic-clay");
        ui.setGeometry(initialGeometry());
        ui.setSectionDrafts(DEFAULT_SECTIONS);
        savedGeotechnical.current = null;
        if (geotechnical) {
          const restored = geotechnicalUiState(geotechnical);
          ui.setGeoStage(restored.geoStage);
          ui.setSoilPresetId(restored.soilPresetId);
          ui.setReport(restored.report);
          savedGeotechnical.current = { profile: geotechnical, ui: JSON.stringify(restored) };
        }
        const instance = instances.find((item) => !item.archived && item.family_id === "pergola-pavilion" && item.variant_id === "guided-grid");
        setSceneInstanceId(instance?.id ?? null);
        if (!instance) return;
        const savedGeometry = await api<SceneGeometryProfile | null>(`${base}/scene-instances/${instance.id}/geometry`, { signal });
        if (savedGeometry?.profile_version !== "2.3") return;
        ui.setGeometry(savedGeometry);
        ui.setSectionDrafts((current) => sectionDraftsFromCatalog(current, savedGeometry.member_types ?? [], sectionCatalog.items));
        const uiAssembly = roofAssemblyUiId(savedGeometry.roof_load_zones?.[0]?.roof_assembly_id);
        if (uiAssembly) ui.setRoofAssemblyId(uiAssembly);
      })
      .catch((error) => {
        if (!isAbortError(error)) onMessage(errorMessage(error));
      });
    return () => controller.abort();
    // onMessage only sets a status line; loading is keyed by the project.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, selectedProjectId]);

  function clearAnalysis() {
    setAnalysisResult(null);
    setAnalysisSnapshotId(null);
  }

  function selectProject(id: number | null) {
    analysis.current?.abort();
    setSelectedProjectIdState(id);
    setSceneInstanceId(null);
    clearAnalysis();
  }

  function geotechnicalProfile(): ProjectGeotechnicalProfile {
    // Keep the saved profile verbatim when its UI fields are unchanged, so
    // fields the workbench does not edit are not lost on save.
    const ui = JSON.stringify({ soilPresetId, geoStage, report });
    if (savedGeotechnical.current?.ui === ui) return savedGeotechnical.current.profile;
    return buildGeotechnicalProfile(geoStage, inputs.soil, soilPresetId, report);
  }

  async function saveSectionRevisions(projectId: number) {
    const base = `/api/v2/projects/${projectId}/custom-sections`;
    const catalog = await api<{ items: CustomSectionDefinition[] }>(base);
    const typeSectionIds: Record<string, string> = {};
    for (const type of geometry.member_types ?? []) {
      const draft = sectionDraftFor(sectionDrafts, type.id);
      const dimensions = sectionDimensions(draft);
      const baseId = `pergola-${type.id}`;
      const existing = catalog.items.find((item) => item.id === type.section_id) ?? catalog.items.find((item) => item.id === baseId);
      const unchanged =
        existing &&
        existing.family === draft.family &&
        Object.entries(dimensions).every(([key, value]) => Math.abs((existing.dimensions[key] ?? Number.NaN) - value) < 1e-9);
      if (unchanged) {
        typeSectionIds[type.id] = existing.id;
        continue;
      }
      const payload = { name: `${type.title} 项目截面`, family: draft.family, dimensions, source_reference: "亭廊工作台用户几何输入" };
      if (existing) {
        const revised = await api<CustomSectionDefinition>(`${base}/${existing.id}/revisions`, { method: "POST", body: JSON.stringify(payload) });
        typeSectionIds[type.id] = revised.id;
        catalog.items.push(revised);
        continue;
      }
      const created = await api<{ items: CustomSectionDefinition[] }>(base, { method: "POST", body: JSON.stringify({ id: baseId, ...payload }) });
      typeSectionIds[type.id] = created.items.find((item) => item.id === baseId)?.id ?? baseId;
      catalog.items = created.items;
    }
    return typeSectionIds;
  }

  async function persistProjectModel() {
    if (selectedProjectId === null) throw new Error("请先选择一个项目，再保存亭廊模型。");
    const unsupportedGrade = geometry.member_types?.find((type) => !["Q235B", "Q355B"].includes(type.material_grade));
    if (unsupportedGrade) {
      throw new Error(`${unsupportedGrade.title} 的钢材牌号 ${unsupportedGrade.material_grade} 尚未在工作台开放，请选择 Q235B 或 Q355B。`);
    }
    if ((siteProfile.completed_conditions?.length ?? 0) < 3) throw new Error("项目条件未完成：风、雪、地震必须全部明确。");
    if (geoStage === "project_check" && (!report.name || !report.date || report.modulus <= 0)) {
      throw new Error("工程校核必须填写勘察报告名称、日期和变形参数。");
    }
    const projectId = selectedProjectId;
    const base = `/api/v2/projects/${projectId}`;
    setServerBusy(true);
    try {
      const typeSectionIds = await saveSectionRevisions(projectId);
      const profileToSave: ProjectSiteProfile = {
        ...siteProfile,
        climate_source_reference:
          siteProfile.climate_source_reference || (siteProfile.region_preset === "manual" ? "用户录入项目资料" : "浙江区域气候目录（未验证）"),
      };
      await api(`${base}/site-profile`, { method: "PUT", body: JSON.stringify(profileToSave) });
      await api(`${base}/geotechnical-profile`, { method: "PUT", body: JSON.stringify(geotechnicalProfile()) });
      let instanceId = sceneInstanceId;
      if (instanceId === null) {
        const created = await api<{ id: number }>(`${base}/scene-instances`, {
          method: "POST",
          body: JSON.stringify({ family_id: "pergola-pavilion", variant_id: "guided-grid", title: "亭廊 Geometry 2.3", mode: "quick" }),
        });
        instanceId = created.id;
        setSceneInstanceId(instanceId);
      }
      const assemblyId = roofAssemblyCatalogId(roofAssemblyId);
      const savedGeometry: SceneGeometryProfile = {
        ...geometry,
        member_types: (geometry.member_types ?? []).map((type) => ({ ...type, section_id: typeSectionIds[type.id] })),
        roof_load_zones: (geometry.roof_load_zones ?? []).map((zone) => ({ ...zone, roof_assembly_id: assemblyId })),
      };
      await api(`${base}/scene-instances/${instanceId}/geometry`, { method: "PUT", body: JSON.stringify(savedGeometry) });
      inputs.setGeometry(savedGeometry);
      inputs.setSiteProfile(profileToSave);
      clearAnalysis();
      onMessage("项目条件、截面修订、Geometry 2.3 与地下条件已保存；旧分析结果已失效。");
      const savedFingerprint = JSON.stringify([savedGeometry, profileToSave, sectionDrafts, soilPresetId, geoStage, report, roofAssemblyId, maintenanceCategory, maintenanceLoad]);
      return { projectId, instanceId, assemblyId, savedFingerprint };
    } finally {
      setServerBusy(false);
    }
  }

  async function createProject(name: string) {
    if (!name.trim()) {
      onMessage("请输入新项目名称。");
      return false;
    }
    setServerBusy(true);
    try {
      const project = await api<Project>("/api/v2/projects", { method: "POST", body: JSON.stringify({ name: name.trim(), description: "" }) });
      onProjectsChange?.([...projects, project]);
      selectProject(project.id);
      onMessage("项目已创建，请完善条件后保存模型。");
      return true;
    } catch (error) {
      onMessage(errorMessage(error));
      return false;
    } finally {
      setServerBusy(false);
    }
  }

  async function saveModel() {
    try {
      await persistProjectModel();
    } catch (error) {
      onMessage(errorMessage(error));
    }
  }

  async function analyze() {
    if (!enabled || selectedProjectId === null) return;
    analysis.current?.abort();
    const controller = new AbortController();
    analysis.current = controller;
    try {
      const { projectId, instanceId, assemblyId, savedFingerprint } = await persistProjectModel();
      setServerBusy(true);
      const result = await api<AnalysisResult>(`/api/v2/projects/${projectId}/scene-instances/${instanceId}/analyze`, {
        method: "POST",
        body: JSON.stringify({ stage: geoStage, roof_load_selection: roofLoadSelection(assemblyId, maintenanceCategory, maintenanceLoad) }),
        signal: controller.signal,
      });
      if (savedFingerprint !== latestFingerprint.current) {
        onMessage("分析期间模型或条件已修改，本次结果已作废，请重新分析。");
        return;
      }
      setAnalysisResult(result);
      setAnalysisSnapshotId(result.snapshot_id ?? null);
      onAnalyzed();
      onMessage(`服务端分析完成：${checkStatusLabel(result.workflow_status)}`);
    } catch (error) {
      if (!isAbortError(error)) onMessage(errorMessage(error));
    } finally {
      if (analysis.current === controller) analysis.current = null;
      setServerBusy(false);
    }
  }

  return {
    selectedProjectId,
    selectProject,
    sceneInstanceId,
    analysisResult,
    analysisSnapshotId,
    serverBusy,
    createProject,
    saveModel,
    analyze,
  };
}
