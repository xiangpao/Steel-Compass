"use client";

import { useState } from "react";
import { Compass, Plus, X } from "lucide-react";
import { NumberField } from "@/components/number-field";
import { PanelHeader } from "@/components/workspace/panel-header";
import type { ClimateCatalog, LoadCatalog, LoadItem, LoadPreset } from "@/lib/types";

const LOAD_LABELS: Record<LoadItem["kind"], string> = {
  self_weight: "自重",
  dead: "恒载",
  live: "活载",
  wind: "风荷载",
  snow: "雪荷载",
  seismic: "地震作用",
};

type Recurrence = "10" | "50" | "100";

/**
 * Load table of a single calculation, with the preset library and the
 * city wind/snow wizard. Every change goes through onLoadsChange so the
 * caller can invalidate the shown result.
 */
export function CalculationLoadsPanel({
  loads,
  loadCatalog,
  climateCatalog,
  onLoadsChange,
  onError,
}: {
  loads: LoadItem[];
  loadCatalog: LoadCatalog | null;
  climateCatalog: ClimateCatalog | null;
  onLoadsChange: (update: (current: LoadItem[]) => LoadItem[]) => void;
  onError: (message: string) => void;
}) {
  const [loadPickerOpen, setLoadPickerOpen] = useState(false);
  const [climateOpen, setClimateOpen] = useState(false);
  const [climateLocationId, setClimateLocationId] = useState("");
  const [climateKind, setClimateKind] = useState<"wind" | "snow">("wind");
  const [recurrence, setRecurrence] = useState<Recurrence>("50");
  const [heightFactor, setHeightFactor] = useState(1);
  const [shapeFactor, setShapeFactor] = useState(1);
  const locationId = climateLocationId || climateCatalog?.items[0]?.id || "";

  function updateLoad(index: number, patch: Partial<LoadItem>) {
    onLoadsChange((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function addLoadPreset(preset: LoadPreset) {
    if (!["kN/m", "kN/m2", "kN"].includes(preset.unit)) {
      onError(`${preset.label} 是体积重度，需先按实际厚度或体积换算后再添加。`);
      return;
    }
    onLoadsChange((current) => [
      ...current,
      {
        kind: preset.kind,
        value: preset.value,
        unit: preset.unit as LoadItem["unit"],
        source: preset.label,
        preset_id: preset.id,
        source_reference: preset.source_reference,
      },
    ]);
    setLoadPickerOpen(false);
    onError("");
  }

  function addClimateLoad() {
    const location = climateCatalog?.items.find((item) => item.id === locationId);
    const basic = climateKind === "wind" ? location?.wind_kpa[recurrence] : location?.snow_kpa[recurrence];
    if (!location || basic == null) {
      onError("该站点没有所选风压或雪压数据，请改为项目人工输入。");
      return;
    }
    const calculated = basic * heightFactor * shapeFactor;
    onLoadsChange((current) => [
      ...current,
      {
        kind: climateKind,
        value: Number(calculated.toFixed(4)),
        unit: "kN/m2",
        source: `${location.province} ${location.station} · ${recurrence}年重现期`,
        preset_id: `climate:${location.id}:${climateKind}:${recurrence}`,
        source_reference: `GB 50009-2012 表E.5；基本值 ${basic} kN/m²；系数 ${heightFactor}×${shapeFactor}`,
      },
    ]);
    setClimateOpen(false);
    onError("");
  }

  return (
    <section className="panel load-panel">
      <PanelHeader number="02" title="荷载与来源" subtitle="Load cases & provenance" />
      <div className="load-tools">
        <button className="secondary-button" onClick={() => setLoadPickerOpen((current) => !current)}>
          <Plus size={16} /> 常用荷载库
        </button>
        <button className="secondary-button" onClick={() => setClimateOpen((current) => !current)}>
          <Compass size={16} /> 城市风雪向导
        </button>
        <small>目录 {loadCatalog?.version ?? "加载中"} · 采用值直接进入计算</small>
      </div>
      {loadPickerOpen && loadCatalog && (
        <div className="catalog-picker">
          {loadCatalog.items.map((preset) => (
            <button key={preset.id} onClick={() => addLoadPreset(preset)}>
              <span>
                <strong>{preset.label}</strong>
                <small>{preset.source_reference}</small>
              </span>
              <b>
                {preset.value}
                {preset.value_max ? `–${preset.value_max}` : ""} {preset.unit}
              </b>
              <p>{preset.notes}</p>
            </button>
          ))}
        </div>
      )}
      {climateOpen && climateCatalog && (
        <div className="climate-wizard">
          <header>
            <strong>城市风雪荷载向导</strong>
            <small>当前为已复核首批站点；未列地点禁止自动借用邻近城市。</small>
          </header>
          <label>
            <span>气象站</span>
            <select value={locationId} onChange={(event) => setClimateLocationId(event.target.value)}>
              {climateCatalog.items.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.province} · {location.station}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>作用</span>
            <select value={climateKind} onChange={(event) => setClimateKind(event.target.value as "wind" | "snow")}>
              <option value="wind">风荷载</option>
              <option value="snow">雪荷载</option>
            </select>
          </label>
          <label>
            <span>重现期</span>
            <select value={recurrence} onChange={(event) => setRecurrence(event.target.value as Recurrence)}>
              <option value="10">10 年</option>
              <option value="50">50 年</option>
              <option value="100">100 年</option>
            </select>
          </label>
          <label>
            <span>{climateKind === "wind" ? "高度/地面粗糙度系数" : "积雪分布系数"}</span>
            <NumberField min={0} step="0.05" value={heightFactor} onChange={setHeightFactor} />
          </label>
          <label>
            <span>{climateKind === "wind" ? "体型系数" : "屋面积雪系数"}</span>
            <NumberField step="0.05" value={shapeFactor} onChange={setShapeFactor} />
          </label>
          <button className="primary-button" onClick={addClimateLoad}>
            计算并添加
          </button>
        </div>
      )}
      <div className="load-table">
        <div className="load-row load-head">
          <span>类型</span>
          <span>数值</span>
          <span>单位</span>
          <span>来源</span>
          <span />
        </div>
        {loads.map((load, index) => (
          <div className="load-entry" key={`${load.kind}-${index}`}>
            <div className="load-row">
              <select
                value={load.kind}
                onChange={(event) => updateLoad(index, { kind: event.target.value as LoadItem["kind"] })}
              >
                {Object.entries(LOAD_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
              <NumberField min={0} step="any" value={load.value} onChange={(value) => updateLoad(index, { value })} />
              <select
                value={load.unit}
                onChange={(event) => updateLoad(index, { unit: event.target.value as LoadItem["unit"] })}
              >
                <option value="kN/m">kN/m</option>
                <option value="kN/m2">kN/m²</option>
                <option value="kN">kN</option>
              </select>
              <input
                value={load.source}
                placeholder="场景建议值"
                onChange={(event) => updateLoad(index, { source: event.target.value })}
              />
              <button
                className="remove-button"
                onClick={() => onLoadsChange((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                title="删除荷载"
              >
                <X size={15} />
              </button>
            </div>
            {(load.source_reference || load.preset_id) && (
              <div className="load-provenance">
                <span>{load.source_reference}</span>
                {load.preset_id &&
                  loadCatalog?.items.some((preset) => preset.id === load.preset_id && preset.value !== load.value) && (
                    <input
                      value={load.override_reason ?? ""}
                      placeholder="已修改目录建议值，请填写覆盖原因"
                      onChange={(event) => updateLoad(index, { override_reason: event.target.value })}
                    />
                  )}
              </div>
            )}
          </div>
        ))}
      </div>
      <button
        className="text-button"
        onClick={() => onLoadsChange((current) => [...current, { kind: "live", value: 0, unit: "kN/m", source: "" }])}
      >
        <Plus size={16} /> 添加荷载工况
      </button>
    </section>
  );
}
