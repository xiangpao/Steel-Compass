"use client";

import { ChevronRight, ClipboardCheck, GitBranch, MapPin, MousePointer2, TriangleAlert } from "lucide-react";
import { NumberField } from "@/components/number-field";
import { CompositeInput, type CompositeItem } from "@/components/pergola/composite-input";
import { selectionDetails, type WorkbenchModel } from "@/components/pergola/workbench-model";
import type { SectionDraft } from "@/lib/pergola-catalog";
import { assignMemberType, completeBeamColumnConnections, updateMemberType, updateNode, updateSpringStiffness, updateSupport } from "@/lib/pergola-edits";
import { sectionDraftFor } from "@/lib/pergola-project";
import type { MemberTypeDefinition } from "@/lib/types";

function sectionItems(section: SectionDraft, update: (patch: Partial<SectionDraft>) => void): CompositeItem[] {
  if (section.family === "H") {
    return (["h", "b", "tw", "tf"] as const).map((key) => ({
      label: key === "h" ? "H" : key === "b" ? "B" : key,
      value: section[key],
      unit: "mm",
      onChange: (value) => update({ [key]: value }),
    }));
  }
  const square = section.family === "SHS";
  return [
    { label: square ? "边长" : "高", value: section.h, unit: "mm", onChange: (value) => update({ h: value, ...(square ? { b: value } : {}) }) },
    ...(square ? [] : [{ label: "宽", value: section.b, unit: "mm", onChange: (value: number) => update({ b: value }) }]),
    { label: "厚", value: section.tw, unit: "mm", onChange: (value) => update({ tw: value, tf: value }) },
  ];
}

