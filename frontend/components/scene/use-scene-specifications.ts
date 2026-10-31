"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { INITIAL_CUSTOM_SECTION, type CustomSectionDraft } from "@/components/scene/member-spec-editor";
import type {
  CustomSectionDefinition,
  FoundationDesignSpecification,
  MemberSpecification,
  SceneGraphTemplate,
  SectionCatalogEntry,
} from "@/lib/types";

type GraphNode = SceneGraphTemplate["nodes"][number];

export const STEEL_MEMBER_MODULES = ["steel_beam", "steel_column", "portal_frame", "continuous_beam", "planar_frame"];
export const FOOTING_MODULES = ["spread_footing", "strip_footing"];

const DEFAULT_REINFORCEMENT = {
  bottom_x_diameter_mm: 14,
  bottom_x_spacing_mm: 150,
  bottom_y_diameter_mm: 14,
  bottom_y_spacing_mm: 150,
};

function memberRoles(calculationModule: string | undefined): string[] {
  if (["portal_frame", "planar_frame"].includes(calculationModule ?? "")) return ["beam", "column"];
  return [["steel_beam", "continuous_beam"].includes(calculationModule ?? "") ? "beam" : "column"];
}

function recommendedMember(
  node: GraphNode,
  role: string,
  sections: SectionCatalogEntry[],
  parameters: Record<string, unknown>,
): MemberSpecification {
  const preferred =
    sections.find((item) => item.id === (role === "column" ? "shs-150x6" : "rhs-200x100x6")) ?? sections[0];
  const length = Number(
    role === "column"
      ? parameters.height_m ?? parameters.column_height_m ?? 3
      : parameters.span_m ?? parameters.length_m ?? 5,
  );
  return {
    node_id: node.id,
    member_role: role,
    material_grade: "Q355B",
    section_catalog_id: preferred.id,
    section_type: preferred.family,
    section_name: preferred.designation,
    orientation: "strong_axis",
    effective_length_m: length,
    unbraced_length_m: length,
    selection_source: "recommended",
  };
}

function recommendedFoundation(node: GraphNode): FoundationDesignSpecification {
  const strip = node.calculation_module === "strip_footing";
  return {
    node_id: node.id,
    foundation_system_id: strip ? "strip" : "spread",
    selection_source: "recommended",
    length_m: strip ? 1 : 2,
    width_m: strip ? 1.2 : 2,
    thickness_mm: strip ? 400 : 500,
    embedment_m: 1,
    concrete_grade: "C30",
    rebar_grade: "HRB400",
    bar_diameter_mm: 14,
    bar_spacing_mm: 150,
    plan_shape: "rectangular",
    section_shape: node.calculation_module === "spread_footing" ? "stepped" : "prismatic",
    steps: node.calculation_module === "spread_footing" ? [{ length_m: 1.2, width_m: 1.2, height_mm: 250 }] : [],
    pedestal: { enabled: false },
    reinforcement: DEFAULT_REINFORCEMENT,
  };
}

function withFoundationDefaults(item: FoundationDesignSpecification): FoundationDesignSpecification {
  return {
    ...item,
    concrete_grade: item.concrete_grade ?? "C30",
    rebar_grade: item.rebar_grade ?? "HRB400",
    bar_diameter_mm: item.bar_diameter_mm ?? 14,
    bar_spacing_mm: item.bar_spacing_mm ?? 150,
    section_shape: item.section_shape ?? "stepped",
    reinforcement: item.reinforcement ?? DEFAULT_REINFORCEMENT,
  };
}

/**
 * Member and foundation specifications of a legacy scene plus the project's
 * custom section catalog. Specifications are generated for every steel and
 * footing node of the graph; existing (saved or edited) entries are kept.
 */
