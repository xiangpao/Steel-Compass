"use client";

import { Building2, ChevronRight, MapPin, RefreshCw, Split } from "lucide-react";
import { ColumnBaseContactFields } from "@/components/column-base-contact-fields";
import { NumberField } from "@/components/number-field";
import { CompositeInput, patchItems } from "@/components/pergola/composite-input";
import { selectionDetails, type WorkbenchModel } from "@/components/pergola/workbench-model";
import { SOIL_PRESETS } from "@/lib/pergola-catalog";
import {
  assignFoundationType,
  autoClassifyFoundations,
  detachFoundation,
  updateColumnBase,
  updateFoundationType,
  updatePedestal,
} from "@/lib/pergola-edits";
import type { GeoReport } from "@/lib/pergola-project";
import type { FoundationTypeDefinition, SceneGeometryProfile } from "@/lib/types";

type FoundationType = FoundationTypeDefinition;
type Pedestal = NonNullable<FoundationType["pedestal"]>;
type ColumnBase = NonNullable<SceneGeometryProfile["column_bases"]>[number];

function CheckRow({
  checked,
  title,
  note,
  onChange,
}: {
  checked: boolean;
  title: string;
  note: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="qa-check-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        <strong>{title}</strong>
        <small>{note}</small>
      </span>
    </label>
  );
}

function ShapeGeometryFields({ type, update }: { type: FoundationType; update: (values: Partial<FoundationType>) => void }) {
  if (type.form_id === "spread-stepped") {
    const steps = type.steps ?? [];
    const editStep = (index: number, values: Partial<(typeof steps)[number]>) =>
      update({ steps: steps.map((item, itemIndex) => (itemIndex === index ? { ...item, ...values } : item)) });
    return (
      <div className="qa-property-group">
        <strong>阶形基础分级（1～3级）</strong>
        {steps.map((step, index) => (
          <div key={index} className="qa-step-editor">
            <CompositeInput
              items={[
                { label: `第${index + 1}级长`, value: step.length_m, unit: "m", onChange: (value) => editStep(index, { length_m: value }) },
                { label: "宽", value: step.width_m, unit: "m", onChange: (value) => editStep(index, { width_m: value }) },
                { label: "高", value: step.height_mm, unit: "mm", onChange: (value) => editStep(index, { height_mm: value }) },
              ]}
            />
            <button
              type="button"
              className="qa-inline-remove"
              onClick={() => update({ steps: steps.filter((_, itemIndex) => itemIndex !== index) })}
            >
              删除本级
            </button>
          </div>
        ))}
        {steps.length < 3 && (
          <button
            type="button"
            className="qa-secondary-action"
            onClick={() =>
              update({
                steps: [
                  ...steps,
                  {
                    length_m: Math.max(type.length_m - 0.5 - steps.length * 0.3, 0.3),
                    width_m: Math.max(type.width_m - 0.5 - steps.length * 0.3, 0.3),
                    height_mm: 250,
                  },
                ],
              })
            }
          >
            增加一级台阶
          </button>
        )}
        <small>底板厚度与各级台阶高度分别计入混凝土体积、自重和基础总高度。</small>
      </div>
    );
  }
  if (type.form_id === "spread-tapered") {
    return (
      <div className="qa-property-group">
        <strong>锥形基础坡面</strong>
        <CompositeInput
          items={patchItems(type, update, [
            ["顶台长", "tapered_top_length_m", "m", 0.6],
            ["顶台宽", "tapered_top_width_m", "m", 0.6],
            ["坡面高", "tapered_height_mm", "mm", 300],
          ])}
        />
        <small>按矩形棱台体积计算坡面混凝土量；底板厚度仍单独参与剪切和冲切有效高度。</small>
      </div>
    );
  }
  return null;
}

