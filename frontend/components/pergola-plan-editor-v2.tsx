"use client";

import {
  Anchor,
  BetweenHorizontalStart,
  BoxSelect,
  CirclePlus,
  Columns3,
  Focus,
  Maximize2,
  Minus,
  MousePointer2,
  PenLine,
  Plus,
  Ruler,
  RotateCcw,
  RotateCw,
  Trash2,
  Waves,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, Layer, Line, Rect, Stage, Text } from "react-konva";
import type { KonvaEventObject } from "konva/lib/Node";

import type { SceneGeometryProfile } from "@/lib/types";

export type WorkbenchSelection = {
  kind: "node" | "member" | "foundation" | "support" | "boundary_segment";
  id: string;
} | null;

export type OrthographicView = "plan" | "x_elevation" | "y_elevation";
type Tool = "select" | "node" | "beam" | "column" | "support" | "boundary" | "arc" | "measure" | "box_zoom" | "delete";

type Props = {
  geometry: SceneGeometryProfile;
  selection: WorkbenchSelection;
  view: OrthographicView;
  workElevation: number;
  activeMemberTypeId: string;
  onSelectionChange: (value: WorkbenchSelection) => void;
  onGeometryChange: (value: SceneGeometryProfile) => void;
  onMessage: (value: string) => void;
};

const BASE_SCALE = 56;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

const TOOL_HELP: Record<Tool, { label: string; description: string; next: string }> = {
  select: { label: "选择", description: "选择节点、构件或基础并在左侧精确编辑。", next: "点击对象；空白处拖动画布。" },
  node: { label: "节点", description: "在当前视图和工作标高建立结构节点。", next: "点击图面放置节点。" },
  beam: { label: "梁", description: "在两个节点之间增加当前类型的梁、檩条或龙骨。", next: "依次点击起点和终点。" },
  column: { label: "柱", description: "在平面位置增加柱、柱脚支承和基础实例。", next: "点击平面位置放置柱。" },
  support: { label: "支承", description: "只给节点设置约束，不自动创建基础。", next: "点击节点设置支承；属性栏可修改约束类型。" },
  boundary: { label: "边界", description: "绘制屋面平面边界；靠近起点时闭合。", next: "连续点击边界点，最后点击起点。" },
  arc: { label: "圆弧", description: "把指定边界段改为三点圆弧。", next: "先点边界段，再点弧上第三点，最后点应用。" },
  measure: { label: "测距", description: "测量两个图面点之间的实际距离。", next: "依次点击两个位置。" },
  box_zoom: { label: "框选缩放", description: "框选需要放大的模型范围。", next: "拖出矩形范围。" },
  delete: { label: "删除", description: "直接点击要删除的构件、节点、支承或基础。", next: "点击对象删除；可用撤销恢复。" },
};

