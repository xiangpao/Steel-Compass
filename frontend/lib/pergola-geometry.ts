import { FOUNDATION_TYPES, MEMBER_TYPES } from "@/lib/pergola-catalog";
import type { SceneGeometryProfile } from "@/lib/types";

export function roofHeight(x: number, y: number, xs: number[], ys: number[], directionDeg: number, ratio: number, leftSlope: number, rightSlope: number, base = 3) {
  const direction = (directionDeg * Math.PI) / 180;
  const normal = { x: -Math.sin(direction), y: Math.cos(direction) };
  const projections = xs.flatMap((px) => ys.map((py) => px * normal.x + py * normal.y));
  const min = Math.min(...projections);
  const max = Math.max(...projections);
  const ridge = min + (max - min) * ratio;
  const value = x * normal.x + y * normal.y;
  return value <= ridge ? base + Math.tan((leftSlope * Math.PI) / 180) * (value - min) : base + Math.tan((rightSlope * Math.PI) / 180) * (max - value);
}

export function initialGeometry(): SceneGeometryProfile {
  const xs = [0, 4, 8];
  const ys = [0, 3, 6];
  const nodes: SceneGeometryProfile["nodes"] = [];
  xs.forEach((x, xi) =>
    ys.forEach((y, yi) => {
      nodes.push({
        id: `B-${xi + 1}-${yi + 1}`,
        x_m: x,
        y_m: y,
        z_m: 0,
        support: "none",
        column_top: false,
      });
      nodes.push({
        id: `T-${xi + 1}-${yi + 1}`,
        x_m: x,
        y_m: y,
        z_m: roofHeight(x, y, xs, ys, 0, 0.5, 8, 8),
        support: "none",
        column_top: true,
      });
    }),
  );
  const members: SceneGeometryProfile["members"] = [];
  const member_instances: NonNullable<SceneGeometryProfile["member_instances"]> = [];
  xs.forEach((_x, xi) =>
    ys.forEach((_y, yi) => {
      const id = `C-${xi + 1}-${yi + 1}`;
      members.push({
        id,
        start_node_id: `B-${xi + 1}-${yi + 1}`,
        end_node_id: `T-${xi + 1}-${yi + 1}`,
        role: "column",
        group_id: "column",
        behavior: "frame",
        end_release: "rigid",
      });
      member_instances.push({
        member_id: id,
        member_type_id: "column",
        mark: `C${String(member_instances.filter((item) => item.member_type_id === "column").length + 1).padStart(2, "0")}`,
        source: "type",
      });
    }),
  );
  ys.forEach((_y, yi) =>
    xs.slice(0, -1).forEach((_x, xi) => {
      const id = `BX-${xi + 1}-${yi + 1}`;
      members.push({
        id,
        start_node_id: `T-${xi + 1}-${yi + 1}`,
        end_node_id: `T-${xi + 2}-${yi + 1}`,
        role: "beam",
        group_id: "x-main",
        behavior: "frame",
        end_release: "rigid",
      });
      member_instances.push({
        member_id: id,
        member_type_id: "x-main",
        mark: `X-M${String(member_instances.filter((item) => item.member_type_id === "x-main").length + 1).padStart(2, "0")}`,
        source: "type",
      });
    }),
  );
  xs.forEach((_x, xi) =>
    ys.slice(0, -1).forEach((_y, yi) => {
      const id = `BY-${xi + 1}-${yi + 1}`;
      members.push({
        id,
        start_node_id: `T-${xi + 1}-${yi + 1}`,
        end_node_id: `T-${xi + 1}-${yi + 2}`,
        role: "beam",
        group_id: "y-main",
        behavior: "frame",
        end_release: "rigid",
      });
      member_instances.push({
        member_id: id,
        member_type_id: "y-main",
        mark: `Y-M${String(member_instances.filter((item) => item.member_type_id === "y-main").length + 1).padStart(2, "0")}`,
        source: "type",
      });
    }),
  );
  const supports = xs.flatMap((_x, xi) =>
    ys.map((_y, yi) => ({
      id: `SUP-B-${xi + 1}-${yi + 1}`,
      node_id: `B-${xi + 1}-${yi + 1}`,
      restraint: "fixed" as const,
      foundation_id: `FI-${xi + 1}-${yi + 1}`,
    })),
  );
  const foundation_instances = supports.map((support, index) => {
    const isEnd = index === 0 || index === supports.length - 1;
    const type = isEnd ? FOUNDATION_TYPES[1] : FOUNDATION_TYPES[0];
    const typeIndex = supports.slice(0, index + 1).filter((_item, itemIndex) => (itemIndex === 0 || itemIndex === supports.length - 1) === isEnd).length;
    return {
      id: support.foundation_id!,
      support_id: support.id,
      foundation_type_id: type.id,
      mark: `${type.mark}-${String(typeIndex).padStart(2, "0")}`,
      column_member_id: `C-${Math.floor(index / ys.length) + 1}-${(index % ys.length) + 1}`,
    };
  });
  const roof_surfaces: SceneGeometryProfile["roof_surfaces"] = [];
  xs.slice(0, -1).forEach((_x, xi) =>
    ys.slice(0, -1).forEach((_y, yi) =>
      roof_surfaces.push({
        id: `R-${xi + 1}-${yi + 1}`,
        node_ids: [`T-${xi + 1}-${yi + 1}`, `T-${xi + 2}-${yi + 1}`, `T-${xi + 2}-${yi + 2}`, `T-${xi + 1}-${yi + 2}`],
        form: "double_slope",
        load_path_group_ids: ["x-main", "y-main"],
      }),
    ),
  );
  const beamColumnConnections: NonNullable<SceneGeometryProfile["connection_instances"]> = [];
  nodes
    .filter((node) => node.id.startsWith("T-"))
    .forEach((node) => {
      const column = members.find((member) => member.role === "column" && member.end_node_id === node.id);
      if (!column) return;
      members
        .filter((member) => member.role !== "column" && (member.start_node_id === node.id || member.end_node_id === node.id))
        .forEach((beam) => {
          const index = beamColumnConnections.length + 1;
          beamColumnConnections.push({
            id: `JBC-${index}`,
            mark: `J-B-${String(index).padStart(2, "0")}`,
            connection_type_id: "joint-beam-column",
            node_id: node.id,
            member_ids: [column.id, beam.id],
            status: "defined",
          });
        });
    });
  return {
    profile_version: "2.3",
    layout_mode: "free_plan",
    axes: [
      { id: "X", direction: "x", positions_m: xs },
      { id: "Y", direction: "y", positions_m: ys },
    ],
    nodes,
    members,
    member_types: MEMBER_TYPES,
    member_instances,
    supports,
    foundation_types: FOUNDATION_TYPES.map((item) => ({
      ...item,
      cover_mm: item.cover_mm ?? 50,
      steps:
        item.steps ??
        (item.form_id === "spread-stepped"
          ? [
              {
                length_m: Math.max(item.length_m - 0.5, 0.3),
                width_m: Math.max(item.width_m - 0.5, 0.3),
                height_mm: 250,
              },
            ]
          : []),
      tapered_top_length_m: item.tapered_top_length_m ?? (item.form_id === "spread-tapered" ? 0.6 : null),
      tapered_top_width_m: item.tapered_top_width_m ?? (item.form_id === "spread-tapered" ? 0.6 : null),
      tapered_height_mm: item.tapered_height_mm ?? (item.form_id === "spread-tapered" ? 300 : null),
    })),
    foundation_instances,
    roof_surfaces,
    object_marks: [],
    work_planes: [
      { id: "roof", kind: "plan", elevation_m: 3 },
      { id: "x-elevation", kind: "x_elevation" },
      { id: "y-elevation", kind: "y_elevation" },
    ],
    double_slope_rule: {
      ridge_direction_deg: 0,
      ridge_offset_ratio: 0.5,
      left_slope_deg: 8,
      right_slope_deg: 8,
    },
    connection_types: [
      {
        id: "joint-column-base",
        mark: "J-A",
        title: "钢管柱脚底板＋锚栓",
        family: "column_base",
        behavior: "rigid",
        supported_section_families: ["SHS", "RHS", "H", "I"],
        parameters: { weld_mm: 8 },
        verification_status: "unverified",
      },
      {
        id: "joint-beam-column",
        mark: "J-B",
        title: "矩形管梁柱全周焊接节点",
        family: "beam_column",
        behavior: "rigid",
        supported_section_families: ["SHS", "RHS"],
        parameters: {
          connection_form: "rhs_full_perimeter_weld",
          weld_throat_mm: 8,
          stiffener_thickness_mm: 8,
        },
        verification_status: "unverified",
      },
    ],
    connection_instances: [
      ...supports.map((support, index) => ({
        id: `JCB-${index + 1}`,
        mark: `J-A-${String(index + 1).padStart(2, "0")}`,
        connection_type_id: "joint-column-base",
        node_id: support.node_id,
        member_ids: [foundation_instances[index].column_member_id!],
        status: "defined" as const,
      })),
      ...beamColumnConnections,
    ],
    column_bases: supports.map((support, index) => ({
      id: `CB-${index + 1}`,
      column_member_id: foundation_instances[index].column_member_id!,
      support_id: support.id,
      connection_instance_id: `JCB-${index + 1}`,
      base_plate_length_mm: 360,
      base_plate_width_mm: 360,
      base_plate_thickness_mm: 24,
      anchor_grade: "5.8",
      anchor_diameter_mm: 24,
      anchor_count: 4,
      anchor_embedment_mm: 600,
      anchor_spacing_mm: 260,
      anchor_edge_mm: 50,
      anchor_head_diameter_mm: 60,
      anchor_supplementary_reinforcement_area_mm2: 0,
      anchor_cracked_concrete: true,
      weld_throat_mm: 8,
      concrete_bearing_capacity_mpa: 10,
      grout_thickness_mm: 30,
    })),
    roof_elevation: {
      kind: "double_slope",
      datum_height_m: 3,
      slope_deg: 8,
      opposite_slope_deg: 8,
      direction_deg: 0,
      ridge_start: [0, 3],
      ridge_end: [8, 3],
    },
    plan_boundary: {
      outer_points: [
        { id: "BP-1", x_m: 0, y_m: 0 },
        { id: "BP-2", x_m: 8, y_m: 0 },
        { id: "BP-3", x_m: 8, y_m: 6 },
        { id: "BP-4", x_m: 0, y_m: 6 },
      ],
      outer_segments: [
        {
          id: "BS-1",
          start_point_id: "BP-1",
          end_point_id: "BP-2",
          kind: "line",
        },
        {
          id: "BS-2",
          start_point_id: "BP-2",
          end_point_id: "BP-3",
          kind: "line",
        },
        {
          id: "BS-3",
          start_point_id: "BP-3",
          end_point_id: "BP-4",
          kind: "line",
        },
        {
          id: "BS-4",
          start_point_id: "BP-4",
          end_point_id: "BP-1",
          kind: "line",
        },
      ],
      source: "QA 亭廊初始轴网",
    },
    roof_openings: [],
    roof_load_zones: roof_surfaces.map((surface) => ({
      id: `Z-${surface.id}`,
      surface_id: surface.id,
      boundary_node_ids: surface.node_ids,
      roof_assembly_id: "steel-panel",
      load_path_group_ids: surface.load_path_group_ids,
    })),
    source: "QA 亭廊工作台 2.3",
  };
}