function PedestalFields({ pedestal, update }: { pedestal: Pedestal; update: (values: Partial<Pedestal>) => void }) {
  return (
    <>
      <CompositeInput
        items={[
          ...patchItems(pedestal, update, [
            ["长", "length_mm", "mm", 500],
            ["宽", "width_mm", "mm", 500],
          ]),
          {
            label: "净高",
            value: pedestal.clear_height_mm ?? 650,
            unit: "mm",
            onChange: (value) => update({ clear_height_mm: value, bottom_elevation_m: (pedestal.top_elevation_m ?? 0) - value / 1000 }),
          },
        ]}
      />
      <div className="qa-two-fields">
        <label className="qa-field">
          <span>纵筋</span>
          <input
            value={`${pedestal.longitudinal_bar_count_x ?? 2}+${pedestal.longitudinal_bar_count_y ?? 2} / Φ${pedestal.longitudinal_bar_diameter_mm ?? 16}`}
            readOnly
          />
        </label>
        <label className="qa-field">
          <span>箍筋</span>
          <input value={`Φ${pedestal.stirrup_diameter_mm ?? 8}@${pedestal.stirrup_spacing_mm ?? 150}`} readOnly />
        </label>
      </div>
      <details className="qa-details">
        <summary>短柱详细配筋与构造</summary>
        <div className="qa-two-fields">
          <label className="qa-field">
            <span>混凝土</span>
            <select value={pedestal.concrete_grade ?? ""} onChange={(event) => update({ concrete_grade: event.target.value })}>
              {["C25", "C30", "C35", "C40"].map((grade) => (
                <option key={grade} value={grade}>
                  {grade}
                </option>
              ))}
            </select>
          </label>
          <label className="qa-field">
            <span>保护层</span>
            <div className="qa-value-unit">
              <input
                type="number"
                min="20"
                max="150"
                value={pedestal.cover_mm ?? ""}
                placeholder="必填"
                onChange={(event) => update({ cover_mm: event.target.value ? Number(event.target.value) : null })}
              />
              <em>mm</em>
            </div>
          </label>
        </div>
        <CompositeInput
          items={patchItems(pedestal, update, [
            ["X边纵筋", "longitudinal_bar_count_x", "根/边", 2],
            ["Y边纵筋", "longitudinal_bar_count_y", "根/边", 2],
            ["纵筋直径", "longitudinal_bar_diameter_mm", "mm", 16],
          ])}
        />
        <CompositeInput
          items={patchItems(pedestal, update, [
            ["箍筋直径", "stirrup_diameter_mm", "mm", 8],
            ["箍筋间距", "stirrup_spacing_mm", "mm", 150],
            ["加密区间距", "confinement_spacing_mm", "mm", 90],
          ])}
        />
        <CompositeInput items={patchItems(pedestal, update, [["插筋锚固", "dowel_anchorage_mm", "mm", 600]])} />
        <div className="qa-two-fields">
          <label className="qa-field">
            <span>插筋连接</span>
            <select value={pedestal.splice_type} onChange={(event) => update({ splice_type: event.target.value as Pedestal["splice_type"] })}>
              <option value="none">不搭接 / 连续钢筋</option>
              <option value="lap">搭接</option>
              <option value="mechanical">机械连接</option>
              <option value="welded">焊接</option>
            </select>
          </label>
          <CheckRow
            checked={pedestal.top_local_reinforcement}
            title="柱脚顶部局部加强筋"
            note="用于底板和锚栓作用区构造记录。"
            onChange={(checked) => update({ top_local_reinforcement: checked })}
          />
        </div>
        <small>
          当前计算覆盖轴压、上拔、双向偏压、双向受剪、纵筋率、箍筋、插筋锚固及地震组合下的轴压比、全高加密和体积配箍筛查；全部仍为 unverified。
        </small>
      </details>
    </>
  );
}

