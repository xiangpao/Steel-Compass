from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt
from typing import Any

from .errors import CalculationInputError
from .validation import number, text


@dataclass(frozen=True)
class SectionProperties:
    description: str
    section_type: str
    area_mm2: float
    ix_mm4: float
    iy_mm4: float
    wx_mm3: float
    wy_mm3: float
    rx_mm: float
    ry_mm: float
    shear_area_mm2: float
    depth_mm: float
    width_mm: float
    local_slenderness: float

    @property
    def self_weight_kn_m(self) -> float:
        return self.area_mm2 * 1e-6 * 78.5


def _ensure_hollow_dimension(outer: float, thickness: float, field: str) -> None:
    if 2 * thickness >= outer:
        raise CalculationInputError(
            "invalid_section_geometry",
            f"{field} 必须大于两倍壁厚",
            field=field,
        )


def steel_section(inputs: dict[str, Any]) -> SectionProperties:
    section_type = text(
        inputs,
        "section_type",
        allowed={"SHS", "RHS", "CHS", "H", "CUSTOM"},
        default="RHS",
    )

    if section_type == "SHS":
        b = number(inputs, "b_mm", minimum=20)
        t = number(inputs, "t_mm", minimum=1)
        _ensure_hollow_dimension(b, t, "b_mm")
        area = b**2 - (b - 2 * t) ** 2
        inertia = (b**4 - (b - 2 * t) ** 4) / 12
        radius = sqrt(inertia / area)
        return SectionProperties(
            f"SHS {b:g}×{b:g}×{t:g}",
            section_type,
            area,
            inertia,
            inertia,
            inertia / (b / 2),
            inertia / (b / 2),
            radius,
            radius,
            2 * t * (b - 2 * t),
            b,
            b,
            (b - 2 * t) / t,
        )

    if section_type == "RHS":
        h = number(inputs, "h_mm", minimum=20)
        b = number(inputs, "b_mm", minimum=20)
        t = number(inputs, "t_mm", minimum=1)
        _ensure_hollow_dimension(min(h, b), t, "h_mm/b_mm")
        area = b * h - (b - 2 * t) * (h - 2 * t)
        ix = (b * h**3 - (b - 2 * t) * (h - 2 * t) ** 3) / 12
        iy = (h * b**3 - (h - 2 * t) * (b - 2 * t) ** 3) / 12
        return SectionProperties(
            f"RHS {h:g}×{b:g}×{t:g}",
            section_type,
            area,
            ix,
            iy,
            ix / (h / 2),
            iy / (b / 2),
            sqrt(ix / area),
            sqrt(iy / area),
            2 * t * (h - 2 * t),
            h,
            b,
            max((h - 2 * t) / t, (b - 2 * t) / t),
        )

    if section_type == "CHS":
        diameter = number(inputs, "diameter_mm", minimum=20)
        t = number(inputs, "t_mm", minimum=1)
        _ensure_hollow_dimension(diameter, t, "diameter_mm")
        inner = diameter - 2 * t
        area = pi * (diameter**2 - inner**2) / 4
        inertia = pi * (diameter**4 - inner**4) / 64
        radius = sqrt(inertia / area)
        return SectionProperties(
            f"CHS Φ{diameter:g}×{t:g}",
            section_type,
            area,
            inertia,
            inertia,
            inertia / (diameter / 2),
            inertia / (diameter / 2),
            radius,
            radius,
            area / 2,
            diameter,
            diameter,
            (diameter - 2 * t) / t,
        )

    if section_type == "H":
        h = number(inputs, "h_mm", minimum=50)
        b = number(inputs, "b_mm", minimum=40)
        tw = number(inputs, "tw_mm", minimum=2)
        tf = number(inputs, "tf_mm", minimum=2)
        if 2 * tf >= h or tw >= b:
            raise CalculationInputError(
                "invalid_section_geometry", "H 型钢尺寸不合理"
            )
        area = 2 * b * tf + (h - 2 * tf) * tw
        ix = (b * h**3 - (b - tw) * (h - 2 * tf) ** 3) / 12
        iy = (2 * tf * b**3 + (h - 2 * tf) * tw**3) / 12
        return SectionProperties(
            f"H {h:g}×{b:g}×{tw:g}×{tf:g}",
            section_type,
            area,
            ix,
            iy,
            ix / (h / 2),
            iy / (b / 2),
            sqrt(ix / area),
            sqrt(iy / area),
            (h - 2 * tf) * tw,
            h,
            b,
            max((h - 2 * tf) / tw, (b - tw) / (2 * tf)),
        )

    area = number(inputs, "area_mm2", minimum=1)
    ix = number(inputs, "ix_mm4", minimum=1)
    iy = number(inputs, "iy_mm4", minimum=1)
    wx = number(inputs, "wx_mm3", minimum=1)
    wy = number(inputs, "wy_mm3", minimum=1)
    depth = number(inputs, "depth_mm", minimum=1)
    width = number(inputs, "width_mm", minimum=1)
    return SectionProperties(
        text(inputs, "section_name", default="自定义截面"),
        section_type,
        area,
        ix,
        iy,
        wx,
        wy,
        sqrt(ix / area),
        sqrt(iy / area),
        number(inputs, "shear_area_mm2", minimum=1, default=0.5 * area),
        depth,
        width,
        number(inputs, "local_slenderness", minimum=0, default=0),
    )
