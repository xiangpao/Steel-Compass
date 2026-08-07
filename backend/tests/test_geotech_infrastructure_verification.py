from __future__ import annotations

import inspect

import pytest

from app.core.gravity_retaining import GravityRetainingInput, calculate_gravity_retaining_wall
from app.core.pile_group import (
    InvestigatedPileCapacities,
    PileCapGeometry,
    PileCapMaterial,
    PileDefinition,
    PileGroupActions,
    PileGroupModel,
    analyze_rigid_pile_group,
)
from app.core.pool_structure import (
    PoolMaterials,
    PoolReinforcement,
    PoolWaterLevels,
    RectangularPoolGeometry,
    RectangularPoolInput,
    calculate_rectangular_pool,
)
from verification import geotech_infrastructure_references as independent
from verification.geotech_infrastructure_evidence import (
    GEOTECH_INFRASTRUCTURE_EVIDENCE,
    can_promote,
)


def test_reference_implementation_has_no_production_dependency() -> None:
    source = inspect.getsource(independent)
    assert "app.core" not in source
    assert "from app" not in source
    assert "import app" not in source


def test_gravity_wall_matches_independent_reference() -> None:
    data = GravityRetainingInput(
        combination_id="GI-GRW-001",
        combination_name="independent evidence",
        limit_state="ULS",
        retained_height_m=2.0,
        base_width_m=2.4,
        base_slab_thickness_m=0.3,
        wall_bottom_thickness_m=1.2,
        wall_top_thickness_m=0.5,
        toe_projection_m=0.7,
        wall_unit_weight_kn_m3=24.0,
        soil_unit_weight_kn_m3=18.0,
        soil_friction_angle_deg=30.0,
        surcharge_kpa=5.0,
        base_friction_coefficient=0.6,
        soil_bearing_capacity_kpa=300.0,
        material_compressive_design_kpa=1000.0,
        water_depth_behind_m=0.8,
        water_unit_weight_kn_m3=10.0,
        uplift_head_toe_m=0.0,
        uplift_head_heel_m=0.5,
    )
    actual = calculate_gravity_retaining_wall(data)
    expected = independent.gravity_wall_reference(
        height_m=2.0,
        base_width_m=2.4,
        base_thickness_m=0.3,
        wall_bottom_m=1.2,
        wall_top_m=0.5,
        toe_m=0.7,
        wall_gamma=24.0,
        soil_gamma=18.0,
        phi_deg=30.0,
        surcharge_kpa=5.0,
        water_depth_m=0.8,
        water_gamma=10.0,
        uplift_toe_m=0.0,
        uplift_heel_m=0.5,
    )
    pairs = {
        "ka": actual.active_coefficient,
        "soil": actual.soil_resultant_kn_per_m,
        "surcharge": actual.surcharge_resultant_kn_per_m,
        "water": actual.water_resultant_kn_per_m,
        "horizontal": actual.total_horizontal_kn_per_m,
        "lateral_moment": actual.lateral_moment_kn_m_per_m,
        "wall_weight": actual.wall_weight_kn_per_m,
        "base_weight": actual.base_weight_kn_per_m,
        "uplift": actual.uplift_kn_per_m,
        "vertical": actual.effective_vertical_kn_per_m,
        "resultant": actual.resultant_location_from_toe_m,
        "eccentricity": actual.eccentricity_m,
        "contact": actual.contact_length_m,
        "q_max": actual.q_max_kpa,
        "q_min": actual.q_min_kpa,
        "material_stress": actual.material_max_compression_kpa,
    }
    for key, value in pairs.items():
        assert value == pytest.approx(expected[key], rel=1e-10, abs=1e-10)
    assert actual.verification_status == "unverified"


def test_pool_matches_independent_action_and_rc_strip_reference() -> None:
    pool = RectangularPoolInput(
        geometry=RectangularPoolGeometry(6.0, 4.0, 2.5, 300.0, 400.0, 0.2, 1.5),
        materials=PoolMaterials(surcharge_kpa=5.0),
        reinforcement=PoolReinforcement(
            wall_vertical_as_mm2_per_m=1600.0,
            wall_horizontal_as_mm2_per_m=2400.0,
            base_x_as_mm2_per_m=1800.0,
            base_y_as_mm2_per_m=1800.0,
        ),
        water_levels=PoolWaterLevels(2.0, 1.0, 0.5),
        additional_ballast_kn=100.0,
    )
    result = calculate_rectangular_pool(pool)
    actual = next(item for item in result.combinations if item.combination_id == "full-uls-gravity")
    expected = independent.pool_combination_reference(
        inside_length_m=6.0,
        inside_width_m=4.0,
        wall_height_m=2.5,
        wall_thickness_mm=300.0,
        base_thickness_mm=400.0,
        base_projection_m=0.2,
        retained_soil_height_m=1.5,
        internal_depth_m=2.0,
        external_head_m=0.5,
        concrete_gamma=25.0,
        water_gamma=10.0,
        soil_gamma=18.0,
        phi_deg=30.0,
        surcharge_kpa=5.0,
        ballast_kn=100.0,
        external_lateral_factor=1.0,
        internal_water_factor=1.35,
        permanent_factor=1.35,
        uplift_factor=1.0,
    )
    pairs = {
        "ka": actual.pressures.active_coefficient,
        "net_force": actual.pressures.net_resultant_kn_per_m,
        "net_moment": actual.pressures.net_base_moment_kn_m_per_m,
        "net_base_pressure": actual.pressures.net_base_pressure_kpa,
        "downward": actual.base.downward_kn,
        "uplift": actual.base.uplift_kn,
        "net_vertical": actual.base.net_vertical_kn,
        "soil_reaction": actual.base.soil_reaction_kpa,
        "net_pressure": actual.base.net_distributed_pressure_kpa,
        "x_moment": actual.base.x_moment_kn_m_per_m,
        "y_moment": actual.base.y_moment_kn_m_per_m,
        "x_shear": actual.base.x_shear_kn_per_m,
        "y_shear": actual.base.y_shear_kn_per_m,
    }
    for key, value in pairs.items():
        assert value == pytest.approx(expected[key], rel=1e-10, abs=1e-10)

    wall_capacity = independent.rc_strip_reference(
        thickness_mm=300.0,
        cover_mm=35.0,
        bar_diameter_mm=14.0,
        steel_area_mm2=1600.0,
        concrete_fc_mpa=14.3,
        concrete_ft_mpa=1.43,
        rebar_fy_mpa=360.0,
    )
    assert result.checks[0].capacity == pytest.approx(wall_capacity["moment_capacity"])
    assert result.checks[1].capacity == pytest.approx(wall_capacity["shear_capacity"])
    assert result.verification_status == "unverified"