function ColumnBaseFields({ base, update }: { base: ColumnBase; update: (values: Partial<ColumnBase>) => void }) {
  // Optional base-plate dimensions are stored as null when cleared to 0.
  const optional = (label: string, key: keyof ColumnBase & string, unit: string) => ({
    label,
    unit,
    value: (base[key] as number | null | undefined) ?? 0,
    onChange: (value: number) => update({ [key]: value || null } as Partial<ColumnBase>),
  });
  return (
    <details className="qa-details" open>
      <summary>钢柱脚底板、锚栓与焊缝</summary>
      <small>锚栓等级是 4.8 / 5.8 / 8.8 性能等级，不是钢材牌号。旧草稿中的 Q355B 必须重新选择。</small>
      <CompositeInput
        items={patchItems(base, update, [
          ["底板长", "base_plate_length_mm", "mm"],
          ["底板宽", "base_plate_width_mm", "mm"],
          ["底板厚", "base_plate_thickness_mm", "mm"],
        ])}
      />
      <label className="qa-field">
        <span>锚栓性能等级</span>
        <select value={base.anchor_grade} onChange={(event) => update({ anchor_grade: event.target.value })}>
          {!["4.8", "5.8", "8.8"].includes(base.anchor_grade) && <option value={base.anchor_grade}>旧值 {base.anchor_grade}（需改选）</option>}
          <option value="4.8">4.8</option>
          <option value="5.8">5.8</option>
          <option value="8.8">8.8</option>
        </select>
      </label>
      <CompositeInput
        items={patchItems(base, update, [
          ["锚栓直径", "anchor_diameter_mm", "mm"],
          ["锚栓数量", "anchor_count", "根"],
          ["有效埋深", "anchor_embedment_mm", "mm"],
        ])}
      />
      <CompositeInput
        items={[
          optional("锚栓间距", "anchor_spacing_mm", "mm"),
          optional("边距", "anchor_edge_mm", "mm"),
          optional("锚板/锚头直径", "anchor_head_diameter_mm", "mm"),
        ]}
      />
      <CompositeInput
        items={[
          ...patchItems(base, update, [["附加锚固钢筋", "anchor_supplementary_reinforcement_area_mm2", "mm²", 0]]),
          optional("焊脚有效厚度", "weld_throat_mm", "mm"),
        ]}
      />
      <CheckRow
        checked={base.anchor_cracked_concrete ?? true}
        title="按开裂混凝土验算锚固区"
        note="影响劈裂承载力；不能由软件静默假定为不开裂。"
        onChange={(checked) => update({ anchor_cracked_concrete: checked })}
      />
      <label className="qa-field">
        <span>混凝土局部承压设计值</span>
        <div className="qa-value-unit">
          <input
            type="number"
            min="1"
            step="0.5"
            value={base.concrete_bearing_capacity_mpa ?? ""}
            placeholder="必填"
            onChange={(event) => update({ concrete_bearing_capacity_mpa: event.target.value ? Number(event.target.value) : null })}
          />
          <em>MPa</em>
        </div>
        <small>用于柱脚底板下局部承压；工作台不再静默套用单项快算默认值。</small>
      </label>
      <ColumnBaseContactFields value={base} onChange={update} />
    </details>
  );
}

