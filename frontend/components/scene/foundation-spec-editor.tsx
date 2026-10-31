"use client";

import { NumberField } from "@/components/number-field";
import type { FoundationDesignSpecification } from "@/lib/types";

type Spec = FoundationDesignSpecification;
type Reinforcement = NonNullable<Spec["reinforcement"]>;
type Shape = "prismatic" | "stepped" | "tapered";

const DEFAULT_PEDESTAL = {
  enabled: true,
  length_mm: 500,
  width_mm: 500,
  height_mm: 600,
  longitudinal_bar_count: 8,
  longitudinal_bar_diameter_mm: 16,
  stirrup_diameter_mm: 8,
  stirrup_spacing_mm: 150,
};

export function defaultFoundationStep(spec: Pick<Spec, "length_m" | "width_m">) {
  return { length_m: Math.max(0.5, spec.length_m - 0.6), width_m: Math.max(0.5, spec.width_m - 0.6), height_mm: 250 };
}

function reinforcementOf(spec: Spec): Reinforcement {
  return {
    bottom_x_diameter_mm: spec.reinforcement?.bottom_x_diameter_mm ?? spec.bar_diameter_mm,
    bottom_x_spacing_mm: spec.reinforcement?.bottom_x_spacing_mm ?? spec.bar_spacing_mm,
    bottom_y_diameter_mm: spec.reinforcement?.bottom_y_diameter_mm ?? spec.bar_diameter_mm,
    bottom_y_spacing_mm: spec.reinforcement?.bottom_y_spacing_mm ?? spec.bar_spacing_mm,
  };
}

function withShape(spec: Spec, shape: Shape): Spec {
  return {
    ...spec,
    section_shape: shape,
    steps: shape === "stepped" ? (spec.steps?.length ? spec.steps : [defaultFoundationStep(spec)]) : [],
    tapered_top_length_m: shape === "tapered" ? (spec.tapered_top_length_m ?? 0.6) : null,
    tapered_top_width_m: shape === "tapered" ? (spec.tapered_top_width_m ?? 0.6) : null,
  };
}

const DIMENSIONS: Array<{ key: "length_m" | "width_m" | "thickness_mm" | "embedment_m"; label: string; unit: string; min: number; step: number; reason: string }> = [
  { key: "length_m", label: "基础长", unit: "m", min: 0.5, step: 0.1, reason: "用户调整基础尺寸" },
  { key: "width_m", label: "基础宽", unit: "m", min: 0.5, step: 0.1, reason: "用户调整基础尺寸" },
  { key: "thickness_mm", label: "基础厚度", unit: "mm", min: 200, step: 50, reason: "用户调整基础尺寸" },
  { key: "embedment_m", label: "基础埋深", unit: "m", min: 0, step: 0.1, reason: "用户调整基础埋深" },
];

// X bars also update the legacy single bar_diameter/bar_spacing fields.
const BARS: Array<{ key: keyof Reinforcement; label: string; min: number; max: number; step: number; legacy?: "bar_diameter_mm" | "bar_spacing_mm" }> = [
  { key: "bottom_x_diameter_mm", label: "X向底筋直径", min: 6, max: 40, step: 1, legacy: "bar_diameter_mm" },
  { key: "bottom_x_spacing_mm", label: "X向底筋间距", min: 50, max: 400, step: 10, legacy: "bar_spacing_mm" },
  { key: "bottom_y_diameter_mm", label: "Y向底筋直径", min: 6, max: 40, step: 1 },
  { key: "bottom_y_spacing_mm", label: "Y向底筋间距", min: 50, max: 400, step: 10 },
];

function UnitNumber({
  label,
  unit,
  value,
  onChange,
  ...rest
}: {
  label: string;
  unit: string;
  value: number | null | undefined;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label>
      <span>{label}</span>
      <div className="input-with-unit">
        <NumberField value={value} onChange={onChange} {...rest} />
        <span>{unit}</span>
      </div>
    </label>
  );
}

