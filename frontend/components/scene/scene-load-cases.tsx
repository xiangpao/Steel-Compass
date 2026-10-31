"use client";

import { AlertTriangle } from "lucide-react";
import { NumberField } from "@/components/number-field";
import { loadRange } from "@/lib/scene-model";
import type { SceneGraphTemplate, SceneLoadCase } from "@/lib/types";

const STANDARD_DIRECTIONS = ["gravity", "uplift", "x_positive", "x_negative", "y_positive", "y_negative"];

const DIRECTION_OPTIONS: Array<[string, string]> = [
  ["gravity", "向下/重力"],
  ["uplift", "上拔/风吸"],
  ["x_positive", "X 正向"],
  ["x_negative", "X 负向"],
  ["y_positive", "Y 正向"],
  ["y_negative", "Y 负向"],
];

const KIND_OPTIONS: Array<[string, string]> = [
  ["dead", "恒载"],
  ["live", "活荷载"],
  ["wind", "风荷载"],
  ["snow", "雪荷载"],
  ["soil", "土压力"],
  ["water", "水压力"],
  ["buoyancy", "浮力"],
  ["custom", "项目资料 / 其他"],
];

const UNIT_OPTIONS: Array<[string, string]> = [
  ["kN/m2", "kN/m²"],
  ["kN/m", "kN/m"],
  ["kN", "kN"],
];

const DISTRIBUTION_OPTIONS: Array<[string, string]> = [
  ["point", "集中荷载"],
  ["line", "线荷载"],
  ["area", "面荷载"],
  ["pressure", "压力"],
];

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, text]) => (
          <option key={optionValue} value={optionValue}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function LoadCaseCard({
  item,
  climateInputsReady,
  nodes,
  onChange,
}: {
  item: SceneLoadCase;
  climateInputsReady: boolean;
  nodes: SceneGraphTemplate["nodes"];
  onChange: (patch: Partial<SceneLoadCase>) => void;
}) {
  const projectDefined = item.value_type === "project_defined";
  const calculated = item.value_type === "calculated";
  // Wind/snow are derived from the project conditions; until those are
  // complete the field stays empty instead of showing a placeholder zero.
  const awaitingConditions = calculated && (item.kind === "wind" || item.kind === "snow") && !climateInputsReady;
  const overridden = !projectDefined && item.recommended_default !== undefined && item.adopted_value !== item.recommended_default;
  return (
    <article className="scene-load-card">
      <div className="load-card-heading">
        <div>
          <strong>{item.label}</strong>
          <span>
            {loadRange(item)} · {item.application_target}
          </span>
        </div>
      </div>
      <div className="load-card-fields">
        <label>
          <span>最终采用值</span>
          <div className="input-with-unit">
            <NumberField
              step="any"
              value={awaitingConditions ? "" : item.adopted_value}
              placeholder={calculated && !climateInputsReady ? "待完成条件" : undefined}
              readOnly={calculated}
              onChange={(adopted) =>
                onChange({
                  adopted_value: adopted,
                  override_reason: adopted !== item.recommended_default ? item.override_reason : undefined,
                })
              }
            />
            <span>{item.unit}</span>
          </div>
        </label>
        {projectDefined ? (
          <SelectField
            label="方向"
            value={item.direction ?? "gravity"}
            options={[
              ...(item.direction && !STANDARD_DIRECTIONS.includes(item.direction)
                ? [[item.direction, item.direction] as [string, string]]
                : []),
              ...DIRECTION_OPTIONS,
            ]}
            onChange={(direction) => onChange({ direction: direction as SceneLoadCase["direction"] })}
          />
        ) : (
          <div className="boundary-note">方向工况由后台自动生成并取控制包络，普通界面无需选择。</div>
        )}
      </div>
      <p>
        {item.source_reference || "来源待填写"} · {item.applicable_when}
      </p>
      {overridden && (
        <label className="override-reason-field">
          <span>覆盖建议值的原因</span>
          <input
            value={item.override_reason ?? ""}
            placeholder="例如：采用项目设备资料或专项复核值"
            onChange={(event) => onChange({ override_reason: event.target.value })}
          />
        </label>
      )}
      {projectDefined && (
        <div className="custom-load-fields">
          <SelectField label="荷载类别" value={item.kind} options={KIND_OPTIONS} onChange={(kind) => onChange({ kind: kind as SceneLoadCase["kind"] })} />
          <SelectField
            label="单位"
            value={item.unit}
            options={UNIT_OPTIONS}
            onChange={(unit) => onChange({ unit, distribution: unit === "kN" ? "point" : unit === "kN/m" ? "line" : "area" })}
          />
          <SelectField
            label="作用目标"
            value={item.application_target}
            options={nodes.map((node) => [node.id, node.label])}
            onChange={(application_target) => onChange({ application_target })}
          />
          <SelectField
            label="分布形式"
            value={item.distribution}
            options={DISTRIBUTION_OPTIONS}
            onChange={(distribution) => onChange({ distribution: distribution as SceneLoadCase["distribution"] })}
          />
          <TextField label="资料名称" value={item.project_source ?? ""} onChange={(project_source) => onChange({ project_source })} />
          <TextField label="页码 / 条款" value={item.source_reference} onChange={(source_reference) => onChange({ source_reference })} />
          <TextField label="说明" value={item.notes ?? ""} onChange={(notes) => onChange({ notes })} />
        </div>
      )}
    </article>
  );
}

export function SceneLoadCases({
  loadCases,
  climateInputsReady,
  nodes,
  onChange,
  onAdd,
}: {
  loadCases: SceneLoadCase[];
  climateInputsReady: boolean;
  nodes: SceneGraphTemplate["nodes"];
  onChange: (index: number, patch: Partial<SceneLoadCase>) => void;
  onAdd: () => void;
}) {
  return (
    <>
      <div className="scene-load-table">
        {loadCases.map((item, index) => (
          <LoadCaseCard
            key={item.id}
            item={item}
            climateInputsReady={climateInputsReady}
            nodes={nodes}
            onChange={(patch) => onChange(index, patch)}
          />
        ))}
      </div>
      <div className="load-table-actions">
        <button className="secondary-button" onClick={onAdd}>
          添加项目资料荷载
        </button>
      </div>
      <div className="boundary-note">
        <AlertTriangle size={17} />
        风雪基本值仍须结合高度、体型和方向系数转换；场景包不替代项目专项资料。
      </div>
    </>
  );
}
