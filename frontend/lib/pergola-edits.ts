// Pure edit operations on a pergola Geometry 2.3 profile. Each takes the
// current geometry and returns the next one; the workbench applies them
// through setGeometry and shows its own status message.

import { roofHeight } from "@/lib/pergola-geometry";
import type { FoundationDesignSpecification, FoundationTypeDefinition, MemberTypeDefinition, SceneGeometryProfile } from "@/lib/types";

type Geometry = SceneGeometryProfile;
type Pedestal = NonNullable<FoundationTypeDefinition["pedestal"]>;
type ColumnBase = NonNullable<Geometry["column_bases"]>[number];
type Restraint = "pinned" | "fixed" | "spring";

const PINNED_RELEASE = { ux: false, uy: false, uz: false, rx: false, ry: true, rz: true };
const RIGID_RELEASE = { ux: false, uy: false, uz: false, rx: false, ry: false, rz: false };

export function typeLetter(index: number) {
  return String.fromCharCode(65 + index);
}

function releaseFor(endRelease: string | undefined) {
  return endRelease === "pinned" ? PINNED_RELEASE : endRelease === "rigid" ? RIGID_RELEASE : null;
}

export function updateNode(geometry: Geometry, id: string, values: Partial<Geometry["nodes"][number]>): Geometry {
  return { ...geometry, nodes: geometry.nodes.map((item) => (item.id === id ? { ...item, ...values } : item)) };
}

export function updateMemberType(geometry: Geometry, typeId: string, values: Partial<MemberTypeDefinition>): Geometry {
  const release = releaseFor(values.end_release);
  const touchesMembers = release !== null || values.orientation !== undefined;
  return {
    ...geometry,
    member_types: (geometry.member_types ?? []).map((item) => (item.id === typeId ? { ...item, ...values } : item)),
    members: !touchesMembers
      ? geometry.members
      : geometry.members.map((item) =>
          item.group_id !== typeId
            ? item
            : {
                ...item,
                ...(release === null ? {} : { end_release: values.end_release!, start_release: release, end_release_dofs: release }),
                ...(values.orientation === undefined || !item.design_parameters
                  ? {}
                  : {
                      design_parameters: {
                        ...item.design_parameters,
                        local_axis_rotation_deg: values.orientation === "weak_axis" ? 90 : 0,
                      },
                    }),
              },
        ),
  };
}

/** Reassign one member to another member type; returns null when the type does not exist. */
export function assignMemberType(geometry: Geometry, memberId: string, typeId: string): { geometry: Geometry; type: MemberTypeDefinition } | null {
  const type = geometry.member_types?.find((item) => item.id === typeId);
  if (!type) return null;
  const index = (geometry.member_instances ?? []).filter((item) => item.member_type_id === typeId).length + 1;
  const release = type.end_release === "pinned" ? PINNED_RELEASE : RIGID_RELEASE;
  return {
    type,
    geometry: {
      ...geometry,
      members: geometry.members.map((item) =>
        item.id === memberId
          ? { ...item, group_id: typeId, role: type.role, end_release: type.end_release, start_release: release, end_release_dofs: release }
          : item,
      ),
      member_instances: (geometry.member_instances ?? []).map((item) =>
        item.member_id === memberId
          ? { ...item, member_type_id: typeId, mark: `${type.mark_prefix}${String(index).padStart(2, "0")}` }
          : item,
      ),
    },
  };
}

export function updateRoof(geometry: Geometry, values: Partial<NonNullable<Geometry["double_slope_rule"]>>) {
  const rule = {
    ...(geometry.double_slope_rule ?? { ridge_direction_deg: 0, ridge_offset_ratio: 0.5, left_slope_deg: 8, right_slope_deg: 8 }),
    ...values,
  };
  const isTop = (item: Geometry["nodes"][number]) => item.column_top || item.id.startsWith("T-");
  const topNodes = geometry.nodes.filter(isTop);
  const xs = topNodes.map((item) => item.x_m);
  const ys = topNodes.map((item) => item.y_m);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const center = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
  const angle = (rule.ridge_direction_deg * Math.PI) / 180;
  const length = Math.hypot(maxX - minX, maxY - minY) * 0.75;
  const ridgeStart: [number, number] = [center.x - Math.cos(angle) * length, center.y - Math.sin(angle) * length];
  const ridgeEnd: [number, number] = [center.x + Math.cos(angle) * length, center.y + Math.sin(angle) * length];
  return {
    rule,
    apply: (current: Geometry): Geometry => ({
      ...current,
      nodes: current.nodes.map((item) =>
        isTop(item)
          ? {
              ...item,
              z_m: roofHeight(item.x_m, item.y_m, xs, ys, rule.ridge_direction_deg, rule.ridge_offset_ratio, rule.left_slope_deg, rule.right_slope_deg),
            }
          : item,
      ),
      double_slope_rule: rule,
      roof_elevation: {
        kind: "double_slope",
        datum_height_m: 3,
        slope_deg: rule.left_slope_deg,
        opposite_slope_deg: rule.right_slope_deg,
        direction_deg: rule.ridge_direction_deg,
        ridge_start: ridgeStart,
        ridge_end: ridgeEnd,
      },
    }),
  };
}

