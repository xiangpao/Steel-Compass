"""Machine-readable sources for the Geometry 2.3 pergola closed loop.

The registry records implementation coverage, not independent verification.
Entries deliberately remain ``unverified`` until the referenced clause,
benchmark and external review evidence are all attached.
"""

from __future__ import annotations

from copy import deepcopy


PERGOLA_STANDARD_SOURCE_VERSION = "CN-2026.7-source-map-1"

STANDARD_FORMULA_SOURCES = [
    {
        "topic": "load_combination",
        "standard": "GB 50009-2012",
        "clause_or_drawing": "3.2.3-3.2.5",
        "scope": "持久设计状况作用组合",
        "symbols": ["gamma_G", "gamma_Q", "psi_c"],
        "units": "dimensionless",
        "implementation": "app/core/load_environment.py::generate_action_combinations",
        "verification_status": "unverified",
    },
    {
        "topic": "wind_and_snow",
        "standard": "GB 50009-2012",
        "clause_or_drawing": "第7章、第8章及附录E",
        "scope": "基本风压、体型/高度系数与屋面雪荷载",
        "symbols": ["w0", "mu_z", "mu_s", "s0", "mu_r"],
        "units": "kPa",
        "implementation": "app/core/pergola_loads.py::build_pergola_load_package",
        "verification_status": "unverified",
    },
    {
        "topic": "seismic_action",
        "standard": "GB 55002-2021; GB/T 50011-2010（2024年版）",
        "clause_or_drawing": "GB/T 50011 第5.1节",
        "scope": "低矮亭廊方案级等效水平地震作用及地震组合",
        "symbols": ["alpha_1", "G_eq", "F_Ek"],
        "units": "kN",
        "implementation": "app/core/seismic.py; app/core/pergola_loads.py",
        "verification_status": "unverified",
    },
    {
        "topic": "steel_member",
        "standard": "GB 55006-2021; GB 50017-2017",
        "clause_or_drawing": "GB 50017 第6章、第7章、第8章",
        "scope": "强度、稳定、长细比、宽厚比、侧扭屈曲和变形",
        "symbols": ["N", "M_y", "M_z", "V", "phi", "lambda", "M_cr"],
        "units": "kN, kN*m, mm, MPa",
        "implementation": "app/core/scene_member_checks.py::calculate_scene_member_checks",
        "verification_status": "unverified",
    },
    {
        "topic": "steel_connection_and_column_base",
        "standard": "GB 55006-2021; GB 50017-2017",
        "clause_or_drawing": "GB 50017 第11章、第12章",
        "scope": "焊缝、螺栓、端板、节点板、底板及锚栓传力",
        "symbols": ["N", "V", "M", "f_w", "f_b"],
        "units": "kN, kN*m, MPa",
        "implementation": "app/core/scene_steel_connection.py; app/core/scene_column_base.py",
        "verification_status": "unverified",
    },
    {
        "topic": "spread_foundation",
        "standard": "GB 55003-2021; GB 50007-2011",
        "clause_or_drawing": "GB 50007 第5.2节、第8.2节",
        "scope": "承载力、偏心、滑移、倾覆、抗拔及独立基础构件验算",
        "symbols": ["fak", "p_k", "e", "V", "M"],
        "units": "kPa, kN, kN*m, mm",
        "implementation": "app/core/foundation.py; app/core/scene_foundation.py",
        "verification_status": "unverified",
    },
    {
        "topic": "pedestal_and_reinforcement",
        "standard": "GB 55008-2021; GB/T 50010-2010（2024年版）; 22G101-3",
        "clause_or_drawing": "GB/T 50010 第6章、第8章；22G101-3 独立基础及短柱构造",
        "scope": "短柱偏压、受剪、纵筋、箍筋、锚固及基础配筋表达",
        "symbols": ["N", "M_x", "M_y", "A_s", "l_a"],
        "units": "kN, kN*m, mm2, mm",
        "implementation": "app/core/scene_pedestal.py; app/core/foundation.py",
        "verification_status": "unverified",
    },
]


COMMERCIAL_WORKFLOW_MATRIX = [
    {"stage": "建模", "steel_compass": "Geometry 2.3 节点/杆件/支承/屋面分区", "yjk": "YJK-MODEL", "pkpm": "结构建模", "status": "implemented_unverified"},
    {"stage": "荷载", "steel_compass": "项目条件自动工况与组合", "yjk": "荷载输入与自动导算", "pkpm": "SATWE荷载与组合", "status": "implemented_unverified"},
    {"stage": "分析", "steel_compass": "空间杆系、P-Delta、弹性屈曲、PyNite并行", "yjk": "上部结构分析", "pkpm": "SATWE", "status": "implemented_unverified"},
    {"stage": "连接", "steel_compass": "连接类型/实例及适用族阻断", "yjk": "YJK-STS节点设计", "pkpm": "钢结构节点模块", "status": "partial_unverified"},
    {"stage": "基础", "steel_compass": "柱脚-短柱-独立基础-地基", "yjk": "YJK-F", "pkpm": "JCCAD", "status": "partial_unverified"},
    {"stage": "报告", "steel_compass": "不可变快照生成计算书", "yjk": "计算书及施工图模块", "pkpm": "计算书", "status": "implemented_unverified"},
]


OFFICIAL_RESEARCH_SOURCES = [
    "https://www.yjk.cn/yonghushouce/",
    "https://help.pkpm.cn/admin/ms/detail?SiteID=123&flagReader=1&id=1308&type=sourceBook",
    "https://www.ndls.org.cn/standard/detail/9ad7d9471a1b794311c75b26059b85d8",
]


def pergola_verification_source_catalog() -> dict:
    return deepcopy({
        "version": PERGOLA_STANDARD_SOURCE_VERSION,
        "formula_sources": STANDARD_FORMULA_SOURCES,
        "commercial_workflow_matrix": COMMERCIAL_WORKFLOW_MATRIX,
        "official_research_sources": OFFICIAL_RESEARCH_SOURCES,
        "release_gate": "all formula and benchmark evidence must be independently verified before project_check",
    })
