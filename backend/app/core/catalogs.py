from __future__ import annotations

from . import STANDARD_PROFILE

from math import pi


MATERIAL_CATALOG_VERSION = "CN-MATERIAL-2024.1"
LOAD_CATALOG_VERSION = "CN-LOAD-2024.2"
CLIMATE_CATALOG_VERSION = "GB50009-E5-2012.1"


def _areas(diameters: list[int]) -> list[dict[str, float]]:
    return [
        {
            "diameter_mm": diameter,
            "area_mm2": round(pi * diameter**2 / 4, 2),
            "mass_kg_m": round(0.00617 * diameter**2, 3),
        }
        for diameter in diameters
    ]


REBAR_MATERIALS = [
    {
        "id": "HPB300",
        "label": "HPB300 热轧光圆钢筋",
        "family": "plain",
        "fy_mpa": 270,
        "fyv_mpa": 270,
        "elastic_modulus_mpa": 210000,
        "diameters": _areas([6, 8, 10, 12, 14, 16, 18, 20, 22]),
        "roles": ["stirrup", "distribution", "longitudinal"],
        "status": "active",
        "notes": ["梁、柱纵向受力钢筋优先采用 400MPa 或 500MPa 级带肋钢筋。"],
    },
    *[
        {
            "id": grade,
            "label": f"{grade} 热轧带肋钢筋",
            "family": "ribbed",
            "fy_mpa": fy,
            "fyv_mpa": min(fy, 360),
            "elastic_modulus_mpa": 200000,
            "diameters": _areas(
                [6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 36, 40]
            ),
            "roles": ["longitudinal", "stirrup"],
            "status": "active",
            "notes": (
                ["E 后缀表示较高抗震性能，设计强度按对应基础牌号采用。"]
                if grade.endswith("E")
                else []
            ),
        }
        for grade, fy in [
            ("HRB400", 360),
            ("HRBF400", 360),
            ("HRB400E", 360),
            ("HRBF400E", 360),
            ("HRB500", 435),
            ("HRBF500", 435),
            ("HRB500E", 435),
            ("HRBF500E", 435),
        ]
    ],
    {
        "id": "RRB400",
        "label": "RRB400 余热处理带肋钢筋",
        "family": "residual_heat_treated",
        "fy_mpa": 360,
        "fyv_mpa": 360,
        "elastic_modulus_mpa": 200000,
        "diameters": _areas([8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 36, 40]),
        "roles": ["longitudinal", "stirrup"],
        "status": "restricted",
        "notes": ["不宜用于直接承受疲劳荷载的构件。"],
    },
    {
        "id": "HRB335",
        "label": "HRB335（旧项目兼容）",
        "family": "ribbed",
        "fy_mpa": 300,
        "fyv_mpa": 300,
        "elastic_modulus_mpa": 200000,
        "diameters": _areas([6, 8, 10, 12, 14, 16]),
        "roles": ["legacy_only"],
        "status": "legacy",
        "notes": ["2024 年局部修订已删除该牌号，新项目禁止选择。"],
    },
    {
        "id": "HRB600",
        "label": "HRB600（尚未完成设计标准映射）",
        "family": "ribbed",
        "fy_mpa": None,
        "fyv_mpa": None,
        "elastic_modulus_mpa": 200000,
        "diameters": [],
        "roles": [],
        "status": "blocked",
        "notes": ["产品标准与结构设计标准不是同一准入层级，当前不参与计算。"],
    },
]


