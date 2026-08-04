from __future__ import annotations

from typing import Any

from .schemas import CalculationMode, CalculationRequest
from .validation import boolean, number, text


STANDARDS = {
    "steel": [
        "GB 55001-2021 工程结构通用规范",
        "GB 55006-2021 钢结构通用规范",
        "GB 50009-2012 建筑结构荷载规范",
        "GB 50017-2017 钢结构设计标准",
    ],
    "concrete": [
        "GB 55001-2021 工程结构通用规范",
        "GB 55008-2021 混凝土结构通用规范",
        "GB 50009-2012 建筑结构荷载规范",
        "GB/T 50010-2010（2024年局部修订）混凝土结构设计标准",
    ],
    "foundation": [
        "GB 55001-2021 工程结构通用规范",
        "GB 55003-2021 建筑与市政地基基础通用规范",
        "GB 50007-2011 建筑地基基础设计规范",
        "GB 50009-2012 建筑结构荷载规范",
        "GB/T 50010-2010（2024年局部修订）混凝土结构设计标准",
    ],
    "timber": [
        "GB 55001-2021 工程结构通用规范",
        "GB 55005-2021 木结构通用规范",
        "GB 50009-2012 建筑结构荷载规范",
        "GB 50005-2017 木结构设计标准",
    ],
}

DISCLAIMER = (
    "本结果仅在所列输入、假定和适用范围内有效。专业模式当前为 Beta，"
    "需由具备相应资格的专业人员复核；本报告不是已签章建设工程设计文件。"
)


def mode_number(
    request: CalculationRequest,
    name: str,
    *,
    quick_default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    return number(
        request.inputs,
        name,
        default=quick_default if request.mode is CalculationMode.QUICK else None,
        minimum=minimum,
        maximum=maximum,
    )


def mode_text(
    request: CalculationRequest,
    name: str,
    *,
    quick_default: str | None = None,
    allowed: set[str] | None = None,
) -> str:
    return text(
        request.inputs,
        name,
        default=quick_default if request.mode is CalculationMode.QUICK else None,
        allowed=allowed,
    )


def mode_bool(
    request: CalculationRequest,
    name: str,
    *,
    quick_default: bool | None = None,
) -> bool:
    return boolean(
        request.inputs,
        name,
        default=quick_default if request.mode is CalculationMode.QUICK else None,
    )


def result_status(utilizations: list[float]) -> str:
    return "passed" if utilizations and max(utilizations) <= 1.0 else "failed"


def result_class(request: CalculationRequest) -> str:
    return (
        "quick_estimate"
        if request.mode is CalculationMode.QUICK
        else "professional_check"
    )


def quantity_summary(values: dict[str, tuple[float, str] | str | bool]) -> dict[str, Any]:
    from .schemas import Quantity

    return {
        key: Quantity(value=value[0], unit=value[1])
        if isinstance(value, tuple)
        else value
        for key, value in values.items()
    }
