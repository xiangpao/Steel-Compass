"use client";

import type { ColumnBaseAssembly } from "@/lib/types";

export function ColumnBaseContactFields({ value, onChange }: {
  value: ColumnBaseAssembly;
  onChange: (changes: Partial<ColumnBaseAssembly>) => void;
}) {
  const springs = value.anchor_springs ?? [];
  return <details className="qa-details">
    <summary>脱开接触与锚栓刚度</summary>
    <small>刚性底板、仅受压支承及仅受拉锚栓；无预拉、无初始间隙。刚度须来自项目计算或试验。求得压力和锚栓拉力不代表底板撬力及局部弯曲验算已完成。</small>
    <label className="qa-field"><span>接触支承刚度（kN/m³）</span>
      <input type="number" min="0" step="any" value={value.contact_stiffness_kn_m3 ?? ""}
        placeholder="脱开接触计算必填"
        onChange={e => onChange({ contact_stiffness_kn_m3: e.target.value === "" ? null : Number(e.target.value) })} />
    </label>
    <label className="qa-field"><span>接触与锚栓刚度来源</span>
      <input value={value.contact_model_source ?? ""} placeholder="计算书/试验编号及版本"
        onChange={e => onChange({ contact_model_source: e.target.value || null })} />
    </label>
    <small>坐标原点为底板中心；X 沿底板长，Y 沿底板宽。每根锚栓分别填写坐标与轴向刚度，不能只填写组总刚度。</small>
    <label className="qa-field"><span>柱周焊缝构造</span>
      <select value={value.continuous_perimeter_weld == null ? "" : String(value.continuous_perimeter_weld)}
        onChange={e => onChange({ continuous_perimeter_weld: e.target.value === "" ? null : e.target.value === "true" })}>
        <option value="">尚未确认</option><option value="true">矩形柱四边连续闭合焊缝</option><option value="false">其他构造（需专项验算）</option>
      </select>
    </label>
    {springs.map((spring, i) => <fieldset key={i}>
      <legend>锚栓 {i + 1}</legend>
      {([ ["x_m", "X 坐标（m）"], ["y_m", "Y 坐标（m）"], ["stiffness_kn_m", "轴向刚度（kN/m）"] ] as const).map(([key, label]) =>
        <label className="qa-field" key={key}><span>{label}</span><input type="number" step="any"
          min={key === "stiffness_kn_m" ? 0 : undefined}
          value={key === "stiffness_kn_m" && spring[key] === 0 ? "" : spring[key]}
          placeholder={key === "stiffness_kn_m" ? "必填正值" : undefined}
          onChange={e => onChange({ anchor_springs: springs.map((item, index) => index === i ? { ...item, [key]: Number(e.target.value) } : item) })} /></label>)}
      <button type="button" className="qa-secondary-action" onClick={() => onChange({ anchor_springs: springs.filter((_, index) => i !== index) })}>移除锚栓 {i + 1} 的刚度记录</button>
    </fieldset>)}
    <button type="button" className="qa-secondary-action" disabled={springs.length >= value.anchor_count}
      onClick={() => onChange({ anchor_springs: [...springs, { x_m: 0, y_m: 0, stiffness_kn_m: 0 }] })}>添加锚栓刚度记录</button>
    {springs.length > 0 && (springs.length !== value.anchor_count || springs.some(s => s.stiffness_kn_m <= 0)) &&
      <p role="status">需填写全部 {value.anchor_count} 根锚栓的独立位置和正刚度后才能保存计算。</p>}
  </details>;
}
