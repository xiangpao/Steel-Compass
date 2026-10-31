"use client";

import { useEffect, useMemo, type Dispatch, type SetStateAction } from "react";
import type { SceneConditions, SceneExposure, SemanticFactors } from "@/lib/scene-profiles";
import type { ClimateRegionCatalog, RoofAssembly, SceneConditionProfile, SceneLoadCase, SceneVariant } from "@/lib/types";

/**
 * Keeps the condition-driven load cases of a legacy scene in step with the
 * project conditions: wind and snow from the region/climate inputs and the
 * roof finish from the selected roof assembly. Returns whether the climate
 * inputs are complete; until then wind/snow are left untouched rather than
 * being written as zero.
 */
export function useConditionDrivenLoads({
  needs,
  conditions,
  conditionProfile,
  exposure,
  factors,
  climateCatalog,
  roofAssemblies,
  variant,
  setLoadCases,
  setParameters,
  onLoadsChanged,
}: {
  needs: { wind: boolean; snow: boolean };
  conditions: SceneConditions;
  conditionProfile: SceneConditionProfile;
  exposure: SceneExposure;
  factors: SemanticFactors;
  climateCatalog?: ClimateRegionCatalog | null;
  roofAssemblies: RoofAssembly[];
  variant: SceneVariant | undefined;
  setLoadCases: Dispatch<SetStateAction<SceneLoadCase[]>>;
  setParameters: Dispatch<SetStateAction<Record<string, unknown>>>;
  onLoadsChanged: () => void;
}) {
  const selectedClimate = climateCatalog?.items.find((item) => item.id === conditions.climateLocationId);
  const { wind: needsWind, snow: needsSnow } = needs;

  const climateInputsReady = useMemo(() => {
    if (!(needsWind || needsSnow)) return true;
    if (conditions.climateLocationId === "manual") {
      return (
        (!needsWind || (conditions.manualWind !== "" && Number(conditions.manualWind) > 0)) &&
        (!needsSnow || (conditions.manualSnow !== "" && Number(conditions.manualSnow) >= 0)) &&
        conditions.manualClimateSource.trim().length >= 4
      );
    }
    return Boolean(selectedClimate);
  }, [needsWind, needsSnow, conditions, selectedClimate]);

  useEffect(() => {
    if (!climateInputsReady || !(needsWind || needsSnow)) return;
    const manual = conditions.climateLocationId === "manual";
    const basicWind = manual ? Number(conditions.manualWind) : Number(selectedClimate?.wind_kpa[conditions.recurrence]);
    const basicSnow = manual ? Number(conditions.manualSnow) : Number(selectedClimate?.snow_kpa[conditions.recurrence]);
    const windAdopted = Number((basicWind * factors.heightFactor * factors.windShape).toFixed(3));
    const snowAdopted = Number((basicSnow * factors.snowShape).toFixed(3));
    const noSnow = conditions.snowExposure === "not_applicable";
    setLoadCases((current) => {
      let changed = false;
      const next = current.map((item) => {
        const adopted =
          item.kind === "wind" && needsWind ? windAdopted : item.kind === "snow" && needsSnow ? (noSnow ? 0 : snowAdopted) : null;
        if (adopted === null || item.adopted_value === adopted) return item;
        changed = true;
        return {
          ...item,
          value_type: item.kind === "snow" && noSnow ? ("project_defined" as const) : ("calculated" as const),
          adopted_value: adopted,
          source_reference: `${climateCatalog?.version ?? "climate"} · ${conditions.recurrence}年 · 自动随项目条件更新`,
          override_reason: "统一项目条件向导自动采用",
        };
      });
      if (changed) onLoadsChanged();
      return changed ? next : current;
    });
    const drivenWindParameter = variant?.parameters.find((parameter) => parameter.hidden_when_condition_driven);
    if (needsWind && drivenWindParameter) {
      setParameters((current) =>
        current[drivenWindParameter.key] === windAdopted ? current : { ...current, [drivenWindParameter.key]: windAdopted },
      );
    }
    // onLoadsChanged only bumps a counter; the setters are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [climateInputsReady, needsWind, needsSnow, conditions, selectedClimate, factors, climateCatalog?.version, variant]);

  useEffect(() => {
    if (conditionProfile.wind_semantics !== "roof") return;
    const assembly = roofAssemblies.find((item) => item.id === exposure.roofAssemblyId);
    if (!assembly) return;
    setLoadCases((current) =>
      current.map((item) =>
        item.id === "roof-finish" || item.id === "canopy-finish"
          ? {
              ...item,
              adopted_value: exposure.topCover === "none" ? 0 : assembly.total_dead_load_kn_m2,
              value_type: "calculated" as const,
              source_reference: `${assembly.source_reference} · ${assembly.reference_range_kn_m2[0]}～${assembly.reference_range_kn_m2[1]} kN/m²`,
            }
          : item,
      ),
    );
  }, [conditionProfile.wind_semantics, roofAssemblies, exposure.roofAssemblyId, exposure.topCover, setLoadCases]);

  return { selectedClimate, climateInputsReady };
}
