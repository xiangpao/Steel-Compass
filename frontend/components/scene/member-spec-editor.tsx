"use client";

import { Plus } from "lucide-react";
import { NumberField } from "@/components/number-field";
import { CUSTOM_SECTION_DIMENSION_LABELS, defaultCustomSectionDimensions } from "@/lib/scene-model";
import type { CustomSectionDefinition, MemberSpecification, SectionCatalogEntry } from "@/lib/types";

export type CustomSectionFamily = CustomSectionDefinition["family"];

export type CustomSectionDraft = {
  name: string;
  family: CustomSectionFamily;
  dimensions: Record<string, number>;
  cornerRadius: number | "";
};

export const INITIAL_CUSTOM_SECTION: CustomSectionDraft = {
  name: "项目自定义矩形管",
  family: "RHS",
  dimensions: { h_mm: 200, b_mm: 100, t_mm: 6 },
  cornerRadius: "",
};

export function SectionCatalogToolbar({ onToggle }: { onToggle: () => void }) {
  return (
    <div className="custom-section-toolbar">
      <div>
        <strong>截面目录</strong>
        <span>标准规格与项目自定义截面统一用于自重、刚度和验算。</span>
      </div>
      <button type="button" onClick={onToggle}>
        <Plus size={16} /> 新建自定义截面
      </button>
    </div>
  );
}

export function CustomSectionEditor({
  draft,
  preview,
  working,
  onChange,
  onCreate,
}: {
  draft: CustomSectionDraft;
  preview: CustomSectionDefinition | null;
  working: boolean;
  onChange: (draft: CustomSectionDraft) => void;
  onCreate: () => void;
}) {
  return (
    <div className="custom-section-editor">
      <div className="parameter-grid compact-parameters">
        <label>
          <span>截面名称</span>
          <input value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} />
        </label>
        <label>
          <span>截面类型</span>
          <select
            value={draft.family}
            onChange={(event) => {
              const family = event.target.value as CustomSectionFamily;
              onChange({ ...draft, family, dimensions: defaultCustomSectionDimensions(family) });
            }}
          >
            <option value="SHS">方管 SHS</option>
            <option value="RHS">矩形管 RHS</option>
            <option value="CHS">圆管 CHS</option>
            <option value="H">H型钢</option>
            <option value="I">工字钢</option>
          </select>
        </label>
        {Object.entries(draft.dimensions).map(([key, value]) => (
          <label key={key}>
            <span>{CUSTOM_SECTION_DIMENSION_LABELS[key] ?? key}</span>
            <div className="input-with-unit">
              <NumberField
                min="1"
                step="1"
                value={value}
                onChange={(next) => onChange({ ...draft, dimensions: { ...draft.dimensions, [key]: next } })}
              />
              <span>mm</span>
            </div>
          </label>
        ))}
        {(draft.family === "SHS" || draft.family === "RHS") && (
          <label>
            <span>外圆角半径（可选）</span>
            <div className="input-with-unit">
              <input
                type="number"
                min="0"
                step="0.5"
                value={draft.cornerRadius}
                placeholder="方案测算可留空"
                onChange={(event) =>
                  onChange({ ...draft, cornerRadius: event.target.value === "" ? "" : Number(event.target.value) })
                }
              />
              <span>mm</span>
            </div>
            <small>留空按锐角理论截面；工程校核应采用产品或厂家截面性质。</small>
          </label>
        )}
      </div>
      {preview ? (
        <div className="custom-section-preview">
          <strong>实时计算结果</strong>
          <span>A = {preview.area_mm2.toFixed(2)} mm²</span>
          <span>理论质量 = {preview.theoretical_mass_kg_m?.toFixed(3)} kg/m</span>
          <span>理论线重 = {preview.self_weight_kn_m.toFixed(5)} kN/m</span>
          <span>
            Iy / Iz = {preview.iy_mm4.toExponential(3)} / {preview.iz_mm4.toExponential(3)} mm⁴
          </span>
          {preview.property_trace?.map((line) => <small key={line}>{line}</small>)}
        </div>
      ) : (
        <div className="inline-error">尺寸组合无效，请检查外形尺寸与厚度。</div>
      )}
      <div className="custom-section-actions">
        <span>面积、惯性矩、扭转常数和自重由后端按几何计算，不能手工伪造。</span>
        <button type="button" disabled={working || !draft.name.trim()} onClick={onCreate}>
          计算并加入项目截面库
        </button>
      </div>
    </div>
  );
}

