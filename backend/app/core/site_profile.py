from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, Field, model_validator

from . import STANDARD_PROFILE


CLIMATE_PRESET_VERSION = "ZJ-CLIMATE-2026.1-unverified"
SEISMIC_PROFILE_VERSION = "CN-SEISMIC-2026.1-unverified"


class ClimateRegionPreset(BaseModel):
    id: Literal[
        "zhejiang_coastal", "zhejiang_inland", "zhejiang_mountain", "manual"
    ]
    label: str
    station_scope: list[str] = Field(default_factory=list)
    wind_kpa: dict[str, float] = Field(default_factory=dict)
    snow_kpa: dict[str, float] = Field(default_factory=dict)
    source_reference: str
    catalog_version: str = CLIMATE_PRESET_VERSION
    verification_status: Literal["unverified"] = "unverified"


CLIMATE_REGION_PRESETS = [
    ClimateRegionPreset(
        id="zhejiang_coastal",
        label="浙江沿海",
        station_scope=["宁波", "温州", "舟山"],
        wind_kpa={"10": 0.50, "50": 0.85, "100": 1.00},
        snow_kpa={"10": 0.30, "50": 0.50, "100": 0.60},
        source_reference="GB 50009-2012 表 E.5；浙江省工程建设标准相关站点表（组内保守值）",
    ),
    ClimateRegionPreset(
        id="zhejiang_inland",
        label="浙江内陆",
        station_scope=["杭州", "金华", "嵊州", "衢州"],
        wind_kpa={"10": 0.30, "50": 0.45, "100": 0.50},
        snow_kpa={"10": 0.35, "50": 0.55, "100": 0.65},
        source_reference="GB 50009-2012 表 E.5；浙江省工程建设标准相关站点表（组内保守值）",
    ),
    ClimateRegionPreset(
        id="zhejiang_mountain",
        label="浙江山区",
        station_scope=["天目山", "括苍山"],
        wind_kpa={"10": 0.60, "50": 0.90, "100": 1.05},
        snow_kpa={"10": 1.00, "50": 1.60, "100": 1.85},
        source_reference="GB 50009-2012 表 E.5；浙江省工程建设标准相关站点表（组内保守值）",
    ),
    ClimateRegionPreset(
        id="manual",
        label="其他地区手动输入",
        source_reference="用户提供项目所在地资料",
    ),
]


class SeismicDesignProfile(BaseModel):
    level: Literal[
        "6_005g", "7_010g", "7_015g", "8_020g", "8_030g", "9_040g"
    ]
    intensity: Literal[6, 7, 8, 9]
    design_acceleration_g: float
    alpha_max: float
    catalog_version: str = SEISMIC_PROFILE_VERSION
    formula_reference: str = "F_Ek = alpha1 * G_eq；首版按短周期平台段 alpha1=alpha_max"
    source_reference: str = "GB 55002-2021；GB/T 50011-2010（2024年版）"
    verification_status: Literal["unverified"] = "unverified"


SEISMIC_DESIGN_PROFILES = {
    item.level: item
    for item in [
        SeismicDesignProfile(level="6_005g", intensity=6, design_acceleration_g=0.05, alpha_max=0.04),
        SeismicDesignProfile(level="7_010g", intensity=7, design_acceleration_g=0.10, alpha_max=0.08),
        SeismicDesignProfile(level="7_015g", intensity=7, design_acceleration_g=0.15, alpha_max=0.12),
        SeismicDesignProfile(level="8_020g", intensity=8, design_acceleration_g=0.20, alpha_max=0.16),
        SeismicDesignProfile(level="8_030g", intensity=8, design_acceleration_g=0.30, alpha_max=0.24),
        SeismicDesignProfile(level="9_040g", intensity=9, design_acceleration_g=0.40, alpha_max=0.32),
    ]
}


ConditionKey = Literal["wind", "snow", "seismic"]