export function updateFoundationType(geometry: Geometry, typeId: string, values: Partial<FoundationTypeDefinition>): Geometry {
  return {
    ...geometry,
    foundation_types: (geometry.foundation_types ?? []).map((item) => {
      if (item.id !== typeId) return item;
      const merged = { ...item, ...values };
      if (values.form_id === "spread-stepped" && !merged.steps?.length) {
        merged.steps = [{ length_m: Math.max(merged.length_m - 0.5, 0.3), width_m: Math.max(merged.width_m - 0.5, 0.3), height_mm: 250 }];
      }
      if (values.form_id === "spread-tapered") {
        merged.tapered_top_length_m ??= 0.6;
        merged.tapered_top_width_m ??= 0.6;
        merged.tapered_height_mm ??= 300;
      }
      return merged;
    }),
  };
}

export function updatePedestal(geometry: Geometry, typeId: string, values: Partial<Pedestal>): Geometry {
  return {
    ...geometry,
    foundation_types: (geometry.foundation_types ?? []).map((item) =>
      item.id === typeId
        ? {
            ...item,
            pedestal: { enabled: false, auto_enabled: true, splice_type: "lap", top_local_reinforcement: false, ...(item.pedestal ?? {}), ...values },
          }
        : item,
    ),
  };
}

export function updateColumnBase(geometry: Geometry, id: string, values: Partial<ColumnBase>): Geometry {
  return { ...geometry, column_bases: (geometry.column_bases ?? []).map((item) => (item.id === id ? { ...item, ...values } : item)) };
}

export function updateSupport(geometry: Geometry, id: string, restraint: Restraint): Geometry {
  return {
    ...geometry,
    supports: (geometry.supports ?? []).map((item) =>
      item.id === id
        ? {
            ...item,
            restraint,
            restrained_dofs: restraint === "fixed" ? ["ux", "uy", "uz", "rx", "ry", "rz"] : restraint === "pinned" ? ["ux", "uy", "uz"] : [],
            spring_stiffness: restraint === "spring" ? { ux: 10000, uy: 10000, uz: 50000 } : {},
          }
        : item,
    ),
  };
}

export function updateSpringStiffness(geometry: Geometry, id: string, axis: "ux" | "uy" | "uz", value: number): Geometry {
  return {
    ...geometry,
    supports: (geometry.supports ?? []).map((item) =>
      item.id === id ? { ...item, spring_stiffness: { ...item.spring_stiffness, [axis]: value } } : item,
    ),
  };
}

export function assignFoundationType(geometry: Geometry, foundationId: string, typeId: string): Geometry {
  return {
    ...geometry,
    foundation_instances: (geometry.foundation_instances ?? []).map((item) =>
      item.id === foundationId ? { ...item, foundation_type_id: typeId } : item,
    ),
  };
}

/** Copy the foundation's type into a new type used only by that foundation. */
export function detachFoundation(geometry: Geometry, foundationId: string, type: FoundationTypeDefinition) {
  const nextIndex = geometry.foundation_types?.length ?? 0;
  const mark = `F-${typeLetter(nextIndex)}`;
  const id = `foundation-${typeLetter(nextIndex).toLowerCase()}`;
  return {
    mark,
    apply: (current: Geometry): Geometry => ({
      ...current,
      foundation_types: [...(current.foundation_types ?? []), { ...type, id, mark, title: `${type.title}（独立调整）` }],
      foundation_instances: (current.foundation_instances ?? []).map((item) =>
        item.id === foundationId ? { ...item, foundation_type_id: id, mark: `${mark}-01` } : item,
      ),
    }),
  };
}

/** Merge foundation types with identical geometry, materials and reinforcement. */
export function autoClassifyFoundations(geometry: Geometry) {
  const types = geometry.foundation_types ?? [];
  const signature = (item: FoundationTypeDefinition) =>
    [
      item.form_id, item.length_m, item.width_m, item.thickness_mm, item.embedment_m, item.concrete_grade, item.rebar_grade,
      item.bottom_x, item.bottom_y, item.top_x ?? null, item.top_y ?? null, item.cover_mm, JSON.stringify(item.steps ?? []),
      item.tapered_top_length_m, item.tapered_top_width_m, item.tapered_height_mm, JSON.stringify(item.pedestal ?? null),
    ].join("|");
  const canonical = new Map<string, FoundationTypeDefinition>();
  types.forEach((item) => {
    if (!canonical.has(signature(item))) canonical.set(signature(item), item);
  });
  const kept = [...canonical.values()].map((item, index) => ({ ...item, mark: `F-${typeLetter(index)}` }));
  const map = new Map(types.map((item) => [item.id, kept.find((candidate) => signature(candidate) === signature(item))!]));
  const counters = new Map<string, number>();
  const instances = (geometry.foundation_instances ?? []).map((item) => {
    const target = map.get(item.foundation_type_id)!;
    const count = (counters.get(target.id) ?? 0) + 1;
    counters.set(target.id, count);
    return { ...item, foundation_type_id: target.id, mark: `${target.mark}-${String(count).padStart(2, "0")}` };
  });
  return { count: kept.length, geometry: { ...geometry, foundation_types: kept, foundation_instances: instances } };
}