function SectionPropertyTrace({ section }: { section: CustomSectionDefinition }) {
  const rows: Array<[string, string]> = [
    ["面积 A", `${section.area_mm2.toFixed(2)} mm²`],
    ["理论质量", `${section.theoretical_mass_kg_m?.toFixed(3) ?? "—"} kg/m`],
    ["理论线重", `${section.self_weight_kn_m.toFixed(5)} kN/m`],
    ["Iy / Iz", `${section.iy_mm4.toExponential(3)} / ${section.iz_mm4.toExponential(3)} mm⁴`],
    ["J", `${section.torsion_mm4.toExponential(3)} mm⁴`],
    ["iy / iz", `${section.radius_y_mm?.toFixed(2) ?? "—"} / ${section.radius_z_mm?.toFixed(2) ?? "—"} mm`],
  ];
  return (
    <details className="section-property-trace">
      <summary>查看截面计算依据</summary>
      <dl>
        {rows.map(([term, value]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {section.property_trace?.map((line) => <p key={line}>{line}</p>)}
      <small>{section.assumptions?.join("；")}</small>
    </details>
  );
}

export function MemberSpecEditor({
  specification,
  nodeLabel,
  availableSections,
  customSection,
  onChange,
  onRequestCustomSection,
}: {
  specification: MemberSpecification;
  nodeLabel?: string;
  availableSections: SectionCatalogEntry[];
  customSection?: CustomSectionDefinition;
  onChange: (patch: Partial<MemberSpecification>) => void;
  onRequestCustomSection: () => void;
}) {
  const lengthField = (key: "effective_length_m" | "unbraced_length_m", label: string) => (
    <label>
      <span>{label}</span>
      <div className="input-with-unit">
        <NumberField min="0.1" step="0.1" value={specification[key]} onChange={(value) => onChange({ [key]: value })} />
        <span>m</span>
      </div>
    </label>
  );
  return (
    <div className="scene-climate-guide">
      <div>
        <strong>
          {nodeLabel} · {specification.member_role === "beam" ? "梁" : "柱"}
        </strong>
        <span>目录推荐仅作为起始候选，利用率与控制项以计算结果为准。</span>
      </div>
      <div className="parameter-grid compact-parameters">
        <label>
          <span>钢材牌号</span>
          <select
            value={specification.material_grade}
            onChange={(event) =>
              onChange({ material_grade: event.target.value, selection_source: "user_locked", override_reason: "用户调整钢材牌号" })
            }
          >
            <option>Q235B</option>
            <option>Q355B</option>
          </select>
        </label>
        <label>
          <span>截面规格</span>
          <select
            value={specification.section_catalog_id}
            onChange={(event) => {
              if (event.target.value === "__custom__") {
                onRequestCustomSection();
                return;
              }
              const selected = availableSections.find((item) => item.id === event.target.value);
              if (!selected) return;
              onChange({
                section_catalog_id: selected.id,
                section_type: selected.family as MemberSpecification["section_type"],
                section_name: selected.designation,
                selection_source: "user_locked",
                override_reason: "用户锁定截面规格",
              });
            }}
          >
            <option value="">请选择</option>
            {availableSections.map((item) => (
              <option key={item.id} value={item.id}>
                {item.designation} · {item.self_weight_kn_m} kN/m
              </option>
            ))}
            <option value="__custom__">＋ 输入自定义尺寸与厚度</option>
          </select>
          <small>目录截面和自定义几何都会参与自重、刚度、位移及基础反力计算。</small>
        </label>
        {lengthField("effective_length_m", "计算长度")}
        {lengthField("unbraced_length_m", "无侧向支撑长度")}
      </div>
      {customSection && <SectionPropertyTrace section={customSection} />}
    </div>
  );
}
