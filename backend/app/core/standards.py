"""Versioned Chinese standard profiles used by new calculation snapshots.

The profile records the basis selected by the engine. It does not imply that
every module has completed verification; module evidence remains authoritative.
"""

from __future__ import annotations

from copy import deepcopy

from . import STANDARD_PROFILE


STANDARD_PROFILES: dict[str, dict] = {
    STANDARD_PROFILE: {
        "profile": STANDARD_PROFILE,
        "effective_from": "2026-08-04",
        "mapping_status": "module_scoped",
        "standards": [
            {"code": "GB 55001-2021", "title": "工程结构通用规范"},
            {"code": "GB 55003-2021", "title": "建筑与市政地基基础通用规范"},
            {"code": "GB 55005-2021", "title": "木结构通用规范"},
            {"code": "GB 55006-2021", "title": "钢结构通用规范"},
            {"code": "GB 55008-2021", "title": "混凝土结构通用规范"},
            {"code": "GB 50009-2012", "title": "建筑结构荷载规范"},
            {"code": "GB 50017-2017", "title": "钢结构设计标准"},
            {"code": "GB 50005-2017", "title": "木结构设计标准"},
            {"code": "GB 50007-2011", "title": "建筑地基基础设计规范"},
            {"code": "GB/T 50010-2010", "title": "混凝土结构设计标准（2024年局部修订）"},
            {"code": "JGJ 94-2008", "title": "建筑桩基技术规范"},
        ],
        "official_review_sources": [
            "https://www.mohurd.gov.cn/api-gateway/jpaas-web-server/front/document/download?fileName=2021%E5%B9%B4.pdf",
            "https://www.mohurd.gov.cn/file/2024/20240822/a015dc08-eaf2-474a-81c1-c4454e3b220c.pdf",
        ],
        "note": "模块是否可生成专业结论仍由独立验证证据决定。",
    }
}


def standard_profile(profile: str = STANDARD_PROFILE) -> dict:
    """Return an isolated copy so API callers cannot mutate the registry."""

    try:
        return deepcopy(STANDARD_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"unknown standard profile: {profile}") from exc
