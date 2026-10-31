"use client";

import { ChevronDown } from "lucide-react";
import { HelpTip } from "@/components/help-tip";
import { NumberField } from "@/components/number-field";
import { MODULE_MAP } from "@/lib/modules";
import { SCENE_ADAPTER_FIELDS } from "@/lib/scene-adapter-fields";
import { specialistLabel, type DesignStage, type GroundwaterCondition } from "@/lib/scene-model";
import { SOIL_HINTS, type OptionalNumber, type SceneGeotech } from "@/lib/scene-profiles";
import type { Module, SceneGraphTemplate, SceneVariant } from "@/lib/types";

function optionalNumber(raw: string): OptionalNumber {
  return raw === "" ? "" : Number(raw);
}

function UnitInput({
  label,
  unit,
  value,
  onChange,
  min,
  step,
}: {
  label: string;
  unit: string;
  value: OptionalNumber;
  onChange: (value: OptionalNumber) => void;
  min?: string;
  step: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <div className="input-with-unit">
        <input type="number" min={min} step={step} value={value} onChange={(event) => onChange(optionalNumber(event.target.value))} />
        <span>{unit}</span>
      </div>
    </label>
  );
}

function numericParameter(raw: unknown): number | "" {
  if (raw === "" || raw == null) return "";
  const value = Number(raw);
  return Number.isFinite(value) ? value : "";
}

