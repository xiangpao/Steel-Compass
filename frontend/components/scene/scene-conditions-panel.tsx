"use client";

import { useState } from "react";
import { HelpTip } from "@/components/help-tip";
import type {
  OptionalNumber,
  SceneConditions,
  SceneExposure,
  SemanticFactors,
  TopCover,
  VerticalEnclosure,
} from "@/lib/scene-profiles";
import type { SnowExposure } from "@/lib/scene-model";
import type { ClimateRegionCatalog, ClimateRegionId, RoofAssembly, SceneConditionProfile, SeismicDesignCatalog, SeismicLevel } from "@/lib/types";

function optionalNumber(raw: string): OptionalNumber {
  return raw === "" ? "" : Number(raw);
}

function RatioField({ label, value, onChange }: { label: string; value: OptionalNumber; onChange: (value: OptionalNumber) => void }) {
  return (
    <label>
      <span>{label}</span>
      <div className="input-with-unit">
        <input type="number" min="0" max="1" step="0.05" value={value} onChange={(event) => onChange(optionalNumber(event.target.value))} />
        <span>0–1</span>
      </div>
    </label>
  );
}

/** "统一项目条件向导": region, climate, seismic and surface exposure of a legacy scene. */
export function SceneConditionsPanel({
  conditionProfile,
  needs,
  conditions,
  onConditionsChange,
  exposure,
  onExposureChange,
  climateCatalog,
  seismicCatalog,
  selectedClimate,
  factors,
  climateInputsReady,
  roofAssemblies,
}: {
  conditionProfile: SceneConditionProfile;
  needs: { wind: boolean; snow: boolean; seismic: boolean };
  conditions: SceneConditions;
  onConditionsChange: (patch: Partial<SceneConditions>) => void;
  exposure: SceneExposure;
  onExposureChange: (patch: Partial<SceneExposure>) => void;
  climateCatalog?: ClimateRegionCatalog | null;
  seismicCatalog?: SeismicDesignCatalog | null;
  selectedClimate: ClimateRegionCatalog["items"][number] | undefined;
  factors: SemanticFactors;
  climateInputsReady: boolean;
  roofAssemblies: RoofAssembly[];
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const climate = needs.wind || needs.snow;
  const manual = conditions.climateLocationId === "manual";
  const { recurrence } = conditions;
  const set = onConditionsChange;
  return (
    <div className="scene-climate-guide">
      <div>
        <strong>统一项目条件向导</strong>
        <span>仅显示当前场景需要的地区、气象和地震条件；自动值会随修订一并留存。</span>
      </div>
      {needs.wind && (
        <div className="parameter-grid compact-parameters">
          <label>
            <span>竖向围护</span>
            <select
              value={exposure.verticalEnclosure}
              onChange={(event) => onExposureChange({ verticalEnclosure: event.target.value as VerticalEnclosure })}
            >
              <option value="none">无围护</option>
              <option value="open_members">格栅/杆件</option>
              <option value="perforated_panel">穿孔板</option>
              <option value="solid_panel">实体面板</option>
            </select>
          </label>
          {(exposure.verticalEnclosure === "open_members" || exposure.verticalEnclosure === "perforated_panel") && (
            <RatioField label="竖向开孔率" value={exposure.verticalOpenRatio} onChange={(verticalOpenRatio) => onExposureChange({ verticalOpenRatio })} />
          )}
          <label>
            <span>顶部覆盖</span>
            <select value={exposure.topCover} onChange={(event) => onExposureChange({ topCover: event.target.value as TopCover })}>
              <option value="none">无顶部覆盖</option>
              <option value="louver_grid">百叶/格栅</option>
              <option value="permeable_cover">透水覆盖</option>
              <option value="solid_roof">实体屋盖</option>
            </select>
          </label>
          {exposure.topCover !== "none" && (
            <label>
              <span>屋面构造</span>
              <select value={exposure.roofAssemblyId} onChange={(event) => onExposureChange({ roofAssemblyId: event.target.value })}>
                {roofAssemblies
                  .filter((item) => item.id !== "none")
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title} · {item.total_dead_load_kn_m2} kN/m²
                    </option>
                  ))}
              </select>
              <small>{roofAssemblies.find((item) => item.id === exposure.roofAssemblyId)?.source_reference}</small>
            </label>
          )}
          {(exposure.topCover === "louver_grid" || exposure.topCover === "permeable_cover") && (
            <RatioField label="顶部开孔率" value={exposure.topOpenRatio} onChange={(topOpenRatio) => onExposureChange({ topOpenRatio })} />
          )}
        </div>
      )}
      {conditionProfile.wind === "optional" && (
        <label className="toggle-field">
          <span>施工阶段临时风工况</span>
          <button
            type="button"
            className={conditions.optionalWindEnabled ? "toggle active" : "toggle"}
            aria-pressed={conditions.optionalWindEnabled}
            onClick={() => set({ optionalWindEnabled: !conditions.optionalWindEnabled })}
          >
            <span />
          </button>
        </label>
      )}
      <div className="climate-guide-grid">
        {climate && (
          <>
            <label>
              <span>地区档</span>
              <select
                value={conditions.climateLocationId}
                onChange={(event) => set({ climateLocationId: event.target.value as ClimateRegionId })}
              >
                {(climateCatalog?.items ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
              {selectedClimate && selectedClimate.station_scope.length > 0 && (
                <small>站点范围：{selectedClimate.station_scope.join("、")}</small>
              )}
            </label>
            <label>
              <span>
                重现期
                <HelpTip term="重现期" what="统计意义上某一荷载水平平均再次出现的时间。" adopted="默认采用 50 年，并从所选地区档读取对应基本值。" changeWhen="项目任务书或当地资料明确要求 10 年或 100 年时。" />
              </span>
              <select value={recurrence} onChange={(event) => set({ recurrence: event.target.value as SceneConditions["recurrence"] })}>
                <option value="10">10 年</option>
                <option value="50">50 年（默认）</option>
                <option value="100">100 年</option>
              </select>
            </label>
          </>
        )}
        {manual && needs.wind && (
          <label>
            <span>
              基本风压 (kPa)
              <HelpTip term="基本风压" what="项目所在地规范站点给出的基准风作用。" adopted="与环境和场景自动形态系数相乘。" changeWhen="使用项目所在地正式资料或专项风环境成果时。" />
            </span>
            <input type="number" min="0.01" step="0.01" value={conditions.manualWind} onChange={(event) => set({ manualWind: optionalNumber(event.target.value) })} />
          </label>
        )}
        {manual && needs.snow && (
          <label>
            <span>基本雪压 (kPa)</span>
            <input type="number" min="0" step="0.01" value={conditions.manualSnow} onChange={(event) => set({ manualSnow: optionalNumber(event.target.value) })} />
          </label>
        )}
        {manual && climate && (
          <label>
            <span>资料来源</span>
            <input value={conditions.manualClimateSource} onChange={(event) => set({ manualClimateSource: event.target.value })} placeholder="资料名称、页码或条款" />
          </label>
        )}
        {needs.wind && (
          <label>
            <span>
              环境类型
              <HelpTip term="地面粗糙度" what="周边地表对近地风速的影响类别。" adopted="转成自动高度/地形系数，不要求直接填写系数。" changeWhen="项目位于海岸、密集城区或地貌与默认值明显不同。" />
            </span>
            <select value={conditions.terrainCategory} onChange={(event) => set({ terrainCategory: event.target.value as SceneConditions["terrainCategory"] })}>
              <option value="A">开阔海岸</option>
              <option value="B">乡村 / 郊野</option>
              <option value="C">一般城市</option>
              <option value="D">密集城区</option>
            </select>
          </label>
        )}
        {needs.snow && conditionProfile.snow_semantics === "exposed_horizontal" && (
          <label>
            <span>露天积雪是否适用</span>
            <select value={conditions.snowExposure} onChange={(event) => set({ snowExposure: event.target.value as SnowExposure })}>
              <option value="exposed">适用露天积雪规则</option>
              <option value="not_applicable">本项目不计积雪</option>
            </select>
          </label>
        )}
        {needs.snow && conditions.snowExposure === "not_applicable" && (
          <label>
            <span>不计积雪依据</span>
            <input value={conditions.snowExemptionReason} onChange={(event) => set({ snowExemptionReason: event.target.value })} placeholder="项目所在地资料、任务书或专项说明" />
          </label>
        )}
        {needs.seismic && (
          <label>
            <span>
              地震烈度 / 设计基本加速度
              <HelpTip term="设防烈度" what="项目所在地抗震设防要求，与设计基本加速度成对使用。" adopted="按所选档生成正负 X/Y 等效水平地震作用。" changeWhen="以项目抗震设防资料或当地主管部门要求为准。" />
            </span>
            <select
              aria-label="地震烈度与设计基本加速度"
              value={conditions.seismicLevel}
              onChange={(event) => set({ seismicLevel: event.target.value as SeismicLevel | "" })}
            >
              <option value="">请选择（必填）</option>
              {(seismicCatalog?.items ?? []).map((item) => (
                <option key={item.level} value={item.level}>
                  {item.intensity}度 / {item.design_acceleration_g.toFixed(2)}g
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {climate && (
        <div className="boundary-note success-note">
          基本值{" "}
          {selectedClimate && !manual
            ? `${needs.wind ? `风 ${selectedClimate.wind_kpa[recurrence]} kPa` : ""}${needs.wind && needs.snow ? " / " : ""}${needs.snow ? `雪 ${selectedClimate.snow_kpa[recurrence]} kPa` : ""}`
            : "待填写"}
          {needs.wind && ` → 风系数 ${factors.heightFactor}×${factors.windShape}`}
          {needs.snow && conditions.snowExposure === "exposed" && ` → 积雪系数 ${factors.snowShape}`}
          → 最终采用值写入下方荷载与报告
        </div>
      )}
      {climate && (
        <button type="button" className="secondary-button" onClick={() => setAdvancedOpen((value) => !value)} aria-expanded={advancedOpen}>
          高级参数
        </button>
      )}
      {advancedOpen && climate && (
        <div className="climate-guide-grid">
          {needs.wind && (
            <label>
              <span>高度系数覆盖值</span>
              <input type="number" min="0.01" step="0.05" value={conditions.heightFactorOverride} onChange={(event) => set({ heightFactorOverride: optionalNumber(event.target.value) })} />
            </label>
          )}
          {needs.wind && (
            <label>
              <span>
                体型系数覆盖值
                <HelpTip term="体型系数" what="构筑物外形对局部风作用的放大或减小影响。" adopted="按当前场景的屋盖、面板或构架类型自动取值。" changeWhen="已有专项风洞、产品资料或明确规范取值时。" />
              </span>
              <input type="number" min="0.01" step="0.05" value={conditions.shapeFactorOverride} onChange={(event) => set({ shapeFactorOverride: optionalNumber(event.target.value) })} />
            </label>
          )}
          {needs.snow && (
            <label>
              <span>
                积雪系数覆盖值
                <HelpTip term="积雪系数" what="屋面或露天水平面上积雪分布的换算系数。" adopted="按场景屋面形式或露天水平面规则自动取值。" changeWhen="屋面构造、积雪易堆积部位或专项资料明确不同取值时。" />
              </span>
              <input type="number" min="0.01" step="0.05" value={conditions.snowFactorOverride} onChange={(event) => set({ snowFactorOverride: optionalNumber(event.target.value) })} />
            </label>
          )}
          <label>
            <span>覆盖原因</span>
            <input value={conditions.factorOverrideReason} onChange={(event) => set({ factorOverrideReason: event.target.value })} />
          </label>
        </div>
      )}
      {climate && (
        <div className="boundary-note success-note">
          {climateInputsReady
            ? "荷载已随地区、屋面、坡度和高度自动更新"
            : "待填写完整地区、屋面或气象资料后自动计算；未完成值不会作为零荷载参与计算"}
        </div>
      )}
    </div>
  );
}
