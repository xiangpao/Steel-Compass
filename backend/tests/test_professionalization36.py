from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.design_profiles import (
    FoundationDesignSpecification,
    SceneGeometryProfile,
    foundation_form_catalog,
    rebar_catalog,
    roof_assembly_catalog,
    soil_preset_catalog,
    steel_grade_catalog,
)


def test_professional_catalogs_expose_roof_soil_rebar_and_foundation_forms() -> None:
    assert len(steel_grade_catalog()["items"]) == 5
    assert len(rebar_catalog()["items"]) == 3
    assert any(item["id"] == "none" for item in roof_assembly_catalog()["items"])
    assert len(soil_preset_catalog()["items"]) >= 8
    assert {item["section_shape"] for item in foundation_form_catalog()["items"]} >= {
        "stepped",
        "tapered",
    }


def test_foundation_forms_require_geometry_and_support_directional_rebar() -> None:
    profile = FoundationDesignSpecification(
        node_id="F1",
        foundation_system_id="spread",
        selection_source="recommended",
        length_m=2.4,
        width_m=1.8,
        thickness_mm=500,
        embedment_m=1.2,
        concrete_grade="C30",
        rebar_grade="HRB400",
        bar_diameter_mm=14,
        bar_spacing_mm=150,
        section_shape="stepped",
        steps=[{"length_m": 1.2, "width_m": 0.9, "height_mm": 250}],
        reinforcement={
            "bottom_x_diameter_mm": 16,
            "bottom_x_spacing_mm": 150,
            "bottom_y_diameter_mm": 12,
            "bottom_y_spacing_mm": 200,
        },
    )
    assert profile.length_m != profile.width_m
    assert profile.reinforcement is not None
    assert (
        profile.reinforcement.bottom_x_diameter_mm
        != profile.reinforcement.bottom_y_diameter_mm
    )
    with pytest.raises(ValidationError):
        FoundationDesignSpecification(
            node_id="F2",
            foundation_system_id="spread",
            selection_source="recommended",
            length_m=2,
            width_m=2,
            thickness_mm=500,
            embedment_m=1,
            concrete_grade="C30",
            rebar_grade="HRB400",
            bar_diameter_mm=14,
            bar_spacing_mm=150,
            section_shape="tapered",
        )


def test_guided_geometry_rejects_unknown_nodes() -> None:
    valid = SceneGeometryProfile(
        layout_mode="custom_grid",
        nodes=[
            {"id": "B1", "x_m": 0, "y_m": 0, "z_m": 0, "support": "fixed"},
            {"id": "T1", "x_m": 0, "y_m": 0, "z_m": 3},
        ],
        members=[
            {
                "id": "C1",
                "start_node_id": "B1",
                "end_node_id": "T1",
                "role": "column",
                "group_id": "columns",
            }
        ],
    )
    assert len(valid.nodes) == 2
    with pytest.raises(ValidationError):
        SceneGeometryProfile(
            nodes=[
                {"id": "N1", "x_m": 0, "y_m": 0, "z_m": 0, "support": "fixed"}
            ],
            members=[
                {
                    "id": "M1",
                    "start_node_id": "N1",
                    "end_node_id": "missing",
                    "role": "beam",
                    "group_id": "beams",
                }
            ],
        )