function FoundationInspector({ model }: { model: WorkbenchModel }) {
  const { geometry, setGeometry, setMessage } = model;
  const { foundation, foundationType: type, support, supportNode, columnBase } = selectionDetails(geometry, model.selection);
  if (!foundation || !type) return null;
  const updateType = (values: Partial<FoundationType>) => setGeometry((current) => updateFoundationType(current, type.id, values));
  const updatePedestalOf = (values: Partial<Pedestal>) => setGeometry((current) => updatePedestal(current, type.id, values));
  return (
    <>
      <label className="qa-field">
        <span>基础保护层</span>
        <div className="qa-value-unit">
          <NumberField
            aria-label="基础保护层"
            min="35"
            max="150"
            value={type.cover_mm ?? 50}
            onChange={(value) => updateType({ cover_mm: value })}
          />
          <em>mm</em>
        </div>
        <small>保护层参与有效高度、剪切、冲切和配筋计算，不再使用隐藏默认值。</small>
      </label>
      <ShapeGeometryFields type={type} update={updateType} />
      <div className="qa-inspector-heading">
        <span className="qa-object-mark foundation">{foundation.mark}</span>
        <div>
          <strong>{type.title}</strong>
          <small>{foundation.id}</small>
        </div>
      </div>
      <div className="qa-location-card">
        <MapPin size={17} />
        <div>
          <strong>对应 {foundation.column_member_id ?? "未绑定柱"}</strong>
          <span>
            支承 {support?.id} · X {supportNode?.x_m.toFixed(2)} / Y {supportNode?.y_m.toFixed(2)}
          </span>
        </div>
      </div>
      <div className={`qa-foundation-diagram ${type.form_id.replace("spread-", "")}`} aria-label={`${type.title}剖面示意`}>
        <div className="base" />
        <div className="step" />
        {type.pedestal?.enabled && (
          <div className="pedestal">
            <span>短柱</span>
          </div>
        )}
        <i>基础底板</i>
      </div>
      <label className="qa-field">
        <span>基础类型</span>
        <select value={type.id} onChange={(event) => setGeometry((current) => assignFoundationType(current, foundation.id, event.target.value))}>
          {geometry.foundation_types?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.mark} · {item.title}
            </option>
          ))}
        </select>
      </label>
      <label className="qa-field">
        <span>基础底板形式</span>
        <select value={type.form_id} onChange={(event) => updateType({ form_id: event.target.value })}>
          <option value="spread-stepped">阶形独立基础</option>
          <option value="spread-tapered">锥形独立基础</option>
          <option value="spread-prismatic">等厚独立基础</option>
        </select>
        <small>短柱是附属构造，不是另一种基础形式。</small>
      </label>
      <div className="qa-property-group">
        <strong>类型尺寸（同步全部 {type.mark}）</strong>
        <CompositeInput
          items={patchItems(type, updateType, [
            ["长", "length_m", "m"],
            ["宽", "width_m", "m"],
            ["厚", "thickness_mm", "mm"],
            ["埋深", "embedment_m", "m"],
          ])}
        />
      </div>
      <div className="qa-two-fields">
        {(["bottom_x", "bottom_y"] as const).map((key) => (
          <label className="qa-field" key={key}>
            <span>{key === "bottom_x" ? "X向底筋" : "Y向底筋"}</span>
            <input value={type[key]} onChange={(event) => updateType({ [key]: event.target.value })} />
          </label>
        ))}
        {(["top_x", "top_y"] as const).map((key) => (
          <label className="qa-field" key={key}>
            <span>{key === "top_x" ? "X向顶筋" : "Y向顶筋"}</span>
            <input
              value={type[key] ?? ""}
              placeholder="如 Φ12@150；存在反向弯矩时必填"
              onChange={(event) => updateType({ [key]: event.target.value || null })}
            />
          </label>
        ))}
      </div>
      <div className="qa-property-group">
        <CheckRow
          checked={type.pedestal?.enabled ?? false}
          title="钢筋混凝土短柱"
          note="柱脚高出基础顶超过 150mm 时默认启用；参与自重、力臂、冲切和配筋。"
          onChange={(checked) => updatePedestalOf({ enabled: checked, auto_enabled: false, override_reason: "QA 工作台用户明确选择" })}
        />
        {type.pedestal?.enabled && <PedestalFields pedestal={type.pedestal} update={updatePedestalOf} />}
      </div>
      {columnBase && (
        <ColumnBaseFields base={columnBase} update={(values) => setGeometry((current) => updateColumnBase(current, columnBase.id, values))} />
      )}
      <button
        type="button"
        className="qa-secondary-action"
        onClick={() => {
          const result = detachFoundation(geometry, foundation.id, type);
          setGeometry(result.apply);
          setMessage(`${foundation.mark} 已从原类型分离为 ${result.mark}。`);
        }}
      >
        <Split size={16} />从 {type.mark} 分离为新类型
      </button>
    </>
  );
}

