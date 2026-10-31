"use client";

import { CloudSnow, MapPin, RefreshCw, Trees } from "lucide-react";
import { NumberField } from "@/components/number-field";
import { CompositeInput } from "@/components/pergola/composite-input";
import type { WorkbenchModel } from "@/components/pergola/workbench-model";
import { ROOF_ASSEMBLIES, SITE_PRESETS } from "@/lib/pergola-catalog";
import { initialGeometry } from "@/lib/pergola-geometry";
import { updateRoof } from "@/lib/pergola-edits";
import type { MaintenanceCategory } from "@/lib/pergola-project";
import type { ProjectSiteProfile } from "@/lib/types";

type Condition = "wind" | "snow" | "seismic";

function withCondition(current: ProjectSiteProfile, conditions: Condition[], complete: boolean) {
  const existing = current.completed_conditions ?? [];
  return complete
    ? Array.from(new Set([...existing, ...conditions]))
    : existing.filter((item) => !conditions.includes(item));
}

export function LibraryPanel({ model }: { model: WorkbenchModel }) {
  return (
    <>
      <div className="qa-panel-title">
        <div>
          <strong>场景库</strong>
          <small>保持当前项目条件，不跳回旧首页</small>
        </div>
        <Trees size={18} />
      </div>
      <div className="qa-scene-drawer">
        <button type="button" className="active">
          <strong>亭廊 / 花架</strong>
          <small>当前 Geometry 2.3 模型</small>
        </button>
        {["雨棚", "导视牌", "景墙", "门楼", "栈道 / 平台"].map((title) => (
          <button type="button" key={title} disabled>
            <strong>{title}</strong>
            <small>待共享专业闭环验证后开放</small>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="qa-secondary-action"
        onClick={() => {
          model.setGeometry(initialGeometry());
          model.setSelection(null);
          model.setMessage("已重建干净的 Geometry 2.3 亭廊模型；项目条件保持不变。");
        }}
      >
        <RefreshCw size={16} />
        重建当前亭廊模型
      </button>
      <small>旧 QA 草稿不会自动升级，避免把孤立对象带入正式模型。</small>
    </>
  );
}

export function ConditionsPanel({ model }: { model: WorkbenchModel }) {
  const { siteProfile, setSiteProfile } = model;
  const preset = siteProfile.region_preset ? SITE_PRESETS[siteProfile.region_preset] : null;
  return (
    <>
      <div className="qa-panel-title">
        <div>
          <strong>项目条件</strong>
          <small>项目级保存，荷载自动读取</small>
        </div>
        <MapPin size={18} />
      </div>
      <label className="qa-field">
        <span>地区档</span>
        <select
          value={siteProfile.region_preset ?? ""}
          onChange={(event) => {
            const region = event.target.value as ProjectSiteProfile["region_preset"];
            const values = region ? SITE_PRESETS[region] : null;
            setSiteProfile((current) => ({
              ...current,
              region_preset: region,
              basic_wind_pressure_kpa: values?.wind || null,
              basic_snow_pressure_kpa: values?.snow || null,
              completed_conditions: withCondition(current, ["wind", "snow"], Boolean(region && region !== "manual")),
            }));
          }}
        >
          <option value="">待选择</option>
          {Object.entries(SITE_PRESETS).map(([id, item]) => (
            <option key={id} value={id}>
              {item.title}
            </option>
          ))}
        </select>
      </label>
      <label className="qa-field">
        <span>重现期</span>
        <select
          value={siteProfile.recurrence_period_years}
          onChange={(event) =>
            setSiteProfile((current) => ({ ...current, recurrence_period_years: Number(event.target.value) as 10 | 50 | 100 }))
          }
        >
          <option value={10}>10年</option>
          <option value={50}>50年（默认）</option>
          <option value={100}>100年</option>
        </select>
      </label>
      <CompositeInput
        items={(
          [
            ["基本风压", "basic_wind_pressure_kpa", "wind"],
            ["基本雪压", "basic_snow_pressure_kpa", "snow"],
          ] as const
        ).map(([label, key, condition]) => ({
          label,
          value: siteProfile[key] ?? 0,
          unit: "kPa",
          onChange: (value: number) =>
            setSiteProfile((current) => ({
              ...current,
              [key]: value || null,
              completed_conditions: withCondition(current, [condition], value > 0),
            })),
        }))}
      />
      <label className="qa-field">
        <span>地面环境类别</span>
        <select
          value={siteProfile.terrain_category}
          onChange={(event) => setSiteProfile((current) => ({ ...current, terrain_category: event.target.value as "A" | "B" | "C" | "D" }))}
        >
          <option value="A">A · 近海海面、海岛</option>
          <option value="B">B · 田野、乡村</option>
          <option value="C">C · 城镇密集建筑</option>
          <option value="D">D · 高层密集城区</option>
        </select>
      </label>
      <label className="qa-field">
        <span>抗震设防烈度 / 加速度</span>
        <select
          value={siteProfile.seismic_level ?? ""}
          onChange={(event) => {
            const value = event.target.value as ProjectSiteProfile["seismic_level"];
            setSiteProfile((current) => ({ ...current, seismic_level: value || null, completed_conditions: withCondition(current, ["seismic"], Boolean(value)) }));
          }}
        >
          <option value="">待填写（无隐含默认）</option>
          <option value="6_005g">6度 / 0.05g</option>
          <option value="7_010g">7度 / 0.10g</option>
          <option value="7_015g">7度 / 0.15g</option>
          <option value="8_020g">8度 / 0.20g</option>
          <option value="8_030g">8度 / 0.30g</option>
          <option value="9_040g">9度 / 0.40g</option>
        </select>
      </label>
      <div className="qa-soil-card">
        <span>条件完整性</span>
        <strong>{siteProfile.completed_conditions?.length ?? 0} / 3</strong>
        <p>
          {preset
            ? `${preset.title}：风 ${siteProfile.basic_wind_pressure_kpa ?? "待填"}、雪 ${siteProfile.basic_snow_pressure_kpa ?? "待填"} kPa`
            : "请选择地区或手动填写风雪基本值。"}
        </p>
        <small>{siteProfile.seismic_level ? "地震档已明确。" : "仍缺地震烈度，不会按零地震计算。"}</small>
      </div>
    </>
  );
}

export function LoadPanel({ model }: { model: WorkbenchModel }) {
  const { geometry, siteProfile, roofAssemblyId, maintenanceCategory, maintenanceLoad } = model;
  const rule = geometry.double_slope_rule!;
  const roofAssembly = ROOF_ASSEMBLIES.find((item) => item.id === roofAssemblyId)!;
  const noCover = roofAssemblyId === "none";
  const maintenance = noCover || maintenanceCategory === "none" ? null : maintenanceCategory === "maintenance" ? 0.5 : maintenanceLoad;
  const editRoof = (values: Partial<typeof rule>) => {
    const result = updateRoof(geometry, values);
    model.setGeometry(result.apply);
    model.setMessage(`双坡屋脊已旋转到 ${result.rule.ridge_direction_deg.toFixed(0)}°，构件编号保持不变。`);
  };
  return (
    <>
      <div className="qa-panel-title">
        <div>
          <strong>屋面与荷载</strong>
          <small>方向变化立即更新三维标高</small>
        </div>
        <CloudSnow size={18} />
      </div>
      <div className="qa-property-group">
        <strong>双坡屋盖</strong>
        <label className="qa-field">
          <span>屋脊方向</span>
          <div className="qa-value-unit">
            <NumberField
              aria-label="屋脊方向"
              min="0"
              max="359"
              value={rule.ridge_direction_deg}
              onChange={(value) => editRoof({ ridge_direction_deg: value })}
            />
            <em>°</em>
          </div>
          <small>0° 为 X 向屋脊，90° 为 Y 向屋脊。</small>
        </label>
        <label className="qa-field">
          <span>屋脊位置</span>
          <input
            type="range"
            min="0.1"
            max="0.9"
            step="0.05"
            value={rule.ridge_offset_ratio}
            onChange={(event) => editRoof({ ridge_offset_ratio: Number(event.target.value) })}
          />
          <small>距一侧边界 {(rule.ridge_offset_ratio * 100).toFixed(0)}%</small>
        </label>
        <CompositeInput
          items={[
            { label: "左坡", value: rule.left_slope_deg, unit: "°", onChange: (value) => editRoof({ left_slope_deg: value }) },
            { label: "右坡", value: rule.right_slope_deg, unit: "°", onChange: (value) => editRoof({ right_slope_deg: value }) },
          ]}
        />
      </div>
      <label className="qa-field">
        <span>屋面构造</span>
        <select
          value={roofAssemblyId}
          onChange={(event) => {
            model.setRoofAssemblyId(event.target.value);
            if (event.target.value === "none") model.setMaintenanceCategory("none");
          }}
        >
          {ROOF_ASSEMBLIES.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
        <small>
          {roofAssembly.layers.map((item) => `${item.name} ${item.surface_weight_kn_m2}kN/m²`).join("；") || "无构造层"}
          。参考范围 {roofAssembly.reference_range_kn_m2[0]}–{roofAssembly.reference_range_kn_m2[1]} kN/m²。
        </small>
      </label>
      <label className="qa-field">
        <span>屋面使用 / 检修类别</span>
        <select
          value={maintenanceCategory}
          disabled={noCover}
          onChange={(event) => model.setMaintenanceCategory(event.target.value as MaintenanceCategory)}
        >
          <option value="none">无顶部覆盖，不适用</option>
          <option value="maintenance">不上人屋面检修</option>
          <option value="walkway">设检修走道或设备</option>
          <option value="occupied">可上人平台</option>
          <option value="custom">自定义</option>
        </select>
      </label>
      {maintenanceCategory !== "none" && maintenanceCategory !== "maintenance" && (
        <label className="qa-field">
          <span>采用面荷载</span>
          <div className="qa-value-unit">
            <NumberField min="0" step="0.1" value={maintenanceLoad} onChange={model.setMaintenanceLoad} />
            <em>kN/m²</em>
          </div>
        </label>
      )}
      <div className="qa-load-cards">
        <div>
          <span>屋面构造恒载</span>
          <strong>{roofAssembly.total_dead_load_kn_m2.toFixed(2)} kN/m²</strong>
          <small>{roofAssembly.source_reference}</small>
        </div>
        <div>
          <span>检修 / 使用荷载</span>
          <strong>{maintenance === null ? "不适用" : `${maintenance.toFixed(2)} kN/m²`}</strong>
          <small>{maintenanceCategory === "maintenance" ? "集中检修作用仍需独立检查" : "按所选类别生成"}</small>
        </div>
        <div>
          <span>屋面雪荷载</span>
          <strong>
            {noCover
              ? "不适用"
              : siteProfile.basic_snow_pressure_kpa
                ? `${siteProfile.basic_snow_pressure_kpa.toFixed(2)} kPa 基本值`
                : "待填写地区"}
          </strong>
          <small>{noCover ? "无顶部覆盖不生成屋面雪" : "坡度与分区系数由模型生成"}</small>
        </div>
        <div>
          <span>风 / 地震</span>
          <strong>
            {siteProfile.basic_wind_pressure_kpa ? `风 ${siteProfile.basic_wind_pressure_kpa.toFixed(2)} kPa` : "风待填写"} ·{" "}
            {siteProfile.seismic_level ?? "地震待填写"}
          </strong>
          <small>自动生成 ±X / ±Y，条件不足不进入完整分析</small>
        </div>
      </div>
    </>
  );
}