function nextId(prefix: string, ids: string[]) {
  let value = ids.length + 1;
  while (ids.includes(`${prefix}${value}`)) value += 1;
  return `${prefix}${value}`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function PergolaPlanEditorV2({
  geometry,
  selection,
  view,
  workElevation,
  activeMemberTypeId,
  onSelectionChange,
  onGeometryChange,
  onMessage,
}: Props) {
  const shellRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 620, height: 620 });
  const [tool, setTool] = useState<Tool>("select");
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 48, y: 48 });
  const [beamStart, setBeamStart] = useState<{ nodeId: string | null; point: { x_m: number; y_m: number; z_m: number } } | null>(null);
  const [measureStart, setMeasureStart] = useState<{ u: number; v: number } | null>(null);
  const [measureEnd, setMeasureEnd] = useState<{ u: number; v: number } | null>(null);
  const [boundaryDraft, setBoundaryDraft] = useState<Array<{ x_m: number; y_m: number }>>([]);
  const [arcDraft, setArcDraft] = useState<{ segmentId: string; mid: { x_m: number; y_m: number } | null } | null>(null);
  const [history, setHistory] = useState<SceneGeometryProfile[]>([]);
  const [future, setFuture] = useState<SceneGeometryProfile[]>([]);
  const [spacePressed, setSpacePressed] = useState(false);
  const [boxStart, setBoxStart] = useState<{ x: number; y: number } | null>(null);
  const [boxCurrent, setBoxCurrent] = useState<{ x: number; y: number } | null>(null);
  const [cursorPlane, setCursorPlane] = useState<{ u: number; v: number } | null>(null);
  const panRef = useRef<{ pointer: { x: number; y: number }; offset: { x: number; y: number } } | null>(null);
  const pinchRef = useRef<{ distance: number; zoom: number; offset: { x: number; y: number }; center: { x: number; y: number } } | null>(null);
  const gestureMovedRef = useRef(false);

  useEffect(() => {
    const element = shellRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.max(360, entry.contentRect.width), height: Math.max(460, entry.contentRect.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.code === "Space" && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        setSpacePressed(true);
      }
      if (event.key === "Escape") {
        setBeamStart(null);
        setMeasureStart(null);
        setBoundaryDraft([]);
        setArcDraft(null);
        setBoxStart(null);
        setBoxCurrent(null);
        panRef.current = null;
        setTool("select");
        onMessage("已取消当前工具，返回选择状态。");
      }
      if (event.key === "Backspace" && boundaryDraft.length && !(event.target instanceof HTMLInputElement)) {
        event.preventDefault();
        setBoundaryDraft((items) => items.slice(0, -1));
        onMessage("已撤销当前边界草稿的最后一点。");
      }
      if (event.key === "Delete" && selection && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        deleteObject(selection);
      }
      if (event.key === "Enter" && tool === "boundary" && boundaryDraft.length >= 3) {
        event.preventDefault();
        finishBoundary();
      }
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") setSpacePressed(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [boundaryDraft, onMessage, tool]); // eslint-disable-line react-hooks/exhaustive-deps

  const nodeById = useMemo(() => new Map(geometry.nodes.map((node) => [node.id, node])), [geometry.nodes]);
  const project = (node: SceneGeometryProfile["nodes"][number]) => {
    if (view === "x_elevation") return { u: node.x_m, v: node.z_m };
    if (view === "y_elevation") return { u: node.y_m, v: node.z_m };
    return { u: node.x_m, v: node.y_m };
  };
  const projected = geometry.nodes.map(project);
  const stageHeight = Math.max(360, size.height - 94);
  const bounds = useMemo(() => {
    const us = projected.map((item) => item.u);
    const vs = projected.map((item) => item.v);
    return {
      minU: Math.min(...us, 0), maxU: Math.max(...us, 1),
      minV: Math.min(...vs, 0), maxV: Math.max(...vs, 1),
    };
  }, [projected]);
  const toScreen = (u: number, v: number) => ({
    x: offset.x + (u - bounds.minU) * BASE_SCALE * zoom,
    y: offset.y + (bounds.maxV - v) * BASE_SCALE * zoom,
  });
  const toModelPlane = (x: number, y: number) => ({
    u: (x - offset.x) / (BASE_SCALE * zoom) + bounds.minU,
    v: bounds.maxV - (y - offset.y) / (BASE_SCALE * zoom),
  });

  function commit(next: SceneGeometryProfile, message: string) {
    setHistory((items) => [...items.slice(-29), geometry]);
    setFuture([]);
    onGeometryChange(next);
    onMessage(message);
  }

  function finishBoundary() {
    if (boundaryDraft.length < 3) return onMessage("边界至少需要三个点。");
    const outer_points = boundaryDraft.map((item, index) => ({ id: `BP-${index + 1}`, ...item }));
    const outer_segments = outer_points.map((item, index) => ({ id: `BS-${index + 1}`, start_point_id: item.id, end_point_id: outer_points[(index + 1) % outer_points.length].id, kind: "line" as const }));
    setBoundaryDraft([]);
    setTool("select");
    commit({ ...geometry, plan_boundary: { outer_points, outer_segments, source: "QA 二维工作台" } }, "屋面荷载边界已闭合；它不会自动变成钢梁。");
  }

  function fitAll() {
    const width = Math.max(bounds.maxU - bounds.minU, 1);
    const height = Math.max(bounds.maxV - bounds.minV, 1);
    const availableWidth = Math.max(size.width - 96, 120);
    const availableHeight = Math.max(stageHeight - 72, 120);
    const nextZoom = clamp(Math.min(availableWidth / (width * BASE_SCALE), availableHeight / (height * BASE_SCALE)), MIN_ZOOM, MAX_ZOOM);
    setZoom(nextZoom);
    setOffset({ x: Math.max(40, (size.width - width * BASE_SCALE * nextZoom) / 2), y: Math.max(34, (stageHeight - height * BASE_SCALE * nextZoom) / 2) });
    onMessage(`已显示全部，当前缩放 ${Math.round(nextZoom * 100)}%。`);
  }

  useEffect(() => {
    fitAll(); /* model/view switch and resized split panes should remain visible */
  }, [view, size.width, size.height]); // eslint-disable-line react-hooks/exhaustive-deps

  function setActiveTool(next: Tool) {
    setBoundaryDraft([]);
    setArcDraft(null);
    setTool(next);
    setBeamStart(null);
    setMeasureStart(null);
    onMessage(`${TOOL_HELP[next].label}：${TOOL_HELP[next].next}`);
  }

  function modelPointFromPlane(u: number, v: number) {
    if (view === "x_elevation") return { x_m: u, y_m: 0, z_m: v };
    if (view === "y_elevation") return { x_m: 0, y_m: u, z_m: v };
    return { x_m: u, y_m: v, z_m: workElevation };
  }

  function nearestNode(u: number, v: number) {
    return geometry.nodes
      .map((node) => ({ node, point: project(node) }))
      .map(({ node, point }) => ({ node, distance: Math.hypot(point.u - u, point.v - v) }))
      .sort((a, b) => a.distance - b.distance)[0];
  }

  function nearestMember(u: number, v: number) {
    return geometry.members.map((member) => {
      const start = nodeById.get(member.start_node_id);
      const end = nodeById.get(member.end_node_id);
      if (!start || !end) return { member, distance: Number.POSITIVE_INFINITY, t: 0 };
      const a = project(start); const b = project(end);
      const dx = b.u - a.u; const dy = b.v - a.v;
      const length2 = dx * dx + dy * dy;
      const t = length2 ? clamp(((u - a.u) * dx + (v - a.v) * dy) / length2, 0, 1) : 0;
      return { member, distance: Math.hypot(u - (a.u + t * dx), v - (a.v + t * dy)), t };
    }).sort((a, b) => a.distance - b.distance)[0];
  }

  function materializeNode(base: SceneGeometryProfile, u: number, v: number) {
    const nearNode = nearestNode(u, v);
    if (nearNode?.distance < 0.16) return { geometry: base, nodeId: nearNode.node.id };
    const nearMember = nearestMember(u, v);
    if (nearMember && nearMember.distance < 0.14 && nearMember.t > 0.03 && nearMember.t < 0.97) {
      const member = base.members.find((item) => item.id === nearMember.member.id)!;
      const start = base.nodes.find((item) => item.id === member.start_node_id)!;
      const end = base.nodes.find((item) => item.id === member.end_node_id)!;
      const nodeId = nextId("N-", base.nodes.map((item) => item.id));
      const node = {
        id: nodeId,
        x_m: start.x_m + nearMember.t * (end.x_m - start.x_m),
        y_m: start.y_m + nearMember.t * (end.y_m - start.y_m),
        z_m: start.z_m + nearMember.t * (end.z_m - start.z_m),
        support: "none" as const,
        column_top: false,
      };
      const secondId = nextId(`${member.id}-`, base.members.map((item) => item.id));
      const first = { ...member, end_node_id: nodeId };
      const second = { ...member, id: secondId, start_node_id: nodeId };
      const assignment = base.member_instances?.find((item) => item.member_id === member.id);
      const instances = assignment
        ? [...(base.member_instances ?? []).map((item) => item.member_id === member.id ? { ...item, member_id: member.id } : item), { ...assignment, member_id: secondId, mark: `${assignment.mark}-B` }]
        : base.member_instances;
      return { geometry: { ...base, nodes: [...base.nodes, node], members: base.members.flatMap((item) => item.id === member.id ? [first, second] : [item]), member_instances: instances }, nodeId };
    }
    const nodeId = nextId("N-", base.nodes.map((item) => item.id));
    return { geometry: { ...base, nodes: [...base.nodes, { id: nodeId, ...modelPointFromPlane(u, v), support: "none" as const, column_top: false }] }, nodeId };
  }

  function setNodeSupport(nodeId: string) {
    const existing = (geometry.supports ?? []).find((item) => item.node_id === nodeId);
    if (existing) {
      onSelectionChange({ kind: "support", id: existing.id });
      return onMessage(`节点 ${nodeId} 已有 ${existing.restraint === "fixed" ? "固定" : existing.restraint === "pinned" ? "铰接" : "弹簧"}支承。`);
    }
    const node = nodeById.get(nodeId);
    if (node && node.z_m > 0.05) onMessage("警告：正在非底部节点设置支承，请确认这是真实边界条件。");
    const supportId = nextId("SUP-", (geometry.supports ?? []).map((item) => item.id));
    commit({ ...geometry, supports: [...(geometry.supports ?? []), { id: supportId, node_id: nodeId, restraint: "pinned", restrained_dofs: ["ux", "uy", "uz"], spring_stiffness: {} }] }, `已在 ${nodeId} 增加铰支承；未自动创建基础。`);
    onSelectionChange({ kind: "support", id: supportId });
  }

  function applyArcDraft() {
    if (!arcDraft?.mid || !geometry.plan_boundary) return;
    commit({ ...geometry, plan_boundary: { ...geometry.plan_boundary, outer_segments: geometry.plan_boundary.outer_segments.map((item) => item.id === arcDraft.segmentId ? { ...item, kind: "arc", arc_mid_x_m: arcDraft.mid!.x_m, arc_mid_y_m: arcDraft.mid!.y_m } : item) } }, `边界段 ${arcDraft.segmentId} 已按三点圆弧更新；分析时采用可追溯直线分段。`);
    setArcDraft(null);
    setTool("select");
  }

  function stagePointer(event: KonvaEventObject<MouseEvent | WheelEvent | TouchEvent>) {
    const pointer = event.target.getStage()?.getPointerPosition();
    return pointer ? { ...pointer, ...toModelPlane(pointer.x, pointer.y) } : null;
  }

  function handleStageClick(event: KonvaEventObject<MouseEvent>) {
    if (gestureMovedRef.current) {
      gestureMovedRef.current = false;
      return;
    }
    if (event.target !== event.target.getStage() && tool === "select") return;
    const point = stagePointer(event);
    if (!point) return;
    if (tool === "select") return onSelectionChange(null);
    if (tool === "measure") {
      if (!measureStart) {
        setMeasureStart({ u: point.u, v: point.v });
        setMeasureEnd(null);
        return onMessage("测距：已确定起点，请选择终点。");
      }
      setMeasureEnd({ u: point.u, v: point.v });
      const horizontal = Math.abs(point.u - measureStart.u);
      const vertical = Math.abs(point.v - measureStart.v);
      const distance = Math.hypot(horizontal, vertical);
      const angle = Math.atan2(point.v - measureStart.v, point.u - measureStart.u) * 180 / Math.PI;
      return onMessage(`测量：水平 ${horizontal.toFixed(3)}m，高差 ${vertical.toFixed(3)}m，三维/图面距离 ${distance.toFixed(3)}m，方向角 ${angle.toFixed(1)}°。`);
    }
    if (tool === "arc" && arcDraft) {
      setArcDraft({ ...arcDraft, mid: { x_m: point.u, y_m: point.v } });
      return onMessage(`圆弧：弧上点已预览；点击工具说明区的“应用”提交，Esc 取消。`);
    }
    if (tool === "arc" && view === "plan" && geometry.plan_boundary) {
      const points = new Map(geometry.plan_boundary.outer_points.map((item) => [item.id, item]));
      const nearest = geometry.plan_boundary.outer_segments.map((segment) => {
        const start = points.get(segment.start_point_id)!; const end = points.get(segment.end_point_id)!;
        const dx = end.x_m - start.x_m; const dy = end.y_m - start.y_m; const length2 = dx * dx + dy * dy;
        const t = length2 ? clamp(((point.u - start.x_m) * dx + (point.v - start.y_m) * dy) / length2, 0, 1) : 0;
        return { segment, distance: Math.hypot(point.u - (start.x_m + t * dx), point.v - (start.y_m + t * dy)) };
      }).sort((a, b) => a.distance - b.distance)[0];
      if (!nearest || nearest.distance > 0.2) return onMessage("圆弧：请先点击要修改的边界段，而不是任意空白位置。");
      setArcDraft({ segmentId: nearest.segment.id, mid: null });
      onSelectionChange({ kind: "boundary_segment", id: nearest.segment.id });
      return onMessage(`圆弧：已选择 ${nearest.segment.id}，请点击弧上第三点。`);
    }
    if (tool === "boundary" && view === "plan") {
      const next = [...boundaryDraft, { x_m: point.u, y_m: point.v }];
      if (next.length >= 4 && Math.hypot(next[0].x_m - point.u, next[0].y_m - point.v) < 0.2) {
        const closed = next.slice(0, -1);
        const outer_points = closed.map((item, index) => ({ id: `BP-${index + 1}`, ...item }));
        const outer_segments = outer_points.map((item, index) => ({ id: `BS-${index + 1}`, start_point_id: item.id, end_point_id: outer_points[(index + 1) % outer_points.length].id, kind: "line" as const }));
        setBoundaryDraft([]);
        setTool("select");
        return commit({ ...geometry, plan_boundary: { outer_points, outer_segments, source: "QA 二维工作台" } }, "屋面边界已闭合。");
      }
      setBoundaryDraft(next);
      return onMessage("边界：继续点击，最后回到起点闭合。");
    }
    const resolved = materializeNode(geometry, point.u, point.v);
    const nodeId = resolved.nodeId;
    const nextGeometry = resolved.geometry;
    if (tool === "node") {
      commit(nextGeometry, nextGeometry.members.length > geometry.members.length ? `已在杆件中插入节点 ${nodeId}，原杆件已拆分并继承属性。` : `已增加节点 ${nodeId}。`);
      return onSelectionChange({ kind: "node", id: nodeId });
    }
    if (tool === "beam") {
      if (!beamStart) {
        const node = nextGeometry.nodes.find((item) => item.id === nodeId)!;
        setBeamStart({ nodeId: nextGeometry === geometry ? nodeId : null, point: { x_m: node.x_m, y_m: node.y_m, z_m: node.z_m } });
        return onMessage(`梁：起点已预览，选择终点后一次性提交；Esc 可取消且不会留下节点。`);
      }
      let finalGeometry = nextGeometry;
      let startId = beamStart.nodeId;
      if (!startId) {
        const startPlane = view === "plan" ? { u: beamStart.point.x_m, v: beamStart.point.y_m } : view === "x_elevation" ? { u: beamStart.point.x_m, v: beamStart.point.z_m } : { u: beamStart.point.y_m, v: beamStart.point.z_m };
        const startResolved = materializeNode(finalGeometry, startPlane.u, startPlane.v);
        finalGeometry = startResolved.geometry;
        startId = startResolved.nodeId;
      }
      if (startId === nodeId) return onMessage("梁的起点和终点不能相同。");
      const type = geometry.member_types?.find((item) => item.id === activeMemberTypeId);
      const prefix = type?.mark_prefix ?? "S";
      const sameType = geometry.member_instances?.filter((item) => item.member_type_id === activeMemberTypeId) ?? [];
      const memberId = nextId("M-", finalGeometry.members.map((item) => item.id));
      const mark = `${prefix}${String(sameType.length + 1).padStart(2, "0")}`;
      const pinned = type?.end_release === "pinned";
      const member = { id: memberId, start_node_id: startId, end_node_id: nodeId, role: type?.role ?? "beam" as const, group_id: activeMemberTypeId, behavior: "frame" as const, end_release: type?.end_release ?? "rigid" as const, start_release: { ux: false, uy: false, uz: false, rx: false, ry: pinned, rz: pinned }, end_release_dofs: { ux: false, uy: false, uz: false, rx: false, ry: pinned, rz: pinned } };
      commit({ ...finalGeometry, members: [...finalGeometry.members, member], member_instances: [...(finalGeometry.member_instances ?? []), { member_id: memberId, member_type_id: activeMemberTypeId, mark, source: "type" }] }, `已增加 ${type?.title ?? "梁"} ${mark}，并完成真实拓扑连接。`);
      setBeamStart(null);
      return onSelectionChange({ kind: "member", id: memberId });
    }
    if (tool === "support") return setNodeSupport(nodeId);
    if (tool === "column" && view === "plan") {
      const topId = nodeId;
      const topNode = nextGeometry.nodes.find((item) => item.id === topId)!;
      const baseId = nextId("B-", nextGeometry.nodes.map((item) => item.id));
      const memberId = nextId("C-", nextGeometry.members.map((item) => item.id));
      const supportId = `SUP-${baseId}`;
      const foundationTypeId = nextGeometry.foundation_types?.[0]?.id ?? "foundation-a";
      const sameTypeCount = nextGeometry.foundation_instances?.filter((item) => item.foundation_type_id === foundationTypeId).length ?? 0;
      const typeMark = nextGeometry.foundation_types?.find((item) => item.id === foundationTypeId)?.mark ?? "F-A";
      const foundationId = `FI-${baseId}`;
      const connectionIndex = (nextGeometry.connection_instances ?? []).length + 1;
      const connectionId = `JCB-${connectionIndex}`;
      commit({
        ...nextGeometry,
        nodes: [...nextGeometry.nodes, { id: baseId, x_m: topNode.x_m, y_m: topNode.y_m, z_m: 0, support: "none", column_top: false }],
        members: [...nextGeometry.members, { id: memberId, start_node_id: baseId, end_node_id: topId, role: "column", group_id: "column", behavior: "frame", end_release: "rigid" }],
        member_instances: [...(nextGeometry.member_instances ?? []), { member_id: memberId, member_type_id: "column", mark: `C${String(nextGeometry.members.filter((item) => item.role === "column").length + 1).padStart(2, "0")}`, source: "type" }],
        supports: [...(nextGeometry.supports ?? []), { id: supportId, node_id: baseId, restraint: "fixed", foundation_id: foundationId }],
        foundation_instances: [...(nextGeometry.foundation_instances ?? []), { id: foundationId, support_id: supportId, foundation_type_id: foundationTypeId, mark: `${typeMark}-${String(sameTypeCount + 1).padStart(2, "0")}`, column_member_id: memberId }],
        connection_instances: [...(nextGeometry.connection_instances ?? []), { id: connectionId, mark: `J-A-${String(connectionIndex).padStart(2, "0")}`, connection_type_id: "joint-column-base", node_id: baseId, member_ids: [memberId], status: "defined" }],
        column_bases: [...(nextGeometry.column_bases ?? []), { id: `CB-${connectionIndex}`, column_member_id: memberId, support_id: supportId, connection_instance_id: connectionId, base_plate_length_mm: 360, base_plate_width_mm: 360, base_plate_thickness_mm: 24, anchor_grade: "Q355B", anchor_diameter_mm: 24, anchor_count: 4, anchor_embedment_mm: 600, grout_thickness_mm: 30 }],
      }, "已增加柱、柱脚支承和基础实例。");
      return onSelectionChange({ kind: "member", id: memberId });
    }
  }

  function handleWheel(event: KonvaEventObject<WheelEvent>) {
    event.evt.preventDefault();
    const pointer = event.target.getStage()?.getPointerPosition();
    if (!pointer) return;
    const factor = event.evt.deltaY > 0 ? 0.9 : 1.1;
    const nextZoom = clamp(zoom * factor, MIN_ZOOM, MAX_ZOOM);
    const modelX = (pointer.x - offset.x) / zoom;
    const modelY = (pointer.y - offset.y) / zoom;
    setOffset({ x: pointer.x - modelX * nextZoom, y: pointer.y - modelY * nextZoom });
    setZoom(nextZoom);
  }

  function handlePointerDown(event: KonvaEventObject<MouseEvent>) {
    const point = stagePointer(event);
    if (!point) return;
    gestureMovedRef.current = false;
    if (tool === "box_zoom" && event.evt.button === 0) {
      setBoxStart({ x: point.x, y: point.y });
      setBoxCurrent({ x: point.x, y: point.y });
      return;
    }
    const blankSelectPan = tool === "select" && event.target === event.target.getStage() && event.evt.button === 0;
    if (event.evt.button === 1 || spacePressed || blankSelectPan) {
      event.evt.preventDefault();
      panRef.current = { pointer: { x: point.x, y: point.y }, offset };
    }
  }

  function handlePointerMove(event: KonvaEventObject<MouseEvent>) {
    const point = stagePointer(event);
    if (!point) return;
    setCursorPlane({ u: point.u, v: point.v });
    if (boxStart) {
      setBoxCurrent({ x: point.x, y: point.y });
      gestureMovedRef.current = Math.hypot(point.x - boxStart.x, point.y - boxStart.y) > 4;
      return;
    }
    if (panRef.current) {
      const dx = point.x - panRef.current.pointer.x;
      const dy = point.y - panRef.current.pointer.y;
      if (Math.hypot(dx, dy) > 2) gestureMovedRef.current = true;
      setOffset({ x: panRef.current.offset.x + dx, y: panRef.current.offset.y + dy });
    }
  }

  function cancelCurrentTool() {
    setBeamStart(null);
    setMeasureStart(null);
    setMeasureEnd(null);
    setBoundaryDraft([]);
    setArcDraft(null);
    setBoxStart(null);
    setBoxCurrent(null);
    setTool("select");
    onMessage("已取消当前未提交操作；正式模型没有写入半成品对象。");
  }

  function handlePointerUp() {
    panRef.current = null;
    if (!boxStart || !boxCurrent) return;
    const boxWidth = Math.abs(boxCurrent.x - boxStart.x);
    const boxHeight = Math.abs(boxCurrent.y - boxStart.y);
    if (boxWidth > 8 && boxHeight > 8) {
      const first = toModelPlane(boxStart.x, boxStart.y);
      const second = toModelPlane(boxCurrent.x, boxCurrent.y);
      const centerU = (first.u + second.u) / 2;
      const centerV = (first.v + second.v) / 2;
      const nextZoom = clamp(zoom * Math.min((size.width - 48) / boxWidth, (stageHeight - 48) / boxHeight), MIN_ZOOM, MAX_ZOOM);
      setZoom(nextZoom);
      setOffset({
        x: size.width / 2 - (centerU - bounds.minU) * BASE_SCALE * nextZoom,
        y: stageHeight / 2 - (bounds.maxV - centerV) * BASE_SCALE * nextZoom,
      });
      onMessage(`已放大框选范围，当前缩放 ${Math.round(nextZoom * 100)}%。`);
    }
    setBoxStart(null);
    setBoxCurrent(null);
    setTool("select");
  }

  function touchPoint(touch: Touch, container: HTMLDivElement) {
    const rect = container.getBoundingClientRect();
    return { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
  }

  function handleTouchStart(event: KonvaEventObject<TouchEvent>) {
    if (event.evt.touches.length !== 2) return;
    event.evt.preventDefault();
    const container = event.target.getStage()?.container();
    if (!container) return;
    const a = touchPoint(event.evt.touches[0], container);
    const b = touchPoint(event.evt.touches[1], container);
    pinchRef.current = {
      distance: Math.hypot(a.x - b.x, a.y - b.y),
      zoom,
      offset,
      center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
    };
  }

  function handleTouchMove(event: KonvaEventObject<TouchEvent>) {
    if (!pinchRef.current || event.evt.touches.length !== 2) return;
    event.evt.preventDefault();
    const container = event.target.getStage()?.container();
    if (!container) return;
    const a = touchPoint(event.evt.touches[0], container);
    const b = touchPoint(event.evt.touches[1], container);
    const center = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const distance = Math.hypot(a.x - b.x, a.y - b.y);
    const nextZoom = clamp(pinchRef.current.zoom * distance / Math.max(pinchRef.current.distance, 1), MIN_ZOOM, MAX_ZOOM);
    const modelX = (pinchRef.current.center.x - pinchRef.current.offset.x) / pinchRef.current.zoom;
    const modelY = (pinchRef.current.center.y - pinchRef.current.offset.y) / pinchRef.current.zoom;
    setZoom(nextZoom);
    setOffset({ x: center.x - modelX * nextZoom, y: center.y - modelY * nextZoom });
    gestureMovedRef.current = true;
  }

  function handleTouchEnd() {
    pinchRef.current = null;
  }

  function moveNode(nodeId: string, screenX: number, screenY: number) {
    const point = toModelPlane(screenX, screenY);
    const nextNodes = geometry.nodes.map((node) => {
      if (node.id !== nodeId) return node;
      if (view === "x_elevation") return { ...node, x_m: point.u, z_m: point.v };
      if (view === "y_elevation") return { ...node, y_m: point.u, z_m: point.v };
      return { ...node, x_m: point.u, y_m: point.v };
    });
    commit({ ...geometry, nodes: nextNodes }, `已移动节点 ${nodeId}；坐标可在左侧继续精确输入。`);
  }

  function moveColumn(memberId: string, screenX: number, screenY: number) {
    if (view !== "plan") return;
    const member = geometry.members.find((item) => item.id === memberId);
    const start = member ? nodeById.get(member.start_node_id) : null;
    if (!member || !start) return;
    const point = toModelPlane(screenX, screenY);
    const dx = point.u - start.x_m;
    const dy = point.v - start.y_m;
    const nodeIds = new Set([member.start_node_id, member.end_node_id]);
    commit({ ...geometry, nodes: geometry.nodes.map((node) => nodeIds.has(node.id) ? { ...node, x_m: node.x_m + dx, y_m: node.y_m + dy } : node) }, `已在平面内移动柱 ${memberId}；柱高请在左侧输入。`);
  }

  function deleteObject(target: NonNullable<WorkbenchSelection>) {
    if (target.kind === "member") {
      const member = geometry.members.find((item) => item.id === target.id);
      if (!member) return;
      const base = geometry.column_bases?.find((item) => item.column_member_id === member.id);
      const foundationIds = new Set((geometry.foundation_instances ?? []).filter((item) => item.column_member_id === member.id).map((item) => item.id));
      commit({
        ...geometry,
        members: geometry.members.filter((item) => item.id !== target.id),
        member_instances: (geometry.member_instances ?? []).filter((item) => item.member_id !== target.id),
        supports: member.role === "column" ? (geometry.supports ?? []).filter((item) => item.id !== base?.support_id && !foundationIds.has(item.foundation_id ?? "")) : geometry.supports,
        foundation_instances: member.role === "column" ? (geometry.foundation_instances ?? []).filter((item) => item.column_member_id !== member.id) : geometry.foundation_instances,
        connection_instances: (geometry.connection_instances ?? []).filter((item) => !item.member_ids.includes(member.id)),
        column_bases: (geometry.column_bases ?? []).filter((item) => item.column_member_id !== member.id),
      }, member.role === "column" ? "已移除柱、对应柱脚支承和基础；柱顶节点及屋面梁保持不变。" : "已删除所选构件及关联连接实例。");
      return onSelectionChange(null);
    }
    if (target.kind === "foundation") {
      const foundation = (geometry.foundation_instances ?? []).find((item) => item.id === target.id);
      commit({
        ...geometry,
        foundation_instances: (geometry.foundation_instances ?? []).filter((item) => item.id !== target.id),
        supports: (geometry.supports ?? []).map((item) => item.id === foundation?.support_id ? { ...item, foundation_id: undefined } : item),
      }, "已删除基础实例；节点支承仍保留且已解除基础绑定。");
      return onSelectionChange(null);
    }
    if (target.kind === "support") {
      const support = (geometry.supports ?? []).find((item) => item.id === target.id);
      const foundation = (geometry.foundation_instances ?? []).find((item) => item.support_id === target.id);
      if (foundation) return onMessage(`支承 ${target.id} 仍绑定基础 ${foundation.mark}，请先删除基础实例。`);
      commit({
        ...geometry,
        supports: (geometry.supports ?? []).filter((item) => item.id !== target.id),
        column_bases: (geometry.column_bases ?? []).filter((item) => item.support_id !== target.id),
      }, `已删除支承 ${support?.id ?? target.id}；节点和构件保持不变。`);
      return onSelectionChange(null);
    }
    if (target.kind === "boundary_segment") {
      return onMessage("不能单独删除屋面边界段，否则边界会断开；请使用“边界”工具重新绘制闭合边界。");
    }
    const related = geometry.members.filter((item) => item.start_node_id === target.id || item.end_node_id === target.id);
    if (related.length) return onMessage(`节点仍连接 ${related.length} 根构件，请先删除或改接构件。`);
    const support = (geometry.supports ?? []).find((item) => item.node_id === target.id);
    if (support) return onMessage(`节点 ${target.id} 仍有支承 ${support.id}，请先删除支承。`);
    commit({ ...geometry, nodes: geometry.nodes.filter((item) => item.id !== target.id) }, `已删除节点 ${target.id}。`);
    onSelectionChange(null);
  }

  function handleObjectClick(event: KonvaEventObject<MouseEvent>, target: NonNullable<WorkbenchSelection>) {
    if (tool !== "select" && tool !== "delete") return;
    event.cancelBubble = true;
    if (tool === "delete") deleteObject(target);
    else onSelectionChange(target);
  }

  function resetView() {
    cancelCurrentTool();
    setZoom(1);
    setOffset({ x: 48, y: 48 });
    onMessage("二维视图已重置为 100%；模型数据没有改变。");
  }

  const toolItems: Array<[Tool, typeof MousePointer2]> = [
    ["select", MousePointer2], ["node", CirclePlus], ["beam", BetweenHorizontalStart], ["column", Columns3],
    ["support", Anchor], ["boundary", PenLine], ["arc", Waves], ["measure", Ruler], ["box_zoom", BoxSelect],
  ];

  return (
    <div className="qa-plan-editor" ref={shellRef} data-testid="qa-plan-editor">
      <div className="qa-canvas-toolbar" aria-label="二维模型工具">
        {toolItems.map(([value, Icon]) => (
          <button key={value} type="button" className={tool === value ? "active" : ""} aria-label={`${TOOL_HELP[value].label}：${TOOL_HELP[value].description}`} title={`${TOOL_HELP[value].description} ${TOOL_HELP[value].next}`} onClick={() => setActiveTool(value)}>
            <Icon size={16} /><span>{TOOL_HELP[value].label}</span>
          </button>
        ))}
        <span className="qa-toolbar-divider" />
        <button type="button" aria-label="缩小" onClick={() => setZoom((value) => clamp(value / 1.2, MIN_ZOOM, MAX_ZOOM))}><Minus size={16} /></button>
        <button type="button" className="zoom-readout" aria-label="恢复100%" onClick={() => { setZoom(1); setOffset({ x: 48, y: 48 }); }}>{Math.round(zoom * 100)}%</button>
        <button type="button" aria-label="放大" onClick={() => setZoom((value) => clamp(value * 1.2, MIN_ZOOM, MAX_ZOOM))}><Plus size={16} /></button>
        <button type="button" aria-label="显示全部" onClick={fitAll}><Maximize2 size={16} /><span>全部</span></button>
        <button type="button" aria-label="撤销" disabled={!history.length} onClick={() => { const previous = history.at(-1); if (!previous) return; setFuture((items) => [geometry, ...items].slice(0, 30)); setHistory((items) => items.slice(0, -1)); onGeometryChange(previous); onMessage("已撤销上一步操作。"); }}><RotateCcw size={16} /></button>
        <button type="button" aria-label="重做" disabled={!future.length} onClick={() => { const next = future[0]; if (!next) return; setHistory((items) => [...items, geometry].slice(-30)); setFuture((items) => items.slice(1)); onGeometryChange(next); onMessage("已重做下一步操作。"); }}><RotateCw size={16} /></button>
        <button type="button" className={tool === "delete" ? "active" : ""} aria-label="删除工具：点击对象删除" onClick={() => setActiveTool("delete")}><Trash2 size={16} /><span>删除</span></button>
        <button type="button" aria-label="重置二维视图" onClick={resetView}><RotateCcw size={16} /><span>重置</span></button>
      </div>
      <div className="qa-tool-guidance" role="status"><Focus size={15} /><strong>{TOOL_HELP[tool].label}</strong><span>{TOOL_HELP[tool].description}</span><em>{TOOL_HELP[tool].next} · Esc/右键取消</em>{arcDraft?.mid && <button type="button" onClick={applyArcDraft}>应用圆弧</button>}</div>
      <Stage
        width={size.width}
        height={stageHeight}
        onClick={handleStageClick}
        onWheel={handleWheel}
        onMouseDown={handlePointerDown}
        onMouseMove={handlePointerMove}
        onMouseUp={handlePointerUp}
        onMouseLeave={handlePointerUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onContextMenu={(event) => { event.evt.preventDefault(); cancelCurrentTool(); }}
      >
        <Layer>
          {Array.from({ length: 36 }, (_, index) => {
            const spacing = BASE_SCALE * zoom;
            const x = ((offset.x % spacing) + index * spacing);
            const y = ((offset.y % spacing) + index * spacing);
            return <Line key={`grid-${index}`} points={[x, 0, x, size.height, 0, y, size.width, y]} stroke="#e6ebed" strokeWidth={1} />;
          })}
          {view === "plan" && geometry.plan_boundary?.outer_segments.map((segment) => {
            const map = new Map(geometry.plan_boundary!.outer_points.map((item) => [item.id, item]));
            const start = map.get(segment.start_point_id)!;
            const end = map.get(segment.end_point_id)!;
            const a = toScreen(start.x_m, start.y_m);
            const b = toScreen(end.x_m, end.y_m);
            const mid = segment.kind === "arc" ? toScreen(segment.arc_mid_x_m!, segment.arc_mid_y_m!) : null;
            const active = arcDraft?.segmentId === segment.id || selection?.kind === "boundary_segment" && selection.id === segment.id;
            return <Line key={segment.id} points={mid ? [a.x, a.y, mid.x, mid.y, b.x, b.y] : [a.x, a.y, b.x, b.y]} stroke={active ? "#dc6b2f" : "#77aab5"} strokeWidth={active ? 5 : 3} hitStrokeWidth={18} dash={[8, 4]} tension={mid ? 0.45 : 0} onClick={(event) => { if (tool === "delete") return handleObjectClick(event, { kind: "boundary_segment", id: segment.id }); if (tool !== "arc") return; event.cancelBubble = true; setArcDraft({ segmentId: segment.id, mid: null }); onSelectionChange({ kind: "boundary_segment", id: segment.id }); onMessage(`圆弧：已选择 ${segment.id}，请点击弧上第三点。`); }} />;
          })}
          {view === "plan" && boundaryDraft.length > 0 && <Line points={boundaryDraft.flatMap((item) => { const value = toScreen(item.x_m, item.y_m); return [value.x, value.y]; })} stroke="#77aab5" strokeWidth={2} dash={[6, 4]} />}
          {beamStart && cursorPlane && (() => { const start = project({ id: "draft", ...beamStart.point, support: "none", column_top: false }); const a = toScreen(start.u, start.v); const b = toScreen(cursorPlane.u, cursorPlane.v); return <Line points={[a.x, a.y, b.x, b.y]} stroke="#dc6b2f" strokeWidth={3} dash={[7, 5]} listening={false} />; })()}
          {measureStart && measureEnd && (() => { const a = toScreen(measureStart.u, measureStart.v); const b = toScreen(measureEnd.u, measureEnd.v); const distance = Math.hypot(measureEnd.u - measureStart.u, measureEnd.v - measureStart.v); return <><Line points={[a.x, a.y, b.x, b.y]} stroke="#b05e2e" strokeWidth={2} dash={[4, 4]} listening={false} /><Text x={(a.x + b.x) / 2 + 6} y={(a.y + b.y) / 2 - 18} text={`${distance.toFixed(3)} m`} fontSize={12} fill="#8b421d" listening={false} /></>; })()}
          {arcDraft?.mid && geometry.plan_boundary && (() => { const segment = geometry.plan_boundary.outer_segments.find((item) => item.id === arcDraft.segmentId); const points = new Map(geometry.plan_boundary.outer_points.map((item) => [item.id, item])); const start = segment ? points.get(segment.start_point_id) : null; const end = segment ? points.get(segment.end_point_id) : null; if (!start || !end) return null; const a = toScreen(start.x_m, start.y_m); const m = toScreen(arcDraft.mid.x_m, arcDraft.mid.y_m); const b = toScreen(end.x_m, end.y_m); return <Line points={[a.x, a.y, m.x, m.y, b.x, b.y]} stroke="#dc6b2f" strokeWidth={4} tension={0.45} dash={[6, 4]} listening={false} />; })()}
          {geometry.members.map((member) => {
            const start = nodeById.get(member.start_node_id);
            const end = nodeById.get(member.end_node_id);
            if (!start || !end) return null;
            const aModel = project(start);
            const bModel = project(end);
            const a = toScreen(aModel.u, aModel.v);
            const b = toScreen(bModel.u, bModel.v);
            const isPoint = Math.hypot(a.x - b.x, a.y - b.y) < 2;
            const active = selection?.kind === "member" && selection.id === member.id;
            const color = active ? "#dc6b2f" : member.role === "column" ? "#176879" : member.role === "purlin" ? "#7b5d97" : "#253f4a";
            if (isPoint) return <Circle key={member.id} x={a.x} y={a.y} radius={active ? 10 : 7} fill={color} stroke="white" strokeWidth={2} draggable={tool === "select" && view === "plan" && member.role === "column"} onDragStart={() => onSelectionChange({ kind: "member", id: member.id })} onDragEnd={(event) => moveColumn(member.id, event.target.x(), event.target.y())} onClick={(event) => handleObjectClick(event, { kind: "member", id: member.id })} />;
            return <Line key={member.id} points={[a.x, a.y, b.x, b.y]} stroke={color} strokeWidth={active ? 6 : member.role === "column" ? 4 : 3} hitStrokeWidth={18} onClick={(event) => handleObjectClick(event, { kind: "member", id: member.id })} />;
          })}
          {(geometry.supports ?? []).map((support) => {
            const node = nodeById.get(support.node_id);
            const instance = geometry.foundation_instances?.find((item) => item.support_id === support.id);
            if (!node) return null;
            const point = project(node);
            const screen = toScreen(point.u, point.v);
            const active = instance ? selection?.kind === "foundation" && selection.id === instance.id : selection?.kind === "support" && selection.id === support.id;
            return <Rect key={support.id} x={screen.x - 9} y={screen.y - 9} width={18} height={18} fill={active ? "#dc6b2f" : instance ? "#c6b69b" : "#dcebed"} stroke={instance ? "#7e6a4d" : "#176879"} strokeWidth={2} onClick={(event) => handleObjectClick(event, instance ? { kind: "foundation", id: instance.id } : { kind: "support", id: support.id })} />;
          })}
          {geometry.nodes.map((node) => {
            const point = project(node);
            const screen = toScreen(point.u, point.v);
            const active = selection?.kind === "node" && selection.id === node.id;
            return <Circle key={node.id} x={screen.x} y={screen.y} radius={active ? 6 : 4} fill={active ? "#dc6b2f" : "#f8fbfb"} stroke="#176879" strokeWidth={2} draggable={tool === "select"} onDragStart={() => onSelectionChange({ kind: "node", id: node.id })} onDragEnd={(event) => moveNode(node.id, event.target.x(), event.target.y())} onClick={(event) => handleObjectClick(event, { kind: "node", id: node.id })} />;
          })}
          {geometry.members.map((member) => {
            const instance = geometry.member_instances?.find((item) => item.member_id === member.id);
            const start = nodeById.get(member.start_node_id);
            const end = nodeById.get(member.end_node_id);
            if (!instance || !start || !end) return null;
            const a = project(start); const b = project(end); const screen = toScreen((a.u + b.u) / 2, (a.v + b.v) / 2);
            return <Text key={`mark-${member.id}`} x={screen.x + 5} y={screen.y - 15} text={instance.mark} fontSize={11} fill="#53676f" />;
          })}
          {(geometry.foundation_instances ?? []).map((instance) => {
            const support = geometry.supports?.find((item) => item.id === instance.support_id);
            const node = support ? nodeById.get(support.node_id) : null;
            if (!node) return null;
            const point = project(node); const screen = toScreen(point.u, point.v);
            return <Text key={`fm-${instance.id}`} x={screen.x + 10} y={screen.y + 8} text={instance.mark} fontSize={11} fill="#806c4d" />;
          })}
          {boxStart && boxCurrent && <Rect x={Math.min(boxStart.x, boxCurrent.x)} y={Math.min(boxStart.y, boxCurrent.y)} width={Math.abs(boxCurrent.x - boxStart.x)} height={Math.abs(boxCurrent.y - boxStart.y)} fill="rgba(23,104,121,0.12)" stroke="#176879" strokeWidth={1.5} dash={[6, 4]} listening={false} />}
        </Layer>
      </Stage>
    </div>
  );
}
