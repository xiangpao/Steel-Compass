import type { Dispatch, SetStateAction } from "react";
import type { useSceneSpecifications } from "@/components/scene/use-scene-specifications";
import type { SceneConditions, SceneExposure, SceneGeotech, SemanticFactors } from "@/lib/scene-profiles";
import type {
  ClimateRegionCatalog,
  FoundationDesignSpecification,
  MemberSpecification,
  Project,
  RoofAssembly,
  SceneConditionProfile,
  SceneFamily,
  SceneGraphTemplate,
  SceneInstance,
  SceneLoadCase,
  SceneRevision,
  SceneVariant,
  SeismicDesignCatalog,
} from "@/lib/types";

/** State and handlers the legacy scene workspace hands to its settings tab. */
export type SceneSettingsModel = {
  family: SceneFamily;
  variant: SceneVariant | undefined;
  variantId: string;
  selectVariant: (variantId: string) => void;
  material: string;
  setMaterial: (material: string) => void;
  sceneTitle: string;
  setSceneTitle: (title: string) => void;
  markChanged: (nodeIds?: string[]) => void;
  visibleNodes: SceneGraphTemplate["nodes"];
  nodeLabel: (nodeId: string) => string | undefined;
  visibleParameters: SceneVariant["parameters"];
  parameters: Record<string, unknown>;
  setParameters: Dispatch<SetStateAction<Record<string, unknown>>>;
  updateParameter: (key: string, value: unknown) => void;
  specs: ReturnType<typeof useSceneSpecifications>;
  memberSpecifications: MemberSpecification[];
  setMemberSpecifications: Dispatch<SetStateAction<MemberSpecification[]>>;
  foundationSpecifications: FoundationDesignSpecification[];
  setFoundationSpecifications: Dispatch<SetStateAction<FoundationDesignSpecification[]>>;
  working: boolean;
  hasGenericFoundation: boolean;
  geotech: SceneGeotech;
  setGeotech: Dispatch<SetStateAction<SceneGeotech>>;
  conditionProfile: SceneConditionProfile;
  hasConditions: boolean;
  needs: { wind: boolean; snow: boolean; seismic: boolean };
  conditions: SceneConditions;
  setConditions: Dispatch<SetStateAction<SceneConditions>>;
  exposure: SceneExposure;
  setExposure: Dispatch<SetStateAction<SceneExposure>>;
  climateCatalog?: ClimateRegionCatalog | null;
  seismicCatalog?: SeismicDesignCatalog | null;
  selectedClimate: ClimateRegionCatalog["items"][number] | undefined;
  factors: SemanticFactors;
  climateInputsReady: boolean;
  roofAssemblies: RoofAssembly[];
  loadCases: SceneLoadCase[];
  updateLoadCase: (index: number, patch: Partial<SceneLoadCase>) => void;
  addCustomLoad: () => void;
  projects: Project[];
  selectedProject: number | "new";
  setSelectedProject: (project: number | "new") => void;
  projectInstances: SceneInstance[];
  instance: SceneInstance | null;
  instanceRevisions: Record<number, SceneRevision[]>;
  hydrateFromInstance: (instance: SceneInstance, revisions: SceneRevision[]) => void;
};
