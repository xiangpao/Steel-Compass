from __future__ import annotations

import math

import pytest

from app.core.errors import CalculationInputError
from app.core.sections import steel_section


def test_rhs_section_properties_match_closed_form() -> None:
    section = steel_section(
        {"section_type": "RHS", "h_mm": 200, "b_mm": 100, "t_mm": 6}
    )
    expected_area = 200 * 100 - 188 * 88
    expected_ix = (100 * 200**3 - 88 * 188**3) / 12
    assert section.area_mm2 == pytest.approx(expected_area)
    assert section.ix_mm4 == pytest.approx(expected_ix)
    assert section.wx_mm3 == pytest.approx(expected_ix / 100)
    assert section.self_weight_kn_m > 0


def test_chs_radius_is_consistent() -> None:
    section = steel_section(
        {"section_type": "CHS", "diameter_mm": 140, "t_mm": 5}
    )
    assert section.rx_mm == pytest.approx(
        math.sqrt(section.ix_mm4 / section.area_mm2)
    )
    assert section.ix_mm4 == pytest.approx(section.iy_mm4)


def test_invalid_hollow_section_is_rejected() -> None:
    with pytest.raises(CalculationInputError) as error:
        steel_section({"section_type": "SHS", "b_mm": 100, "t_mm": 50})
    assert error.value.code == "invalid_section_geometry"