function ReportFields({ report, setReport }: { report: GeoReport; setReport: WorkbenchModel["setReport"] }) {
  const update = (values: Partial<GeoReport>) => setReport((current) => ({ ...current, ...values }));
  return (
    <div className="qa-report-card">
      <label className="qa-field">
        <span>勘察报告名称</span>
        <input value={report.name} onChange={(event) => update({ name: event.target.value })} />
      </label>
      <label className="qa-field">
        <span>报告日期</span>
        <input type="date" value={report.date} onChange={(event) => update({ date: event.target.value })} />
      </label>
      <CompositeInput
        items={patchItems(report, update, [
          ["承载力", "bearing", "kPa"],
          ["压缩模量", "modulus", "MPa"],
        ])}
      />
      <CompositeInput
        items={patchItems(report, update, [
          ["压缩层厚度", "layerThickness", "m"],
          ["土层天然重度", "unitWeight", "kN/m³"],
        ])}
      />
      <CompositeInput
        items={patchItems(report, update, [
          ["沉降经验系数", "settlementFactor", "1"],
          ["允许沉降", "settlementLimit", "mm"],
          ["基底摩擦系数", "friction", "1"],
        ])}
      />
      <CompositeInput
        items={patchItems(report, update, [
          ["施工水位", "construction", "m"],
          ["使用水位", "service", "m"],
          ["抗浮水位", "antifloat", "m"],
        ])}
      />
      <small>报告资料在项目级录入一次，场景直接引用，不再逐项填写来源。</small>
    </div>
  );
}

function FoundationOverview({ model }: { model: WorkbenchModel }) {
  const { geometry, geoStage, setGeoStage, soilPresetId } = model;
  const soil = SOIL_PRESETS.find((item) => item.id === soilPresetId)!;
  return (
    <>
      <div className="qa-panel-title">
        <div>
          <strong>基础与地基</strong>
          <small>按基础类型归类和套用</small>
        </div>
        <Building2 size={18} />
      </div>
      <div className="qa-type-list">
        <div className="qa-list-heading">
          <strong>基础类型</strong>
          <button
            type="button"
            onClick={() => {
              const result = autoClassifyFoundations(geometry);
              model.setGeometry((current) => autoClassifyFoundations(current).geometry);
              model.setMessage(`基础已按几何、材料和配筋自动归为 ${result.count} 类。`);
            }}
          >
            <RefreshCw size={14} />
            自动归类
          </button>
        </div>
        {geometry.foundation_types?.map((type) => (
          <button
            key={type.id}
            type="button"
            onClick={() => {
              const instance = geometry.foundation_instances?.find((item) => item.foundation_type_id === type.id);
              if (instance) model.handleSelection({ kind: "foundation", id: instance.id });
            }}
          >
            <span className="qa-foundation-swatch">{type.mark}</span>
            <div>
              <strong>{type.title}</strong>
              <small>
                {type.length_m}×{type.width_m}×{type.thickness_mm}mm ·{" "}
                {geometry.foundation_instances?.filter((item) => item.foundation_type_id === type.id).length} 处
              </small>
            </div>
            <ChevronRight size={15} />
          </button>
        ))}
      </div>
      <div className="qa-property-group">
        <div className="qa-segmented">
          {(
            [
              ["scheme_estimate", "方案测算"],
              ["project_check", "工程校核"],
            ] as const
          ).map(([stage, label]) => (
            <button key={stage} type="button" className={geoStage === stage ? "active" : ""} onClick={() => setGeoStage(stage)}>
              {label}
            </button>
          ))}
        </div>
        {geoStage === "scheme_estimate" ? (
          <>
            <label className="qa-field">
              <span>持力层参考档</span>
              <select value={soilPresetId} onChange={(event) => model.setSoilPresetId(event.target.value)}>
                {SOIL_PRESETS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="qa-soil-card">
              <span>{soil.title}</span>
              <strong>
                {soil.range[0]}–{soil.range[1]} kPa
              </strong>
              <b>
                方案采用 {soil.adopted} kPa · 基底摩擦系数 {soil.friction.toFixed(2)}
              </b>
              <p>{soil.description}</p>
              <small>{soil.risk}</small>
            </div>
          </>
        ) : (
          <ReportFields report={model.report} setReport={model.setReport} />
        )}
      </div>
    </>
  );
}

export function FoundationPanel({ model }: { model: WorkbenchModel }) {
  const { foundation, foundationType } = selectionDetails(model.geometry, model.selection);
  return foundation && foundationType ? <FoundationInspector model={model} /> : <FoundationOverview model={model} />;
}