/** Editor for one spread or strip footing specification of the scene workspace. */
export function FoundationSpecEditor({
  specification,
  nodeLabel,
  onChange,
}: {
  specification: Spec;
  nodeLabel?: string;
  onChange: (update: (current: Spec) => Spec) => void;
}) {
  const spread = specification.foundation_system_id === "spread";
  const reinforcement = reinforcementOf(specification);
  return (
    <div className="scene-climate-guide">
      <div>
        <strong>
          {nodeLabel} · {spread ? "独立基础" : "条形基础"}
        </strong>
        <span>尺寸为显式起始候选；不满足时返回失败，不自动切换桩基。</span>
      </div>
      <div className="parameter-grid compact-parameters">
        {spread && (
          <label>
            <span>基础形式</span>
            <select
              value={specification.section_shape ?? "stepped"}
              onChange={(event) => {
                const shape = event.target.value as Shape;
                onChange((current) => withShape(current, shape));
              }}
            >
              <option value="stepped">阶形独立基础</option>
              <option value="tapered">锥形独立基础</option>
              <option value="prismatic">等厚独立基础</option>
            </select>
          </label>
        )}
        {DIMENSIONS.map(({ key, label, unit, min, step, reason }) => (
          <UnitNumber
            key={key}
            label={label}
            unit={unit}
            min={min}
            step={step}
            value={specification[key]}
            onChange={(value) =>
              onChange((current) => ({ ...current, [key]: value, selection_source: "user_locked", override_reason: reason }))
            }
          />
        ))}
        <label>
          <span>混凝土等级</span>
          <select
            value={specification.concrete_grade}
            onChange={(event) => {
              const concrete_grade = event.target.value;
              onChange((current) => ({ ...current, concrete_grade }));
            }}
          >
            <option>C25</option>
            <option>C30</option>
            <option>C35</option>
            <option>C40</option>
          </select>
        </label>
        <label>
          <span>钢筋等级</span>
          <select
            value={specification.rebar_grade}
            onChange={(event) => {
              const rebar_grade = event.target.value;
              onChange((current) => ({ ...current, rebar_grade }));
            }}
          >
            <option>HRB400</option>
            <option>HRB500</option>
          </select>
        </label>
        {BARS.map(({ key, label, legacy, ...limits }) => (
          <UnitNumber
            key={key}
            label={label}
            unit="mm"
            {...limits}
            value={reinforcement[key]}
            onChange={(value) =>
              onChange((current) => ({
                ...current,
                ...(legacy ? { [legacy]: value } : {}),
                reinforcement: { ...reinforcementOf(current), [key]: value },
              }))
            }
          />
        ))}
        {spread && (
          <label className="toggle-field">
            <span>钢筋混凝土短柱</span>
            <button
              type="button"
              className={specification.pedestal?.enabled ? "toggle active" : "toggle"}
              aria-pressed={Boolean(specification.pedestal?.enabled)}
              onClick={() =>
                onChange((current) => ({
                  ...current,
                  pedestal: current.pedestal?.enabled ? { enabled: false } : DEFAULT_PEDESTAL,
                }))
              }
            >
              <span />
            </button>
          </label>
        )}
        {specification.pedestal?.enabled && (
          <>
            <UnitNumber
              label="短柱截面"
              unit="mm"
              min={150}
              step={50}
              value={specification.pedestal.length_mm ?? 500}
              onChange={(value) =>
                onChange((current) => ({ ...current, pedestal: { ...current.pedestal!, length_mm: value, width_mm: value } }))
              }
            />
            <UnitNumber
              label="短柱净高"
              unit="mm"
              min={100}
              step={50}
              value={specification.pedestal.height_mm ?? 600}
              onChange={(value) =>
                onChange((current) => ({ ...current, pedestal: { ...current.pedestal!, height_mm: value } }))
              }
            />
          </>
        )}
      </div>
    </div>
  );
}
