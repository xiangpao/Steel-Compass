import type { Dispatch, SetStateAction } from "react";
import type { WorkbenchSelection } from "@/components/pergola-plan-editor-v2";
import type { useWorkbenchProject } from "@/components/pergola/use-workbench-project";
import type { SectionDraft } from "@/lib/pergola-catalog";
import type { GeoReport, GeoStage, MaintenanceCategory } from "@/lib/pergola-project";
import type { ProjectSiteProfile, SceneGeometryProfile } from "@/lib/types";

/** State and actions of the pergola workbench shared with its property panels. */
export type WorkbenchModel = {
  mode: "qa" | "project";
  geometry: SceneGeometryProfile;
  setGeometry: Dispatch<SetStateAction<SceneGeometryProfile>>;
  selection: WorkbenchSelection;
  setSelection: (selection: WorkbenchSelection) => void;
  handleSelection: (selection: WorkbenchSelection) => void;
  setMessage: (message: string) => void;
  sectionDrafts: Record<string, SectionDraft>;
  setSectionDrafts: Dispatch<SetStateAction<Record<string, SectionDraft>>>;
  activeMemberTypeId: string;
  setActiveMemberTypeId: (id: string) => void;
  workElevation: number;
  setWorkElevation: (value: number) => void;
  siteProfile: ProjectSiteProfile;
  setSiteProfile: Dispatch<SetStateAction<ProjectSiteProfile>>;
  roofAssemblyId: string;
  setRoofAssemblyId: (id: string) => void;
  maintenanceCategory: MaintenanceCategory;
  setMaintenanceCategory: (category: MaintenanceCategory) => void;
  maintenanceLoad: number;
  setMaintenanceLoad: (value: number) => void;
  soilPresetId: string;
  setSoilPresetId: (id: string) => void;
  geoStage: GeoStage;
  setGeoStage: (stage: GeoStage) => void;
  report: GeoReport;
  setReport: Dispatch<SetStateAction<GeoReport>>;
  project: ReturnType<typeof useWorkbenchProject>;
};

/** Objects referenced by the current selection. */
export function selectionDetails(geometry: SceneGeometryProfile, selection: WorkbenchSelection) {
  const member = selection?.kind === "member" ? geometry.members.find((item) => item.id === selection.id) : undefined;
  const memberInstance = member ? geometry.member_instances?.find((item) => item.member_id === member.id) : undefined;
  const memberType = memberInstance ? geometry.member_types?.find((item) => item.id === memberInstance.member_type_id) : undefined;
  const foundation = selection?.kind === "foundation" ? geometry.foundation_instances?.find((item) => item.id === selection.id) : undefined;
  const foundationType = foundation ? geometry.foundation_types?.find((item) => item.id === foundation.foundation_type_id) : undefined;
  const support = foundation ? geometry.supports?.find((item) => item.id === foundation.support_id) : undefined;
  return {
    member,
    memberInstance,
    memberType,
    node: selection?.kind === "node" ? geometry.nodes.find((item) => item.id === selection.id) : undefined,
    foundation,
    foundationType,
    support,
    supportNode: support ? geometry.nodes.find((item) => item.id === support.node_id) : undefined,
    columnBase: support ? geometry.column_bases?.find((item) => item.support_id === support.id) : undefined,
    directSupport: selection?.kind === "support" ? geometry.supports?.find((item) => item.id === selection.id) : undefined,
  };
}
