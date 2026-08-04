from __future__ import annotations

import pytest

from app.core.engine import calculate
from app.core.schemas import (
    CalculationModule,
    CalculationRequest,
    LoadDirection,
    LoadItem,
    LoadKind,
)
from verification.milestone_references import (
    solve_cantilever_post,
    solve_rc_wall_cantilever,
    solve_rc_wall_wind_and_soil,
    solve_retaining_wall_actions,
    solve_simply_supported_udl,
    solve_wall_strip,
)


def _request(module: CalculationModule, inputs: dict, loads: list[LoadItem]) -> CalculationRequest:
    return CalculationRequest(
        schema_version="3.1",
        mode="quick",
        module=module,
        project_name="milestone reference",
        confirmed_assumptions=True,
        inputs=inputs,
        loads=loads,
    )


def test_timber_deck_reactions_match_independent_udl_reference() -> None:
    result = calculate(
        _request(
            CalculationModule.TIMBER_DECK_PANEL,
            {"span_m": 1.2, "thickness_mm": 50, "strip_width_m": 1.0, "timber_grade": "TC13"},
            [
                LoadItem(kind=LoadKind.DEAD, value=0.5, unit="kN/m2", source="reference", confirmed=True),
                LoadItem(kind=LoadKind.LIVE, value=3.5, unit="kN/m2", source="reference", confirmed=True),
            ],
        )
    )
    # The production result exposes the governing ULS line load through the
    # support packet; the independent script only knows mechanics.
    envelope = next(item for item in result.reaction_envelopes if item.limit_state == "ULS")
    reaction = envelope.components["Vy"].value
    line_load = 2.0 * reaction / 1.2
    reference = solve_simply_supported_udl(
        line_load_kn_m=line_load,
        span_m=1.2,
        elastic_modulus_mpa=9000,
        inertia_mm4=1000 * 50**3 / 12,
    )
    assert reaction == pytest.approx(reference.reaction_kn, rel=1e-9)
    assert result.checks[0].demand.value == pytest.approx(
        line_load * 1.2**2 / 8,
        rel=1e-9,
    )


def test_sign_post_actions_match_independent_reference_and_keep_direction() -> None:
    result = calculate(
        _request(
            CalculationModule.STEEL_CANTILEVER_POST,
            {"height_m": 2.8, "panel_area_m2": 1.5, "panel_cg_height_m": 2.1, "panel_eccentricity_m": 0.2},
            [
                LoadItem(
                    kind=LoadKind.WIND,
                    value=0.6,
                    unit="kN/m2",
                    source="reference",
                    direction=LoadDirection.X_POSITIVE,
                    confirmed=True,
                )
            ],
        )
    )
    reference = solve_cantilever_post(force_kn=0.6 * 1.5, lever_arm_m=2.1, eccentricity_m=0.2)
    assert result.reactions["base_horizontal"].value == pytest.approx(reference.shear_kn)
    assert result.reactions["base_moment"].value == pytest.approx(reference.moment_kn_m)
    assert result.reaction_envelopes[0].direction is LoadDirection.X_POSITIVE


def test_sign_panel_dead_load_is_transferred_to_post_axial_reaction() -> None:
    result = calculate(
        _request(
            CalculationModule.STEEL_CANTILEVER_POST,
            {"height_m": 2.8, "panel_area_m2": 1.5, "panel_cg_height_m": 2.1},
            [
                LoadItem(
                    kind=LoadKind.DEAD,
                    value=0.35,
                    unit="kN/m2",
                    source="panel data",
                    confirmed=True,
                ),
            ],
        )
    )
    assert result.reactions["base_vertical"].value == pytest.approx(0.35 * 1.5)


def test_masonry_and_rc_wall_closed_forms_are_independent() -> None:
    masonry = calculate(
        _request(
            CalculationModule.MASONRY_WALL,
            {"height_m": 2.0, "column_spacing_m": 3.0, "thickness_mm": 240},
            [
                LoadItem(
                    kind=LoadKind.WIND,
                    value=0.5,
                    unit="kN/m2",
                    source="reference",
                    direction=LoadDirection.X_POSITIVE,
                    confirmed=True,
                )
            ],
        )
    )
    masonry_ref = solve_wall_strip(pressure_kpa=0.5, height_m=2.0, span_m=1.0)
    assert masonry.steps[0].result.value == pytest.approx(masonry_ref.line_load_kn_m)

    rc = calculate(
        _request(
            CalculationModule.RC_WALL,
            {"height_m": 1.2, "thickness_mm": 180, "bar_dia_mm": 12, "bar_spacing_mm": 200},
            [
                LoadItem(
                    kind=LoadKind.WIND,
                    value=0.3,
                    unit="kN/m2",
                    source="reference",
                    direction=LoadDirection.X_POSITIVE,
                    confirmed=True,
                )
            ],
        )
    )
    rc_ref = solve_rc_wall_cantilever(pressure_kpa=0.3, height_m=1.2)
    assert rc.steps[0].result.value == pytest.approx(rc_ref.moment_kn_m)


def test_retaining_actions_match_independent_rankine_and_water_reference() -> None:
    result = calculate(
        _request(
            CalculationModule.RETAINING_WALL,
            {
                "retained_height_m": 1.5,
                "base_width_m": 1.6,
                "toe_length_m": 0.45,
                "stem_thickness_mm": 200,
                "base_thickness_m": 0.35,
                "soil_unit_weight_kn_m3": 18,
                "soil_friction_angle_deg": 30,
                "surcharge_kpa": 0,
                "water_level_depth_m": 0,
                "submerged_depth_m": 0,
                "soil_capacity_kpa": 120,
                "base_friction_coefficient": 0.35,
                "stem_moment_capacity_kn_m_per_m": 80,
            },
            [LoadItem(kind=LoadKind.DEAD, value=1, unit="kN/m", source="reference", confirmed=True)],
        )
    )
    reference = solve_retaining_wall_actions(
        height_m=1.5,
        soil_unit_weight_kn_m3=18,
        friction_angle_deg=30,
    )
    assert result.reactions["base_horizontal"].value == pytest.approx(reference.horizontal_force_kn_m)
    assert result.reactions["base_moment"].value == pytest.approx(reference.overturning_moment_kn_m)


def test_planter_wall_adds_active_soil_to_wind_resultant() -> None:
    result = calculate(
        _request(
            CalculationModule.RC_WALL,
            {
                "height_m": 0.8,
                "thickness_mm": 180,
                "soil_height_m": 0.8,
                "soil_unit_weight_kn_m3": 18,
                "soil_friction_angle_deg": 30,
            },
            [LoadItem(kind=LoadKind.WIND, value=0.3, unit="kN/m2", source="reference", confirmed=True)],
        )
    )
    reference = solve_rc_wall_wind_and_soil(
        wind_pressure_kpa=0.3,
        wall_height_m=0.8,
        soil_height_m=0.8,
        soil_unit_weight_kn_m3=18,
        friction_angle_deg=30,
    )
    assert result.reactions["base_horizontal"].value == pytest.approx(reference.shear_kn)
    assert result.reactions["base_moment"].value == pytest.approx(reference.moment_kn_m)