const BEAM_COLUMN_TYPE = {
  id: "joint-beam-column",
  mark: "J-B",
  title: "矩形管梁柱全周焊接节点",
  family: "beam_column" as const,
  behavior: "rigid" as const,
  supported_section_families: ["SHS", "RHS"],
  parameters: { connection_form: "rhs_full_perimeter_weld", weld_throat_mm: 8, stiffener_thickness_mm: 8 },
  verification_status: "unverified" as const,
};

/** Add J-B connections where a column and a beam meet at one node; existing ones are kept. */
export function completeBeamColumnConnections(current: Geometry): Geometry {
  const typeId = BEAM_COLUMN_TYPE.id;
  const connectionTypes = current.connection_types?.some((item) => item.id === typeId)
    ? (current.connection_types ?? [])
    : [...(current.connection_types ?? []), BEAM_COLUMN_TYPE];
  const existing = [...(current.connection_instances ?? [])];
  const signatures = new Set(existing.map((item) => `${item.node_id}:${[...item.member_ids].sort().join("+")}`));
  let nextIndex = existing.filter((item) => item.connection_type_id === typeId).length + 1;
  current.nodes.forEach((node) => {
    const connected = current.members.filter((member) => member.start_node_id === node.id || member.end_node_id === node.id);
    const column = connected.find((member) => member.role === "column");
    if (!column) return;
    connected
      .filter((member) => member.role !== "column")
      .forEach((beam) => {
        const signature = `${node.id}:${[column.id, beam.id].sort().join("+")}`;
        if (signatures.has(signature)) return;
        existing.push({
          id: `JBC-${nextIndex}`,
          mark: `J-B-${String(nextIndex).padStart(2, "0")}`,
          connection_type_id: typeId,
          node_id: node.id,
          member_ids: [column.id, beam.id],
          status: "defined",
        });
        signatures.add(signature);
        nextIndex += 1;
      });
  });
  return { ...current, connection_types: connectionTypes, connection_instances: existing };
}

/** Foundation specification per support, used by the 3D preview. */
export function foundationsBySupportId(geometry: Geometry): Record<string, FoundationDesignSpecification> {
  return Object.fromEntries(
    (geometry.foundation_instances ?? []).flatMap((instance) => {
      const type = geometry.foundation_types?.find((item) => item.id === instance.foundation_type_id);
      if (!type) return [];
      const tapered = type.form_id.includes("tapered");
      const stepped = type.form_id.includes("stepped");
      const pedestal = type.pedestal;
      const specification: FoundationDesignSpecification = {
        node_id: instance.id,
        foundation_system_id: "spread",
        selection_source: "user_locked",
        length_m: type.length_m,
        width_m: type.width_m,
        thickness_mm: type.thickness_mm,
        embedment_m: type.embedment_m,
        concrete_grade: type.concrete_grade,
        rebar_grade: type.rebar_grade,
        bar_diameter_mm: 14,
        bar_spacing_mm: 150,
        section_shape: tapered ? "tapered" : stepped ? "stepped" : "prismatic",
        steps: stepped ? [{ length_m: Math.max(0.5, type.length_m - 0.5), width_m: Math.max(0.5, type.width_m - 0.5), height_mm: 250 }] : [],
        tapered_top_length_m: tapered ? 0.6 : null,
        tapered_top_width_m: tapered ? 0.6 : null,
        reinforcement: { bottom_x_diameter_mm: 14, bottom_x_spacing_mm: 150, bottom_y_diameter_mm: 12, bottom_y_spacing_mm: 150 },
        pedestal: pedestal
          ? {
              enabled: pedestal.enabled,
              length_mm: pedestal.length_mm,
              width_mm: pedestal.width_mm,
              height_mm: pedestal.clear_height_mm,
              longitudinal_bar_count: (pedestal.longitudinal_bar_count_x ?? 0) * 2 + (pedestal.longitudinal_bar_count_y ?? 0) * 2,
              longitudinal_bar_diameter_mm: pedestal.longitudinal_bar_diameter_mm,
              stirrup_diameter_mm: pedestal.stirrup_diameter_mm,
              stirrup_spacing_mm: pedestal.stirrup_spacing_mm,
            }
          : null,
        override_reason: "QA 工作台显式基础类型",
      };
      return [[instance.support_id, specification]];
    }),
  );
}