class ProjectSiteProfile(BaseModel):
    """Persisted, traceable project-wide climate and seismic assumptions.

    Version 1.1 permits a project to collect conditions in stages.  Individual
    scene calculations enforce only the conditions they use, so the service
    never fabricates a climate or seismic value for an unrelated scene.
    """

    profile_version: Literal["1.0", "1.1"] = "1.1"
    completed_conditions: list[ConditionKey] = Field(default_factory=list)
    region_preset: Literal[
        "zhejiang_coastal", "zhejiang_inland", "zhejiang_mountain", "manual"
    ] | None = None
    recurrence_period_years: Literal[10, 50, 100] = 50
    basic_wind_pressure_kpa: float | None = Field(default=None, gt=0)
    basic_snow_pressure_kpa: float | None = Field(default=None, ge=0)
    climate_source_reference: str | None = Field(default=None, min_length=2, max_length=500)
    terrain_category: Literal["A", "B", "C", "D"] = "B"
    structure_shape: Literal["open_frame", "solid_panel", "roof"] = "open_frame"
    roof_form: Literal["flat", "single_slope", "double_slope", "other"] = "flat"
    height_factor_override: float | None = Field(default=None, gt=0)
    wind_shape_factor_override: float | None = Field(default=None, gt=0)
    snow_shape_factor_override: float | None = Field(default=None, gt=0)
    override_reason: str | None = Field(default=None, max_length=500)
    seismic_level: Literal[
        "6_005g", "7_010g", "7_015g", "8_020g", "8_030g", "9_040g"
    ] | None = None
    catalog_versions: dict[str, str] = Field(
        default_factory=lambda: {
            "climate_regions": CLIMATE_PRESET_VERSION,
            "seismic": SEISMIC_PROFILE_VERSION,
            "standards": STANDARD_PROFILE,
        }
    )

    @model_validator(mode="before")
    @classmethod
    def complete_legacy_profiles(cls, raw: object) -> object:
        """Derive completion flags for fully populated pre-1.1 JSON records."""

        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if "completed_conditions" not in data:
            completed: list[str] = []
            if (
                data.get("region_preset")
                and data.get("basic_wind_pressure_kpa") is not None
                and data.get("climate_source_reference")
            ):
                completed.append("wind")
            if (
                data.get("region_preset")
                and data.get("basic_snow_pressure_kpa") is not None
                and data.get("climate_source_reference")
            ):
                completed.append("snow")
            if data.get("seismic_level"):
                completed.append("seismic")
            data["completed_conditions"] = completed
            if data.get("profile_version") is None:
                data["profile_version"] = "1.0" if completed else "1.1"
        return data

    @model_validator(mode="after")
    def validate_traceability(self) -> "ProjectSiteProfile":
        completed = set(self.completed_conditions)
        if len(completed) != len(self.completed_conditions):
            raise ValueError("completed_conditions 不能重复")

        climate_complete = {"wind", "snow"} & completed
        if climate_complete:
            if self.region_preset is None:
                raise ValueError("完成风或雪条件时必须选择地区档")
            if not self.climate_source_reference:
                raise ValueError("完成风或雪条件时必须填写资料来源")
        if "wind" in completed and self.basic_wind_pressure_kpa is None:
            raise ValueError("完成风条件时必须填写基本风压")
        if "snow" in completed and self.basic_snow_pressure_kpa is None:
            raise ValueError("完成雪条件时必须填写基本雪压")
        if "seismic" in completed and self.seismic_level is None:
            raise ValueError("完成地震条件时必须选择设防烈度")
        if (
            self.region_preset == "manual"
            and climate_complete
            and self.climate_source_reference
            and len(self.climate_source_reference.strip()) < 4
        ):
            raise ValueError("其他地区必须填写基本风压、基本雪压的资料来源")
        if any(
            value is not None
            for value in (
                self.height_factor_override,
                self.wind_shape_factor_override,
                self.snow_shape_factor_override,
            )
        ) and not (self.override_reason or "").strip():
            raise ValueError("修改高级系数时必须填写覆盖原因")
        return self

    def is_condition_complete(self, condition: ConditionKey) -> bool:
        return condition in set(self.completed_conditions)

    def require_conditions(self, conditions: Iterable[ConditionKey]) -> None:
        missing = [condition for condition in conditions if not self.is_condition_complete(condition)]
        if missing:
            raise ValueError(f"项目条件未完成：{'、'.join(missing)}")


def climate_region_catalog() -> dict:
    return {
        "version": CLIMATE_PRESET_VERSION,
        "standard_profile": STANDARD_PROFILE,
        "coverage": "zhejiang_screening_presets",
        "verification_status": "unverified",
        "items": [item.model_dump(mode="json") for item in CLIMATE_REGION_PRESETS],
    }


def seismic_design_catalog() -> dict:
    return {
        "version": SEISMIC_PROFILE_VERSION,
        "standard_profile": STANDARD_PROFILE,
        "verification_status": "unverified",
        "items": [item.model_dump(mode="json") for item in SEISMIC_DESIGN_PROFILES.values()],
    }