def test_pile_group_matches_independent_rigid_cap_reference() -> None:
    coordinates = ((-800.0, -800.0), (800.0, -800.0), (800.0, 800.0), (-800.0, 800.0))
    piles = tuple(
        PileDefinition(f"p{i + 1}", x, y, 400.0, "bored")
        for i, (x, y) in enumerate(coordinates)
    )
    actions = PileGroupActions(800.0, 40.0, 20.0, 80.0, 40.0, 30.0)
    model = PileGroupModel(
        piles=piles,
        capacities=InvestigatedPileCapacities(500.0, 200.0, 100.0, "GI-PILE-001 investigation input"),
        cap=PileCapGeometry(3000.0, 3000.0, 500.0, 500.0, 500.0, 70.0, 20.0),
        material=PileCapMaterial(1.43, 360.0, 2500.0, 2500.0),
        actions=actions,
    )
    actual = analyze_rigid_pile_group(model)
    expected = independent.pile_group_reference(
        coordinates_mm=coordinates,
        n_kn=800.0,
        vx_kn=40.0,
        vy_kn=20.0,
        mx_kn_m=80.0,
        my_kn_m=40.0,
        torsion_kn_m=30.0,
        cap_length_x_mm=3000.0,
        cap_width_y_mm=3000.0,
        cap_thickness_mm=500.0,
        column_x_mm=500.0,
        column_y_mm=500.0,
        cover_mm=70.0,
        bar_diameter_mm=20.0,
        concrete_ft_mpa=1.43,
        rebar_fy_mpa=360.0,
        rebar_x_mm2_per_m=2500.0,
        rebar_y_mm2_per_m=2500.0,
        minimum_ratio=0.0015,
    )
    for index, pile in enumerate(piles):
        reaction = actual.pile_reactions[pile.id]
        signed_axial = reaction.compression_kn - reaction.uplift_kn
        assert signed_axial == pytest.approx(expected["axial"][index])
        assert reaction.horizontal_x_kn == pytest.approx(expected["horizontal_x"][index])
        assert reaction.horizontal_y_kn == pytest.approx(expected["horizontal_y"][index])
        assert reaction.horizontal_resultant_kn == pytest.approx(expected["horizontal"][index])

    cap = actual.cap_checks
    assert cap[0].demand == pytest.approx(expected["punching_demand"])
    assert cap[0].capacity == pytest.approx(expected["punching_capacity"])
    assert cap[1].demand == pytest.approx(expected["shear_x_demand"])
    assert cap[1].capacity == pytest.approx(expected["shear_x_capacity"])
    assert cap[2].demand == pytest.approx(expected["shear_y_demand"])
    assert cap[2].capacity == pytest.approx(expected["shear_y_capacity"])
    assert cap[3].demand == pytest.approx(expected["moment_x_demand"])
    assert cap[3].capacity == pytest.approx(expected["moment_x_capacity"])
    assert cap[4].demand == pytest.approx(expected["moment_y_demand"])
    assert cap[4].capacity == pytest.approx(expected["moment_y_capacity"])
    assert actual.balance.maximum_absolute_residual == pytest.approx(0.0, abs=1e-9)
    assert actual.verification_status == "unverified"


@pytest.mark.parametrize("utilization, expected", [(0.99, True), (1.01, False)])
def test_independent_threshold_evidence_flips_at_099_and_101(utilization: float, expected: bool) -> None:
    assert independent.threshold_passes(utilization * 100.0, 100.0) is expected


def test_evidence_inventory_blocks_premature_status_promotion() -> None:
    assert set(GEOTECH_INFRASTRUCTURE_EVIDENCE) == {
        "gravity_retaining",
        "pool_structure",
        "pile_group",
    }
    for record in GEOTECH_INFRASTRUCTURE_EVIDENCE.values():
        assert record.applicability
        assert record.boundaries
        assert record.evidence_date == "2026-08-04"
        assert record.independent_case.startswith("GI-")
        assert "0.99" in record.threshold_evidence and "1.01" in record.threshold_evidence
        assert record.remaining_gaps
        assert record.reviewer is None
        assert record.human_review_date is None
        assert record.verification_status == "unverified"
        assert all(mapping.status == "candidate_pending_clause_review" for mapping in record.mappings)
        assert not can_promote(record)
