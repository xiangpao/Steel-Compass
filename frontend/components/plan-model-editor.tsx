"use client";

import {
  Anchor,
  BetweenHorizontalStart,
  CirclePlus,
  CornerUpLeft,
  CornerUpRight,
  MousePointer2,
  PenLine,
  Ruler,
  Trash2,
  Unlink,
  Waves,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, Layer, Line, Stage, Text } from "react-konva";
import type { KonvaEventObject } from "konva/lib/Node";
import earcut from "earcut";
import polygonClipping from "polygon-clipping";

import type { SceneGeometryProfile } from "@/lib/types";

type Tool = "select" | "node" | "beam" | "column" | "support" | "boundary" | "arc" | "measure";
type Selection = { kind: "node" | "member"; id: string } | null;

type Props = {
  geometry: SceneGeometryProfile;
  selected: Selection;
  onSelectedChange: (selection: Selection) => void;
  onChange: (geometry: SceneGeometryProfile) => void;
  onMessage: (message: string) => void;
};

const SCALE = 52;
const PADDING = 42;

function nextId(prefix: string, values: string[]) {
  let index = values.length + 1;
  while (values.includes(`${prefix}${index}`)) index += 1;
  return `${prefix}${index}`;
}

export function PlanModelEditor({ geometry, selected, onSelectedChange, onChange, onMessage }: Props) {
  const shellRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 720, height: 580 });
  const [tool, setTool] = useState<Tool>("select");
  const [beamStart, setBeamStart] = useState<string | null>(null);
  const [boundaryDraft, setBoundaryDraft] = useState<Array<{ x_m: number; y_m: number }>>([]);
  const [measureStart, setMeasureStart] = useState<string | null>(null);
  const [history, setHistory] = useState<SceneGeometryProfile[]>([]);
  const [future, setFuture] = useState<SceneGeometryProfile[]>([]);

  useEffect(() => {
    const element = shellRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.max(320, entry.contentRect.width), height: Math.max(420, entry.contentRect.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const planNodes = useMemo(() => geometry.nodes.filter((node) => node.z_m > 0), [geometry.nodes]);
  const bounds = useMemo(() => {
    const xs = [...geometry.nodes.map((item) => item.x_m), ...(geometry.plan_boundary?.outer_points.map((item) => item.x_m) ?? [])];
    const ys = [...geometry.nodes.map((item) => item.y_m), ...(geometry.plan_boundary?.outer_points.map((item) => item.y_m) ?? [])];
    return { minX: Math.min(...xs, 0), maxY: Math.max(...ys, 0) };
  }, [geometry]);
  const toScreen = (x: number, y: number) => ({ x: PADDING + (x - bounds.minX) * SCALE, y: PADDING + (bounds.maxY - y) * SCALE });
  const toModel = (x: number, y: number) => ({ x_m: (x - PADDING) / SCALE + bounds.minX, y_m: bounds.maxY - (y - PADDING) / SCALE });
  const nodeById = useMemo(() => new Map(geometry.nodes.map((item) => [item.id, item])), [geometry.nodes]);
  const boundaryPreview = useMemo(() => {
    const points = geometry.plan_boundary?.outer_points ?? [];
    if (points.length < 3) return null;
    const ring = points.map((point) => [point.x_m, point.y_m] as [number, number]);
    const normalized = polygonClipping.union([[...ring, ring[0]]]);
    const triangles = earcut(ring.flat());
    const area = Math.abs(ring.reduce((sum, point, index) => {
      const next = ring[(index + 1) % ring.length];
      return sum + point[0] * next[1] - next[0] * point[1];
    }, 0)) / 2;
    return { area, triangleCount: triangles.length / 3, polygonCount: normalized.length };
  }, [geometry.plan_boundary]);

  function commit(next: SceneGeometryProfile) {
    setHistory((items) => [...items.slice(-49), geometry]);
    setFuture([]);
    onChange(next);
  }

  function undo() {
    const previous = history.at(-1);
    if (!previous) return;
    setHistory((items) => items.slice(0, -1));
    setFuture((items) => [geometry, ...items].slice(0, 50));
    onChange(previous);
  }

  function redo() {
    const next = future[0];
    if (!next) return;
    setFuture((items) => items.slice(1));
    setHistory((items) => [...items, geometry].slice(-50));
    onChange(next);
  }

  function selectNode(id: string) {
    onSelectedChange({ kind: "node", id });
    if (tool === "beam") {
      if (!beamStart) return setBeamStart(id);
      if (beamStart === id) return;
      const memberId = nextId("BM-", geometry.members.map((item) => item.id));
      commit({
        ...geometry,
        members: [...geometry.members, { id: memberId, start_node_id: beamStart, end_node_id: id, role: "beam", group_id: "roof-beams", behavior: "frame", end_release: "rigid" }],
      });
      setBeamStart(null);
      onSelectedChange({ kind: "member", id: memberId });
      onMessage("已增加钢梁；默认继承屋面梁构件组。")
    } else if (tool === "column") {
      const top = nodeById.get(id);
      if (!top || top.z_m <= 0) return;
      const baseId = `BASE-${id}`;
      const baseExists = nodeById.has(baseId);
      const memberId = nextId("COL-", geometry.members.map((item) => item.id));
      commit({
        ...geometry,
        nodes: baseExists ? geometry.nodes : [...geometry.nodes, { id: baseId, x_m: top.x_m, y_m: top.y_m, z_m: 0, support: "none", column_top: false }],
        members: [...geometry.members, { id: memberId, start_node_id: baseId, end_node_id: id, role: "column", group_id: "columns", behavior: "frame", end_release: "rigid" }],
        supports: [...(geometry.supports ?? []), { id: `SUP-${baseId}`, node_id: baseId, restraint: "fixed", foundation_id: `F-${baseId}` }],
      });
      onSelectedChange({ kind: "member", id: memberId });
      onMessage("已增加钢柱和柱脚支承。")
    } else if (tool === "support") {
      if ((geometry.supports ?? []).some((item) => item.node_id === id)) return;
      commit({ ...geometry, supports: [...(geometry.supports ?? []), { id: `SUP-${id}`, node_id: id, restraint: "fixed", foundation_id: `F-${id}` }] });
      onMessage("已为节点增加固定支承。")
    } else if (tool === "measure") {
      if (!measureStart) return setMeasureStart(id);
      const start = nodeById.get(measureStart);
      const end = nodeById.get(id);
      if (start && end) onMessage(`测量长度：${Math.hypot(end.x_m - start.x_m, end.y_m - start.y_m, end.z_m - start.z_m).toFixed(3)} m`);
      setMeasureStart(null);
    }
  }

  function selectOrSplitMember(memberId: string, event: KonvaEventObject<MouseEvent>) {
    if (tool !== "beam") {
      onSelectedChange({ kind: "member", id: memberId });
      return;
    }
    const member = geometry.members.find((item) => item.id === memberId);
    const start = member ? nodeById.get(member.start_node_id) : null;
    const end = member ? nodeById.get(member.end_node_id) : null;
    const pointer = event.target.getStage()?.getPointerPosition();
    if (!member || !start || !end || !pointer) return;
    const clicked = toModel(pointer.x, pointer.y);
    const dx = end.x_m - start.x_m;
    const dy = end.y_m - start.y_m;
    const denominator = dx * dx + dy * dy;
    const t = denominator > 0 ? Math.max(0.02, Math.min(0.98, ((clicked.x_m - start.x_m) * dx + (clicked.y_m - start.y_m) * dy) / denominator)) : 0.5;
    const nodeId = nextId("N-", geometry.nodes.map((item) => item.id));
    const node = { id: nodeId, x_m: start.x_m + dx * t, y_m: start.y_m + dy * t, z_m: start.z_m + (end.z_m - start.z_m) * t, support: "none" as const, column_top: false };
    const splitMembers = [
      { ...member, id: `${member.id}.1`, end_node_id: nodeId },
      { ...member, id: `${member.id}.2`, start_node_id: nodeId },
    ];
    const addedBeam = beamStart
      ? [{ id: nextId("BM-", geometry.members.map((item) => item.id)), start_node_id: beamStart, end_node_id: nodeId, role: "beam" as const, group_id: "roof-beams", behavior: "frame" as const, end_release: "rigid" as const }]
      : [];
    commit({
      ...geometry,
      nodes: [...geometry.nodes, node],
      members: [...geometry.members.filter((item) => item.id !== member.id), ...splitMembers, ...addedBeam],
    });
    if (beamStart) {
      setBeamStart(null);
      onSelectedChange({ kind: "member", id: addedBeam[0].id });
      onMessage("已在杆件点击位置建立交点、拆分原杆件并连接新钢梁。");
    } else {
      setBeamStart(nodeId);
      onSelectedChange({ kind: "node", id: nodeId });
      onMessage("已在杆件点击位置建立交点并拆分原杆件；请选择新梁终点。");
    }
  }

  function deleteSelection() {
    if (!selected) return;
    if (selected.kind === "member") {
      const member = geometry.members.find((item) => item.id === selected.id);
      if (!member) return;
      const remainingMembers = geometry.members.filter((item) => item.id !== selected.id);
      const baseNodeId = member.role === "column" ? member.start_node_id : null;
      const baseStillUsed = baseNodeId ? remainingMembers.some((item) => item.start_node_id === baseNodeId || item.end_node_id === baseNodeId) : true;
      commit({
        ...geometry,
        members: remainingMembers,
        nodes: baseNodeId && !baseStillUsed ? geometry.nodes.filter((item) => item.id !== baseNodeId) : geometry.nodes,
        supports: baseNodeId ? (geometry.supports ?? []).filter((item) => item.node_id !== baseNodeId) : geometry.supports,
      });
      onSelectedChange(null);
      onMessage(member.role === "column" ? "已移除钢柱；屋面节点和钢梁保持不变。" : "已删除所选钢梁。")
      return;
    }
    const related = geometry.members.filter((item) => item.start_node_id === selected.id || item.end_node_id === selected.id);
    if (related.length) {
      onMessage(`节点仍连接 ${related.length} 根杆件，请先删除或改接这些杆件。`);
      return;
    }
    commit({
      ...geometry,
      nodes: geometry.nodes.filter((item) => item.id !== selected.id),
      supports: (geometry.supports ?? []).filter((item) => item.node_id !== selected.id),
    });
    onSelectedChange(null);
  }

  function convertSelectedBoundaryToArc() {
    const segment = geometry.plan_boundary?.outer_segments[0];
    if (!geometry.plan_boundary || !segment) return onMessage("请先绘制闭合屋面边界。")
    const points = new Map(geometry.plan_boundary.outer_points.map((item) => [item.id, item]));
    const start = points.get(segment.start_point_id)!;
    const end = points.get(segment.end_point_id)!;
    const dx = end.x_m - start.x_m;
    const dy = end.y_m - start.y_m;
    const length = Math.hypot(dx, dy) || 1;
    const updated = { ...segment, kind: "arc" as const, arc_mid_x_m: (start.x_m + end.x_m) / 2 - dy / length * Math.min(1, length / 4), arc_mid_y_m: (start.y_m + end.y_m) / 2 + dx / length * Math.min(1, length / 4) };
    commit({ ...geometry, plan_boundary: { ...geometry.plan_boundary, outer_segments: geometry.plan_boundary.outer_segments.map((item) => item.id === segment.id ? updated : item) } });
    onMessage("已将第一段边界转换为三点圆弧；可在属性区精确修改弧上点。")
  }

  function stageClick(event: KonvaEventObject<MouseEvent>) {
    if (event.target !== event.target.getStage()) return;
    const pointer = event.target.getStage().getPointerPosition();
    if (!pointer) return;
    const model = toModel(pointer.x, pointer.y);
    if (tool === "node") {
      const id = nextId("N-", geometry.nodes.map((item) => item.id));
      commit({ ...geometry, nodes: [...geometry.nodes, { id, ...model, z_m: geometry.roof_elevation?.datum_height_m ?? 3, support: "none", column_top: false }] });
      onSelectedChange({ kind: "node", id });
    } else if (tool === "boundary") {
      const nextDraft = [...boundaryDraft, model];
      if (nextDraft.length >= 3 && Math.hypot(nextDraft[0].x_m - model.x_m, nextDraft[0].y_m - model.y_m) < 0.25) {
        const closed = nextDraft.slice(0, -1);
        const outer_points = closed.map((point, index) => ({ id: `BP-${index + 1}`, ...point }));
        const outer_segments = outer_points.map((point, index) => ({ id: `BS-${index + 1}`, start_point_id: point.id, end_point_id: outer_points[(index + 1) % outer_points.length].id, kind: "line" as const }));
        commit({ ...geometry, plan_boundary: { outer_points, outer_segments, source: "用户二维图面定义" } });
        setBoundaryDraft([]);
        setTool("select");
        onMessage("屋面边界已闭合。")
      } else setBoundaryDraft(nextDraft);
    } else onSelectedChange(null);
  }

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") { event.preventDefault(); redo(); }
      if (event.key === "Delete" || event.key === "Backspace") deleteSelection();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  });

  const tools: Array<[Tool, string, typeof MousePointer2]> = [
    ["select", "选择", MousePointer2], ["node", "节点", CirclePlus], ["beam", "钢梁", BetweenHorizontalStart],
    ["column", "钢柱", PenLine], ["support", "支承", Anchor], ["boundary", "边界", PenLine],
    ["arc", "圆弧", Waves], ["measure", "测距", Ruler],
  ];

  return (
    <div className="plan-model-editor" ref={shellRef}>
      <div className="model-editor-toolbar" aria-label="二维模型工具">
        {tools.map(([value, label, Icon]) => <button key={value} type="button" className={tool === value ? "active" : ""} aria-pressed={tool === value} onClick={() => value === "arc" ? convertSelectedBoundaryToArc() : setTool(value)}><Icon size={16} /><span>{label}</span></button>)}
        <button type="button" disabled={!history.length} onClick={undo}><CornerUpLeft size={16} /><span>撤销</span></button>
        <button type="button" disabled={!future.length} onClick={redo}><CornerUpRight size={16} /><span>重做</span></button>
        <button type="button" disabled={!selected} onClick={deleteSelection}><Trash2 size={16} /><span>{selected?.kind === "member" && geometry.members.find((item) => item.id === selected.id)?.role === "column" ? "移除柱" : "删除"}</span></button>
      </div>
      <Stage width={size.width} height={size.height - 54} onClick={stageClick}>
        <Layer>
          {Array.from({ length: Math.ceil(size.width / SCALE) }, (_, index) => <Line key={`gx-${index}`} points={[index * SCALE, 0, index * SCALE, size.height]} stroke="#e5eaeb" strokeWidth={1} />)}
          {Array.from({ length: Math.ceil(size.height / SCALE) }, (_, index) => <Line key={`gy-${index}`} points={[0, index * SCALE, size.width, index * SCALE]} stroke="#e5eaeb" strokeWidth={1} />)}
          {geometry.plan_boundary?.outer_segments.map((segment) => {
            const points = new Map(geometry.plan_boundary!.outer_points.map((item) => [item.id, item]));
            const start = points.get(segment.start_point_id)!;
            const end = points.get(segment.end_point_id)!;
            const a = toScreen(start.x_m, start.y_m);
            const b = toScreen(end.x_m, end.y_m);
            const middle = segment.kind === "arc" ? toScreen(segment.arc_mid_x_m!, segment.arc_mid_y_m!) : null;
            return <Line key={segment.id} points={middle ? [a.x, a.y, middle.x, middle.y, b.x, b.y] : [a.x, a.y, b.x, b.y]} stroke="#77aab5" strokeWidth={3} dash={[7, 4]} tension={middle ? 0.45 : 0} />;
          })}
          {boundaryDraft.length > 0 && <Line points={boundaryDraft.flatMap((point) => { const value = toScreen(point.x_m, point.y_m); return [value.x, value.y]; })} stroke="#77aab5" strokeWidth={2} dash={[6, 4]} />}
          {geometry.members.filter((item) => item.role !== "column").map((member) => {
            const start = nodeById.get(member.start_node_id);
            const end = nodeById.get(member.end_node_id);
            if (!start || !end) return null;
            const a = toScreen(start.x_m, start.y_m);
            const b = toScreen(end.x_m, end.y_m);
            const active = selected?.kind === "member" && selected.id === member.id;
            return <Line key={member.id} points={[a.x, a.y, b.x, b.y]} stroke={active ? "#dc6b2f" : "#263d4a"} strokeWidth={active ? 6 : 3} hitStrokeWidth={16} onClick={(event) => { event.cancelBubble = true; selectOrSplitMember(member.id, event); }} />;
          })}
          {geometry.members.filter((item) => item.role === "column").map((member) => {
            const top = nodeById.get(member.end_node_id);
            if (!top) return null;
            const point = toScreen(top.x_m, top.y_m);
            const active = selected?.kind === "member" && selected.id === member.id;
            return <Circle key={member.id} x={point.x} y={point.y} radius={active ? 11 : 8} fill={active ? "#dc6b2f" : "#1e6675"} stroke="white" strokeWidth={2} onClick={(event) => { event.cancelBubble = true; onSelectedChange({ kind: "member", id: member.id }); }} />;
          })}
          {planNodes.map((node) => {
            const point = toScreen(node.x_m, node.y_m);
            const active = selected?.kind === "node" && selected.id === node.id;
            return <Circle key={node.id} x={point.x} y={point.y} radius={active ? 7 : 5} fill={active ? "#dc6b2f" : "#f8fbfb"} stroke="#1e6675" strokeWidth={2} draggable onClick={(event) => { event.cancelBubble = true; selectNode(node.id); }} onDragEnd={(event) => { const model = toModel(event.target.x(), event.target.y()); commit({ ...geometry, nodes: geometry.nodes.map((item) => item.id === node.id ? { ...item, ...model } : item) }); }} />;
          })}
          {planNodes.map((node) => { const point = toScreen(node.x_m, node.y_m); return <Text key={`label-${node.id}`} x={point.x + 7} y={point.y - 16} text={node.id} fontSize={10} fill="#63757b" />; })}
          {beamStart && <Text x={12} y={12} text={`钢梁起点：${beamStart}，请选择终点`} fontSize={13} fill="#b35e32" />}
        </Layer>
      </Stage>
      <div className="model-editor-status"><Unlink size={14} />删除柱只移除柱杆件与支承，不会删除屋面节点和钢梁。{boundaryPreview ? ` 边界 ${boundaryPreview.area.toFixed(2)} m² · 显示三角 ${boundaryPreview.triangleCount} · 闭合区 ${boundaryPreview.polygonCount}` : ""}</div>
    </div>
  );
}