function MemberInspector({ model }: { model: WorkbenchModel }) {
  const { geometry, setGeometry, setMessage, sectionDrafts, setSectionDrafts } = model;
  const { member, memberInstance, memberType } = selectionDetails(geometry, model.selection);
  if (!member || !memberInstance || !memberType) return null;
  const start = geometry.nodes.find((item) => item.id === member.start_node_id)!;
  const end = geometry.nodes.find((item) => item.id === member.end_node_id)!;
  const angle = (Math.atan2(end.y_m - start.y_m, end.x_m - start.x_m) * 180) / Math.PI;
  const section = sectionDraftFor(sectionDrafts, memberType.id);
  const editType = (values: Partial<MemberTypeDefinition>) => setGeometry((current) => updateMemberType(current, memberType.id, values));
  const changeType = (typeId: string) => {
    const result = assignMemberType(geometry, member.id, typeId);
    if (!result) return;
    setGeometry((current) => assignMemberType(current, member.id, typeId)?.geometry ?? current);
    setMessage(`已将 ${memberInstance.mark} 改为 ${result.type.title}。`);
  };
  const updateSection = (patch: Partial<SectionDraft>) =>
    setSectionDrafts((current) => ({ ...current, [memberType.id]: { ...section, ...patch } }));
  return (
    <>
      <div className="qa-inspector-heading">
        <span className="qa-object-mark">{memberInstance.mark}</span>
        <div>
          <strong>{memberType.title}</strong>
          <small>
            {member.id} · 方向 {angle.toFixed(1)}°
          </small>
        </div>
      </div>
      <label className="qa-field">
        <span>构件类型</span>
        <select value={memberType.id} onChange={(event) => changeType(event.target.value)}>
          {geometry.member_types?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </label>
      <div className="qa-property-group">
        <strong>起止节点与标高</strong>
        <CompositeInput
          items={[
            { label: "起点Z", value: start.z_m, unit: "m", onChange: (value) => setGeometry((current) => updateNode(current, start.id, { z_m: value })) },
            { label: "终点Z", value: end.z_m, unit: "m", onChange: (value) => setGeometry((current) => updateNode(current, end.id, { z_m: value })) },
          ]}
        />
        <small>
          {start.id} → {end.id}；柱高只通过这里修改，平面拖动不会改变高度。
        </small>
      </div>
      <label className="qa-field">
        <span>钢材牌号</span>
        <select value={memberType.material_grade} onChange={(event) => editType({ material_grade: event.target.value })}>
          <option>Q235B</option>
          <option>Q355B</option>
          {!["Q235B", "Q355B"].includes(memberType.material_grade) && (
            <option value={memberType.material_grade} disabled>
              {memberType.material_grade}（请选择已开放牌号）
            </option>
          )}
        </select>
      </label>
      <div className="qa-property-group">
        <strong>截面尺寸</strong>
        <CompositeInput items={sectionItems(section, updateSection)} />
        <small>
          {section.family === "SHS" ? "方管高宽相等，按边长保存；修改作用于同类型全部构件。" : "修改作用于同类型全部构件。"}
          保存时生成新截面修订，不覆盖历史规格。
        </small>
      </div>
      <details className="qa-details">
        <summary>详细参数</summary>
        <label className="qa-field">
          <span>杆端连接</span>
          <select value={memberType.end_release} onChange={(event) => editType({ end_release: event.target.value as "rigid" | "pinned" })}>
            <option value="rigid">刚接</option>
            <option value="pinned">铰接</option>
          </select>
        </label>
        <label className="qa-field">
          <span>截面方向</span>
          <select
            value={memberType.orientation}
            onChange={(event) => editType({ orientation: event.target.value as "strong_axis" | "weak_axis" })}
          >
            <option value="strong_axis">强轴受弯</option>
            <option value="weak_axis">弱轴受弯</option>
          </select>
        </label>
      </details>
    </>
  );
}

function SupportInspector({ model }: { model: WorkbenchModel }) {
  const { geometry, setGeometry } = model;
  const support = selectionDetails(geometry, model.selection).directSupport;
  if (!support) return null;
  const node = geometry.nodes.find((item) => item.id === support.node_id);
  const spring = (label: string, axis: "ux" | "uy" | "uz", fallback: number): CompositeItem => ({
    label,
    value: support.spring_stiffness?.[axis] ?? fallback,
    unit: "kN/m",
    onChange: (value) => setGeometry((current) => updateSpringStiffness(current, support.id, axis, value)),
  });
  return (
    <>
      <div className="qa-inspector-heading">
        <span className="qa-object-mark">S</span>
        <div>
          <strong>支承 {support.id}</strong>
          <small>节点 {support.node_id} · 与基础分开定义</small>
        </div>
      </div>
      <label className="qa-field">
        <span>约束类型</span>
        <select
          value={support.restraint}
          onChange={(event) =>
            setGeometry((current) => updateSupport(current, support.id, event.target.value as "pinned" | "fixed" | "spring"))
          }
        >
          <option value="pinned">铰接（约束 UX/UY/UZ）</option>
          <option value="fixed">固定（约束六自由度）</option>
          <option value="spring">弹簧支承</option>
        </select>
      </label>
      {support.restraint === "spring" && (
        <div className="qa-property-group">
          <strong>平移弹簧刚度</strong>
          <small>默认仅用于交互草稿；工程计算须按地基或连接资料填写。</small>
          <CompositeInput items={[spring("Kx", "ux", 10000), spring("Ky", "uy", 10000), spring("Kz", "uz", 50000)]} />
        </div>
      )}
      <div className="qa-location-card">
        <MapPin size={17} />
        <div>
          <strong>约束位置</strong>
          <span>
            X {node?.x_m.toFixed(2)} / Y {node?.y_m.toFixed(2)} / Z {node?.z_m.toFixed(2)}
          </span>
        </div>
      </div>
    </>
  );
}

function NodeInspector({ model }: { model: WorkbenchModel }) {
  const { geometry, setGeometry } = model;
  const node = selectionDetails(geometry, model.selection).node;
  if (!node) return null;
  const axis = (key: "x_m" | "y_m" | "z_m", label: string): CompositeItem => ({
    label,
    value: node[key],
    unit: "m",
    onChange: (value) => setGeometry((current) => updateNode(current, node.id, { [key]: value })),
  });
  return (
    <>
      <div className="qa-inspector-heading">
        <span className="qa-object-mark">N</span>
        <div>
          <strong>节点 {node.id}</strong>
          <small>结构几何坐标</small>
        </div>
      </div>
      <CompositeInput items={[axis("x_m", "X"), axis("y_m", "Y"), axis("z_m", "Z")]} />
    </>
  );
}

function ModelOverview({ model }: { model: WorkbenchModel }) {
  const { geometry, setGeometry, setMessage } = model;
  return (
    <>
      <div className="qa-panel-title">
        <div>
          <strong>模型对象</strong>
          <small>按图纸编号定位和批量修改</small>
        </div>
        <MousePointer2 size={18} />
      </div>
      <div className="qa-model-summary">
        <span>
          <b>{geometry.nodes.length}</b> 节点
        </span>
        <span>
          <b>{geometry.members.length}</b> 构件
        </span>
        <span>
          <b>{geometry.foundation_instances?.length ?? 0}</b> 基础
        </span>
      </div>
      <button
        type="button"
        className="qa-secondary-action"
        onClick={() => {
          setGeometry(completeBeamColumnConnections);
          setMessage("已补齐可识别的矩形管梁柱连接实例；既有连接未被覆盖。");
        }}
      >
        <GitBranch size={16} />
        识别并补齐梁柱连接
      </button>
      <small>只增加柱与梁在同一节点真实相交的 J-B 实例，不覆盖已有连接。</small>
      <label className="qa-field">
        <span>新增构件类型</span>
        <select value={model.activeMemberTypeId} onChange={(event) => model.setActiveMemberTypeId(event.target.value)}>
          {geometry.member_types
            ?.filter((item) => item.role !== "column")
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
        </select>
      </label>
      <label className="qa-field">
        <span>新增构件工作标高</span>
        <div className="qa-value-unit">
          <NumberField step="0.1" value={model.workElevation} onChange={model.setWorkElevation} />
          <em>m</em>
        </div>
      </label>
      <div className="qa-model-tree">
        {geometry.member_types?.map((type) => (
          <button
            type="button"
            key={type.id}
            onClick={() => {
              const instance = geometry.member_instances?.find((item) => item.member_type_id === type.id);
              if (instance) model.handleSelection({ kind: "member", id: instance.member_id });
            }}
          >
            <span>{type.mark_prefix}</span>
            <div>
              <strong>{type.title}</strong>
              <small>
                {geometry.member_instances?.filter((item) => item.member_type_id === type.id).length ?? 0} 根 · {type.material_grade}
              </small>
            </div>
            <ChevronRight size={15} />
          </button>
        ))}
      </div>
      <div className="qa-task-list">
        <strong>当前任务</strong>
        <span className="done">
          <ClipboardCheck size={15} />
          对象编号和类型已建立
        </span>
        <span>
          <TriangleAlert size={15} />
          荷载分配与二阶分析仍待验证
        </span>
      </div>
    </>
  );
}

export function ModelPanel({ model }: { model: WorkbenchModel }) {
  const details = selectionDetails(model.geometry, model.selection);
  if (details.member && details.memberInstance && details.memberType) return <MemberInspector model={model} />;
  if (details.directSupport) return <SupportInspector model={model} />;
  if (details.node) return <NodeInspector model={model} />;
  return <ModelOverview model={model} />;
}