/** Variant parameters of a legacy scene; number fields keep an emptied value empty. */
export function SceneParameterFields({
  parameters,
  variantParameters,
  onChange,
}: {
  parameters: Record<string, unknown>;
  variantParameters: SceneVariant["parameters"];
  onChange: (key: string, value: unknown) => void;
}) {
  return variantParameters.map((parameter) => (
    <label key={parameter.key}>
      <span>{parameter.label}</span>
      {parameter.value_type === "choice" ? (
        <select value={String(parameters[parameter.key] ?? "")} onChange={(event) => onChange(parameter.key, event.target.value)}>
          {parameter.options.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      ) : (
        <div className="input-with-unit">
          {parameter.value_type === "number" ? (
            <NumberField
              value={numericParameter(parameters[parameter.key])}
              onChange={(value) => onChange(parameter.key, value)}
            />
          ) : (
            <input type="text" value={String(parameters[parameter.key] ?? "")} onChange={(event) => onChange(parameter.key, event.target.value)} />
          )}
          {parameter.unit && <span>{parameter.unit}</span>}
        </div>
      )}
    </label>
  ));
}

/** Generic foundation geotechnical inputs (scheme estimate or project check). */
export function SceneGeotechFields({
  geotech,
  onChange,
}: {
  geotech: SceneGeotech;
  onChange: (patch: Partial<SceneGeotech>) => void;
}) {
  return (
    <>
      <label>
        <span>结果阶段</span>
        <select value={geotech.designStage} onChange={(event) => onChange({ designStage: event.target.value as DesignStage })}>
          <option value="scheme_estimate">方案测算（区域参考）</option>
          <option value="project_check">工程校核（勘察资料）</option>
        </select>
      </label>
      {geotech.designStage === "scheme_estimate" && (
        <label>
          <span>区域土质参考档</span>
          <select
            value={geotech.soilHintId}
            onChange={(event) => {
              const hint = SOIL_HINTS[event.target.value];
              onChange({
                soilHintId: event.target.value,
                ...(hint
                  ? { soilClass: hint.soilClass, bearingCapacity: hint.bearing, bearingSource: "浙江区域参考档，用户已确认现场土质类别" }
                  : {}),
              });
            }}
          >
            {Object.entries(SOIL_HINTS).map(([id, hint]) => (
              <option key={id} value={id}>
                {hint.title}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        <span>现场确认土质类型</span>
        <input value={geotech.soilClass} onChange={(event) => onChange({ soilClass: event.target.value })} />
      </label>
      <label>
        <span>
          地基承载力特征值
          <HelpTip term="地基承载力" what="地基在正常使用条件下允许采用的承载能力。" adopted="方案阶段采用已确认土质档的保守参考值；工程校核采用勘察值。" changeWhen="取得项目岩土勘察报告或现场土质与参考档不符时。" />
        </span>
        <div className="input-with-unit">
          <input
            aria-label="地基承载力特征值"
            type="number"
            min="1"
            value={geotech.bearingCapacity}
            onChange={(event) => onChange({ bearingCapacity: event.target.value ? Number(event.target.value) : "" })}
          />
          <span>kPa</span>
        </div>
      </label>
      <label>
        <span>承载力资料来源</span>
        <input value={geotech.bearingSource} onChange={(event) => onChange({ bearingSource: event.target.value })} />
      </label>
      <label>
        <span>
          基底摩擦系数
          <HelpTip term="基底摩擦系数" what="基础底面与地基土之间的摩擦系数，用于抗滑验算。" adopted="按勘察报告或 GB 50007 表 6.7.5-2 按土类取值；未填写时基础结果保持资料不完整。" changeWhen="取得勘察建议值或土类与参考档不符时。" />
        </span>
        <input
          aria-label="基底摩擦系数"
          type="number"
          min="0.05"
          max="1"
          step="0.05"
          value={geotech.baseFriction}
          placeholder="例如 0.30"
          onChange={(event) => onChange({ baseFriction: optionalNumber(event.target.value) })}
        />
      </label>
      <label>
        <span>
          地下水条件
          <HelpTip term="地下水" what="影响基础有效自重、浮力和土压力的设计水位边界。" adopted="按相对场地 ±0.000 的标高分别记录施工、使用和抗浮水位。" changeWhen="取得勘察、季节最高水位或运营控制水位资料时。" />
        </span>
        <select
          aria-label="地下水条件"
          value={geotech.groundwaterCondition}
          onChange={(event) => onChange({ groundwaterCondition: event.target.value as GroundwaterCondition })}
        >
          <option value="unknown">尚未确认</option>
          <option value="no_influence">有资料证明无影响</option>
          <option value="known_water_table">已知三个设计水位</option>
        </select>
      </label>
      {geotech.groundwaterCondition === "known_water_table" && (
        <>
          <UnitInput label="施工期水位标高" unit="m" step="0.1" value={geotech.constructionWaterLevel} onChange={(constructionWaterLevel) => onChange({ constructionWaterLevel })} />
          <UnitInput label="正常使用水位标高" unit="m" step="0.1" value={geotech.serviceWaterLevel} onChange={(serviceWaterLevel) => onChange({ serviceWaterLevel })} />
          <UnitInput label="抗浮设计水位标高" unit="m" step="0.1" value={geotech.antifloatWaterLevel} onChange={(antifloatWaterLevel) => onChange({ antifloatWaterLevel })} />
        </>
      )}
      <label>
        <span>地下水资料来源</span>
        <input
          value={geotech.groundwaterSource}
          placeholder="勘察报告、水位记录或无影响依据"
          onChange={(event) => onChange({ groundwaterSource: event.target.value })}
        />
      </label>
      {geotech.designStage === "project_check" && (
        <>
          <label>
            <span>勘察报告名称</span>
            <input value={geotech.reportName} onChange={(event) => onChange({ reportName: event.target.value })} />
          </label>
          <label>
            <span>报告日期</span>
            <input type="date" value={geotech.reportDate} onChange={(event) => onChange({ reportDate: event.target.value })} />
          </label>
          <UnitInput label="变形模量" unit="MPa" min="0.1" step="0.1" value={geotech.deformationModulus} onChange={(deformationModulus) => onChange({ deformationModulus })} />
        </>
      )}
    </>
  );
}

const SPECIALIST_OPTIONS: Record<string, Array<[string, string]>> = {
  cap_groundwater_condition: [
    ["no_influence", "有资料证明无地下水影响"],
    ["known_water_table", "已知淹没高度"],
  ],
  base_restraint: [
    ["fixed", "固定"],
    ["pinned", "铰支"],
  ],
  pile_type: [
    ["bored", "灌注桩"],
    ["precast_pipe", "预制管桩"],
    ["precast_square", "预制方桩"],
  ],
};

const CAP_WATER_KEYS = ["cap_submerged_depth_m", "cap_water_unit_weight_kn_m3", "cap_buoyancy_factor_uls"];

// Fields that only apply to one scene family.
const FAMILY_ONLY_FIELDS: Record<string, string> = {
  slab_load_distribution: "boardwalk-platform",
  frame_wind_exposed_height_m: "entrance-frame",
  post_height_m: "signage-billboard",
  // Only the pergola workbench (never this legacy workspace) uses it.
  roof_member_tributary_width_m: "",
};

/** "专项参数" sections for nodes that use dedicated server adapters. */
export function SpecialistParameterSections({
  familyId,
  nodes,
  parameters,
  onChange,
}: {
  familyId: string;
  nodes: SceneGraphTemplate["nodes"];
  parameters: Record<string, unknown>;
  onChange: (nodeId: string, key: string, value: unknown) => void;
}) {
  const nodeInputs = (parameters.scene_node_inputs as Record<string, Record<string, unknown>> | undefined) ?? {};
  return nodes
    .filter((node) => SCENE_ADAPTER_FIELDS[node.calculation_module ?? ""])
    .map((node) => {
      const saved = nodeInputs[node.id] ?? {};
      const definition = MODULE_MAP[node.calculation_module as Module];
      const fields = Object.entries(SCENE_ADAPTER_FIELDS[node.calculation_module!]).filter(
        ([key]) =>
          !(key in parameters) &&
          !(CAP_WATER_KEYS.includes(key) && saved.cap_groundwater_condition !== "known_water_table") &&
          !(key in FAMILY_ONLY_FIELDS && FAMILY_ONLY_FIELDS[key] !== familyId),
      );
      return (
        <details className="settings-section" key={`specialist-${node.id}`}>
          <summary>
            <span>
              <strong>{node.label} · 专项参数</strong>
              <small>按材料、配筋和勘察资料填写；空白项会阻止该节点计算</small>
            </span>
            <ChevronDown size={17} />
          </summary>
          <div className="settings-section-body parameter-grid compact-parameters">
            {fields.map(([key, unit]) => {
              const label = definition.fields.find((field) => field.key === key)?.label ?? specialistLabel(key);
              const options =
                key === "support_condition"
                  ? [["four_edges_simply_supported", "四边简支"], ...(familyId === "boardwalk-platform" ? [] : [["four_edges_fixed", "四边固支"]])]
                  : SPECIALIST_OPTIONS[key];
              const update = (value: unknown) => onChange(node.id, key, value);
              return (
                <label key={key}>
                  <span>{label}</span>
                  {options ? (
                    <select value={String(saved[key] ?? "")} onChange={(event) => update(event.target.value)}>
                      <option value="">请选择</option>
                      {options.map(([value, text]) => (
                        <option key={value} value={value}>
                          {text}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="input-with-unit">
                      <input
                        type={unit === "text" ? "text" : "number"}
                        step="any"
                        value={String(saved[key] ?? "")}
                        onChange={(event) =>
                          update(event.target.value === "" ? undefined : unit === "text" ? event.target.value : Number(event.target.value))
                        }
                      />
                      <span>{unit === "text" ? "" : unit}</span>
                    </div>
                  )}
                </label>
              );
            })}
          </div>
        </details>
      );
    });
}