LOAD_PRESETS = [
    {
        "id": "dead-steel",
        "category": "material_self_weight",
        "label": "钢材自重",
        "value": 78.5,
        "unit": "kN/m3",
        "kind": "dead",
        "scenes": ["pergola", "canopy", "sign"],
        "source_reference": "GB 50009-2012 附录A",
        "notes": "通常由截面面积自动换算，不应重复添加。",
    },
    {
        "id": "dead-reinforced-concrete",
        "category": "material_self_weight",
        "label": "钢筋混凝土自重",
        "value": 25.0,
        "unit": "kN/m3",
        "kind": "dead",
        "scenes": ["wall", "bench", "walkway", "foundation"],
        "source_reference": "GB 50009-2012 附录A",
        "notes": "由构件体积自动换算时不应重复添加。",
    },
    {
        "id": "dead-timber",
        "category": "material_self_weight",
        "label": "常用结构木材参考自重",
        "value": 5.0,
        "value_max": 8.0,
        "unit": "kN/m3",
        "kind": "dead",
        "scenes": ["pergola", "walkway"],
        "source_reference": "GB 50009-2012 附录A（按树种核对）",
        "notes": "这是选材范围，必须按实际树种或产品资料确认。",
    },
    {
        "id": "dead-stone-finish",
        "category": "finish",
        "label": "石材面层参考值",
        "value": 0.8,
        "value_max": 1.5,
        "unit": "kN/m2",
        "kind": "dead",
        "scenes": ["wall", "bench", "walkway"],
        "source_reference": "按材料密度与构造厚度计算",
        "notes": "根据石材、砂浆和粘结层实际厚度复核。",
    },
    {
        "id": "dead-soil",
        "category": "landscape",
        "label": "种植土参考重度",
        "value": 16.0,
        "value_max": 20.0,
        "unit": "kN/m3",
        "kind": "dead",
        "scenes": ["planter", "green_roof"],
        "source_reference": "项目材料与含水状态",
        "notes": "应按饱和状态、排水构造和材料报告确认。",
    },
    {
        "id": "dead-water",
        "category": "landscape",
        "label": "水自重",
        "value": 10.0,
        "unit": "kN/m3",
        "kind": "dead",
        "scenes": ["water_feature", "planter"],
        "source_reference": "工程常用重度",
        "notes": "按最高设计水位换算。",
    },
    {
        "id": "live-maintenance-roof",
        "category": "imposed",
        "label": "不上人屋面检修荷载建议入口",
        "value": 0.5,
        "unit": "kN/m2",
        "kind": "live",
        "scenes": ["pergola", "canopy"],
        "source_reference": "GB 50009-2012 第5章（须核对具体屋面类别）",
        "notes": "不得代替集中检修荷载和项目专项要求。",
    },
    {
        "id": "live-walkway",
        "category": "imposed",
        "label": "景观步道活荷载方案建议",
        "value": 3.5,
        "unit": "kN/m2",
        "kind": "live",
        "scenes": ["walkway", "platform"],
        "source_reference": "使用场景建议，须按 GB 50009-2012 第5章归类",
        "notes": "人群密集、消防或车辆通行时不得采用。",
    },
    {
        "id": "live-assembly",
        "category": "imposed",
        "label": "人员聚集场景提示值",
        "value": 3.5,
        "value_max": 5.0,
        "unit": "kN/m2",
        "kind": "live",
        "scenes": ["pavilion", "platform", "seating"],
        "source_reference": "GB 50009-2012 第5章（按具体用途取值）",
        "notes": "只用于触发分类选择，必须由设计人员确认最终类别和值。",
    },
]


# 这些记录由 GB 50009-2012 表 E.5 逐项转录，并保留三种重现期。
# 当前仓库只内置已复核的首批站点；接口会明确返回数据集覆盖状态，
# 未列地点必须手动输入并提供项目依据，不能自动回退到相邻城市。
CLIMATE_LOCATIONS = [
    {
        "id": "beijing-beijing",
        "province": "北京",
        "city": "北京市",
        "station": "北京市",
        "elevation_m": 54.0,
        "wind_kpa": {"10": 0.30, "50": 0.45, "100": 0.50},
        "snow_kpa": {"10": 0.25, "50": 0.40, "100": 0.45},
        "snow_zone": "Ⅱ",
    },
    {
        "id": "tianjin-tianjin",
        "province": "天津",
        "city": "天津市",
        "station": "天津市",
        "elevation_m": 3.3,
        "wind_kpa": {"10": 0.30, "50": 0.50, "100": 0.60},
        "snow_kpa": {"10": 0.25, "50": 0.40, "100": 0.45},
        "snow_zone": "Ⅱ",
    },
    {
        "id": "tianjin-tanggu",
        "province": "天津",
        "city": "天津市",
        "station": "塘沽",
        "elevation_m": 3.2,
        "wind_kpa": {"10": 0.40, "50": 0.55, "100": 0.65},
        "snow_kpa": {"10": 0.20, "50": 0.35, "100": 0.40},
        "snow_zone": "Ⅱ",
    },
    {
        "id": "shanghai-shanghai",
        "province": "上海",
        "city": "上海市",
        "station": "上海市",
        "elevation_m": 2.8,
        "wind_kpa": {"10": 0.40, "50": 0.55, "100": 0.60},
        "snow_kpa": {"10": 0.10, "50": 0.20, "100": 0.25},
        "snow_zone": "Ⅲ",
    },
    {
        "id": "chongqing-chongqing",
        "province": "重庆",
        "city": "重庆市",
        "station": "重庆市",
        "elevation_m": 259.1,
        "wind_kpa": {"10": 0.25, "50": 0.40, "100": 0.45},
        "snow_kpa": {"10": None, "50": None, "100": None},
        "snow_zone": None,
    },
    {
        "id": "hebei-shijiazhuang",
        "province": "河北",
        "city": "石家庄市",
        "station": "石家庄市",
        "elevation_m": 80.5,
        "wind_kpa": {"10": 0.25, "50": 0.35, "100": 0.40},
        "snow_kpa": {"10": 0.20, "50": 0.30, "100": 0.35},
        "snow_zone": "Ⅱ",
    },
    {
        "id": "shanxi-taiyuan",
        "province": "山西",
        "city": "太原市",
        "station": "太原市",
        "elevation_m": 778.3,
        "wind_kpa": {"10": 0.30, "50": 0.40, "100": 0.45},
        "snow_kpa": {"10": 0.25, "50": 0.35, "100": 0.40},
        "snow_zone": "Ⅱ",
    },
    {
        "id": "inner-mongolia-hohhot",
        "province": "内蒙古",
        "city": "呼和浩特市",
        "station": "呼和浩特市",
        "elevation_m": 1063.0,
        "wind_kpa": {"10": 0.35, "50": 0.55, "100": 0.60},
        "snow_kpa": {"10": 0.25, "50": 0.40, "100": 0.45},
        "snow_zone": "Ⅱ",
    },
    {
        "id": "liaoning-shenyang",
        "province": "辽宁",
        "city": "沈阳市",
        "station": "沈阳市",
        "elevation_m": 42.8,
        "wind_kpa": {"10": 0.40, "50": 0.55, "100": 0.60},
        "snow_kpa": {"10": 0.30, "50": 0.50, "100": 0.55},
        "snow_zone": "Ⅰ",
    },
]