export function useSceneSpecifications({
  visibleNodes,
  parameters,
  selectedProject,
  onError,
}: {
  visibleNodes: GraphNode[];
  parameters: Record<string, unknown>;
  selectedProject: number | "new";
  onError: (message: string) => void;
}) {
  const [steelSections, setSteelSections] = useState<SectionCatalogEntry[]>([]);
  const [customSections, setCustomSections] = useState<CustomSectionDefinition[]>([]);
  const [customSectionOpen, setCustomSectionOpen] = useState(false);
  const [customSectionDraft, setCustomSectionDraft] = useState<CustomSectionDraft>(INITIAL_CUSTOM_SECTION);
  const [customSectionPreview, setCustomSectionPreview] = useState<CustomSectionDefinition | null>(null);
  const [creatingSection, setCreatingSection] = useState(false);
  const [memberSpecifications, setMemberSpecifications] = useState<MemberSpecification[]>([]);
  const [foundationSpecifications, setFoundationSpecifications] = useState<FoundationDesignSpecification[]>([]);

  const availableSections = useMemo<SectionCatalogEntry[]>(
    () => [
      ...steelSections,
      ...customSections.map((item) => ({
        id: item.id,
        family: item.family,
        designation: `${item.name}（项目自定义）`,
        dimensions: item.dimensions,
        area_mm2: item.area_mm2,
        self_weight_kn_m: item.self_weight_kn_m,
        material_grades: ["Q235B", "Q355B"],
        source_reference: item.source_reference,
      })),
    ],
    [customSections, steelSections],
  );

  useEffect(() => {
    api<{ items: SectionCatalogEntry[] }>("/api/v2/catalogs/steel-sections")
      .then((catalog) => setSteelSections(catalog.items))
      .catch(() => setSteelSections([]));
  }, []);

  useEffect(() => {
    if (selectedProject === "new") {
      setCustomSections([]);
      return;
    }
    api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${selectedProject}/custom-sections`)
      .then((result) => setCustomSections(result.items))
      .catch(() => setCustomSections([]));
  }, [selectedProject]);

  const { name, family, dimensions, cornerRadius } = customSectionDraft;
  useEffect(() => {
    if (!customSectionOpen || !name.trim()) return;
    let active = true;
    const timer = window.setTimeout(() => {
      api<CustomSectionDefinition>("/api/v2/catalogs/custom-section-properties", {
        method: "POST",
        body: JSON.stringify({
          id: "custom-preview",
          name: name.trim(),
          family,
          dimensions,
          corner_radius_mm: cornerRadius === "" ? null : cornerRadius,
          source_reference: "用户几何实时计算预览",
        }),
      })
        .then((value) => {
          if (active) setCustomSectionPreview(value);
        })
        .catch(() => {
          if (active) setCustomSectionPreview(null);
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [cornerRadius, dimensions, family, name, customSectionOpen]);

  const { height_m, column_height_m, span_m, length_m } = parameters;
  useEffect(() => {
    if (!availableSections.length) return;
    const lengths = { height_m, column_height_m, span_m, length_m };
    const steelNodes = visibleNodes.filter((node) => STEEL_MEMBER_MODULES.includes(node.calculation_module ?? ""));
    setMemberSpecifications((current) => {
      const currentByKey = new Map(current.map((item) => [`${item.node_id}:${item.member_role}`, item]));
      return steelNodes.flatMap((node) =>
        memberRoles(node.calculation_module).map(
          (role) => currentByKey.get(`${node.id}:${role}`) ?? recommendedMember(node, role, availableSections, lengths),
        ),
      );
    });
  }, [availableSections, visibleNodes, height_m, column_height_m, span_m, length_m]);

  useEffect(() => {
    const nodes = visibleNodes.filter(
      (node) => node.role === "foundation" && FOOTING_MODULES.includes(node.calculation_module ?? ""),
    );
    setFoundationSpecifications((current) => {
      const currentByNode = new Map(current.map((item) => [item.node_id, item]));
      return nodes.map((node) => {
        const existing = currentByNode.get(node.id);
        return existing ? withFoundationDefaults(existing) : recommendedFoundation(node);
      });
    });
  }, [visibleNodes]);

  async function createCustomSection() {
    setCreatingSection(true);
    onError("");
    try {
      const created = await api<CustomSectionDefinition>("/api/v2/catalogs/custom-section-properties", {
        method: "POST",
        body: JSON.stringify({
          id: `custom-${Date.now().toString(36)}`,
          name: name.trim(),
          family,
          dimensions,
          corner_radius_mm: cornerRadius === "" ? null : cornerRadius,
          source_reference: "用户按厂家资料或实测尺寸输入；截面性质由软件根据几何计算",
        }),
      });
      setCustomSections((current) => [...current.filter((item) => item.id !== created.id), created]);
      setCustomSectionOpen(false);
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setCreatingSection(false);
    }
  }

  async function persistCustomSections(projectId: number) {
    if (!customSections.length) return;
    await api<{ items: CustomSectionDefinition[] }>(`/api/v2/projects/${projectId}/custom-sections`, {
      method: "PUT",
      body: JSON.stringify({ items: customSections }),
    });
  }

  return {
    availableSections,
    customSections,
    customSectionOpen,
    setCustomSectionOpen,
    customSectionDraft,
    setCustomSectionDraft,
    customSectionPreview,
    creatingSection,
    createCustomSection,
    persistCustomSections,
    memberSpecifications,
    setMemberSpecifications,
    foundationSpecifications,
    setFoundationSpecifications,
  };
}
