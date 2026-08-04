from __future__ import annotations

import numpy as np
import pytest

from app.core.engine import calculate
from app.core.frame import Element, _element_response, solve_portal
from app.core.schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    LoadDirection,
    LoadItem,
    LoadKind,
)
from app.core.sections import steel_section


def test_portal_reactions_balance_vertical_load() -> None:
    span = 5000.0
    height = 3000.0
    section = steel_section(
        {"section_type": "RHS", "h_mm": 200, "b_mm": 100, "t_mm": 6}
    )
    coordinates = [(0, 0), (span, 0), (0, height), (span, height)]
    q = -2.0  # N/mm == kN/m
    elements = [
        Element("left", 0, 2, section.area_mm2, section.ix_mm4, section),
        Element(
            "beam",
            2,
            3,
            section.area_mm2,
            section.ix_mm4,
            section,
            distributed_q_n_mm=q,
        ),
        Element("right", 1, 3, section.area_mm2, section.ix_mm4, section),
    ]
    result = solve_portal(
        coordinates, elements, support="fixed", horizontal_force_kn=0
    )
    vertical_reaction = result.reactions[1] + result.reactions[4]
    assert vertical_reaction == pytest.approx(-q * span, rel=1e-8)
    assert result.reactions[0] + result.reactions[3] == pytest.approx(0, abs=1e-8)
    assert np.isfinite(result.displacements).all()


def test_symmetric_portal_has_equal_vertical_reactions() -> None:
    section = steel_section(
        {"section_type": "SHS", "b_mm": 180, "t_mm": 8}
    )
    coordinates = [(0, 0), (5000, 0), (0, 3000), (5000, 3000)]
    elements = [
        Element("left", 0, 2, section.area_mm2, section.ix_mm4, section),
        Element(
            "beam",
            2,
            3,
            section.area_mm2,
            section.ix_mm4,
            section,
            distributed_q_n_mm=-3,
        ),
        Element("right", 1, 3, section.area_mm2, section.ix_mm4, section),
    ]
    result = solve_portal(
        coordinates, elements, support="pinned", horizontal_force_kn=0
    )
    assert result.reactions[1] == pytest.approx(result.reactions[4], rel=1e-8)


def test_member_response_captures_between_node_moment_and_deflection() -> None:
    section = steel_section(
        {"section_type": "SHS", "b_mm": 180, "t_mm": 8}
    )
    coordinates = [(0, 0), (5000, 0), (0, 3000), (5000, 3000)]
    elements = [
        Element("left", 0, 2, section.area_mm2, section.ix_mm4, section),
        Element(
            "beam",
            2,
            3,
            section.area_mm2,
            section.ix_mm4,
            section,
            distributed_q_n_mm=-3,
        ),
        Element("right", 1, 3, section.area_mm2, section.ix_mm4, section),
    ]
    solution = solve_portal(
        coordinates, elements, support="pinned", horizontal_force_kn=0
    )
    beam = solution.elements[1]
    x, moments, _, deflection = _element_response(beam)
    assert len(x) == 101
    assert np.max(np.abs(moments)) > max(abs(moments[0]), abs(moments[-1]))
    assert np.max(np.abs(deflection)) > max(
        abs(beam.local_displacements[1]), abs(beam.local_displacements[4])
    )


def test_opposite_wind_directions_produce_opposite_frame_reactions() -> None:
    request = CalculationRequest(
        mode=CalculationMode.QUICK,
        module=CalculationModule.PORTAL_FRAME,
        project_name="wind-directions",
        confirmed_assumptions=True,
        inputs={
            "steel_grade": "Q355B",
            "span_m": 5,
            "height_m": 3,
            "base_support": "fixed",
            "wind_area_m2": 15,
            "tributary_width_m": 1,
            "beam_section": {
                "section_type": "RHS",
                "h_mm": 300,
                "b_mm": 150,
                "t_mm": 6,
            },
            "column_section": {
                "section_type": "SHS",
                "b_mm": 180,
                "t_mm": 8,
            },
        },
        loads=[
            LoadItem(kind=LoadKind.DEAD, value=1, unit="kN/m", source="dead"),
            LoadItem(
                kind=LoadKind.WIND,
                value=0.5,
                unit="kN/m2",
                source="wind +",
                direction=LoadDirection.X_POSITIVE,
            ),
            LoadItem(
                kind=LoadKind.WIND,
                value=0.5,
                unit="kN/m2",
                source="wind -",
                direction=LoadDirection.X_NEGATIVE,
            ),
        ],
    )
    result = calculate(request)
    wind_uls = [
        item
        for item in result.reaction_envelopes
        if item.limit_state == "ULS"
        and item.combination_name.startswith("ULS-活荷载控制")
    ]
    positive = sum(
        item.components["Vx"].value
        for item in wind_uls
        if item.direction is LoadDirection.X_POSITIVE
    )
    negative = sum(
        item.components["Vx"].value
        for item in wind_uls
        if item.direction is LoadDirection.X_NEGATIVE
    )
    assert positive == pytest.approx(-negative, rel=1e-9)
    assert any(diagram.name == "横梁竖向位移（SLS）" for diagram in result.diagrams)