def material_catalog() -> dict:
    return {
        "version": MATERIAL_CATALOG_VERSION,
        "standard_profile": STANDARD_PROFILE,
        "source_references": [
            "GB/T 50010-2010（2024年局部修订）",
            "GB 1499.1-2024",
            "GB 1499.2-2024",
        ],
        "items": REBAR_MATERIALS,
    }


def load_catalog() -> dict:
    items = []
    for item in LOAD_PRESETS:
        default = item.get("value")
        maximum = item.get("value_max")
        is_range = maximum is not None and maximum != default
        items.append(
            {
                **item,
                "value_type": "reference_range" if is_range else "fixed",
                "recommended_min": default,
                "recommended_default": default,
                "recommended_max": maximum if maximum is not None else default,
                "adopted_value": default,
                "applicable_when": item.get(
                    "notes", "按项目场景和构造条件确认。"
                ),
                "distribution": (
                    "pressure"
                    if item["unit"] == "kPa"
                    else "area"
                    if item["unit"] == "kN/m2"
                    else "line"
                    if item["unit"] == "kN/m"
                    else "point"
                ),
                "direction": "gravity",
                "application_target": "user_selected",
                "override_reason": None,
            }
        )
    items.append(
        {
            "id": "custom-project-load",
            "category": "project_defined",
            "label": "自定义项目资料",
            "value": None,
            "unit": "kN/m2",
            "kind": "custom",
            "scenes": ["all"],
            "source_reference": "由用户填写项目资料名称、页码或条款",
            "notes": "必须填写采用值、单位、来源和适用位置。",
            "value_type": "project_defined",
            "recommended_min": None,
            "recommended_default": None,
            "recommended_max": None,
            "adopted_value": None,
            "applicable_when": "项目专项资料与通用目录不一致或目录未覆盖时。",
            "distribution": "area",
            "direction": "gravity",
            "application_target": "user_selected",
            "override_reason": None,
        }
    )
    return {
        "version": LOAD_CATALOG_VERSION,
        "standard_profile": STANDARD_PROFILE,
        "items": items,
    }


def climate_catalog(query: str = "") -> dict:
    normalized = query.strip().lower()
    items = [
        item
        for item in CLIMATE_LOCATIONS
        if not normalized
        or normalized in item["province"].lower()
        or normalized in item["city"].lower()
        or normalized in item["station"].lower()
    ]
    return {
        "version": CLIMATE_CATALOG_VERSION,
        "standard_profile": STANDARD_PROFILE,
        "source_reference": "GB 50009-2012 表 E.5",
        "coverage": "reviewed_initial_batch",
        "professional_use_requires_confirmation": True,
        "items": items,
    }
