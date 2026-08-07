from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.bridge_rc import (
    RCBridgeGeometry,
    RCBridgeLoads,
    RCBridgeMaterial,
    RCBridgeModel,
    RCBridgeReinforcement,
    RCBridgeServiceLimits,
    RCBridgeSpanLoad,
    RCBridgeSupport,
    analyze_rc_pedestrian_bridge,
)
from app.core.errors import CalculationInputError


def bridge_model(
    span_count: int = 1,
    *,
    span_loads: tuple[RCBridgeSpanLoad, ...] | None = None,
    loads: RCBridgeLoads | None = None,
    limits: RCBridgeServiceLimits | None = None,
) -> RCBridgeModel:
    geometry = RCBridgeGeometry(
        span_count=span_count,
        span_length_m=6.0,
        deck_width_m=3.0,
        deck_elevation_m=2.0,
        slab_thickness_mm=180,
        girder_count=3,
        girder_width_mm=300,
        girder_height_mm=600,
    )
    return RCBridgeModel(
        geometry=geometry,
        material=RCBridgeMaterial(30_000, 14.3, 1.43, 360),
        reinforcement=RCBridgeReinforcement(
            cover_mm=40,
            slab_bar_diameter_mm=12,
            slab_bar_spacing_mm=150,
            girder_bottom_area_mm2=4_000,
            girder_top_area_mm2=3_000,
            girder_stirrup_area_mm2=157,
            girder_stirrup_spacing_mm=150,
        ),
        loads=loads
        or RCBridgeLoads(
            spans=span_loads
            or tuple(RCBridgeSpanLoad(1.0, 5.0) for _ in range(span_count)),
            railing_left_kn_m=1.0,
            railing_right_kn_m=1.0,
            wind_pressure_kpa=0.8,
            wind_exposed_height_m=1.2,
        ),
        supports=tuple(
            RCBridgeSupport(
                f"support-{index}",
                index,
                "shallow" if index % 2 == 0 else "pile",
            )
            for index in range(span_count + 1)
        ),
        service_limits=limits or RCBridgeServiceLimits(),
    )


def check(result, name: str):
    return next(
        item
        for item in result.slab_checks + result.girder_checks
        if item.name == name
    )


def test_single_span_reactions_match_closed_form_and_foundation_routing() -> None:
    model = bridge_model()
    result = analyze_rc_pedestrian_bridge(model)
    sls = next(item for item in result.combinations if item.id == "SLS-standard")
    reactions = [
        item for item in result.reactions if item.combination_id == "SLS-standard"
    ]
    assert len(reactions) == 2
    assert reactions[0].n_kn == pytest.approx(sls.applied_vertical_kn / 2)
    assert reactions[1].n_kn == pytest.approx(sls.applied_vertical_kn / 2)
    assert reactions[0].foundation_type == "shallow"
    assert reactions[1].foundation_type == "pile"
    assert set(reactions[0].components_6dof) == {"N", "Vx", "Vy", "Mx", "My", "T"}
    assert sum(item.n_kn for item in reactions) == pytest.approx(sls.applied_vertical_kn)
    assert sum(item.vx_kn for item in reactions) == pytest.approx(sls.applied_wind_kn)
    assert sum(item.my_kn_m for item in reactions) == pytest.approx(
        sls.applied_wind_moment_kn_m
    )
    assert result.maximum_girder_positive_moment_kn_m > 0
    assert result.maximum_girder_shear_kn > 0
    assert result.maximum_girder_deflection_mm > 0
    assert result.verification_status == "unverified"


def test_equal_multispan_asymmetric_load_produces_asymmetric_reactions_and_balance() -> None:
    model = bridge_model(
        3,
        span_loads=(
            RCBridgeSpanLoad(1.0, 5.0),
            RCBridgeSpanLoad(1.0, 2.0),
            RCBridgeSpanLoad(1.0, 0.5),
        ),
    )
    result = analyze_rc_pedestrian_bridge(model)
    assert result.maximum_girder_negative_moment_kn_m > 0
    for combination in result.combinations:
        reactions = [
            item
            for item in result.reactions
            if item.combination_id == combination.id
        ]
        assert sum(item.n_kn for item in reactions) == pytest.approx(
            combination.applied_vertical_kn, abs=1e-8
        )
        assert sum(item.vx_kn for item in reactions) == pytest.approx(
            combination.applied_wind_kn, abs=1e-8
        )
        assert sum(item.my_kn_m for item in reactions) == pytest.approx(
            combination.applied_wind_moment_kn_m, abs=1e-8
        )
    sls = [item for item in result.reactions if item.combination_id == "SLS-standard"]
    assert sls[0].n_kn != pytest.approx(sls[-1].n_kn)


def test_railing_asymmetry_is_preserved_as_combination_consistent_torsion() -> None:
    loads = RCBridgeLoads(
        spans=(RCBridgeSpanLoad(1, 4), RCBridgeSpanLoad(1, 4)),
        railing_left_kn_m=0.5,
        railing_right_kn_m=2.0,
        wind_pressure_kpa=1.0,
        wind_exposed_height_m=1.4,
    )
    result = analyze_rc_pedestrian_bridge(bridge_model(2, loads=loads))
    for combination in result.combinations:
        reactions = [
            item
            for item in result.reactions
            if item.combination_id == combination.id
        ]
        assert sum(item.torsion_kn_m for item in reactions) == pytest.approx(
            combination.applied_railing_torsion_kn_m
        )
        assert all(item.components_6dof["Vy"] == 0 for item in reactions)


def test_slab_and_girder_checks_include_required_screening_items() -> None:
    result = analyze_rc_pedestrian_bridge(bridge_model(2))
    names = {item.name for item in result.slab_checks + result.girder_checks}
    assert {
        "桥面板受弯",
        "桥面板受剪",
        "桥面板最小配筋",
        "桥面板最大配筋",
        "桥面板裂缝宽度",
        "桥面板挠度",
        "RC纵梁正弯矩",
        "RC纵梁负弯矩",
        "RC纵梁受剪",
        "RC纵梁裂缝宽度",
        "RC纵梁挠度",
        "简化竖向基本频率",
    } <= names
    assert result.estimated_vertical_frequency_hz > 0
    assert any("未完成规范独立验证" in item for item in result.exclusions)


@pytest.mark.parametrize(
    ("check_name", "factor", "expected_passed"),
    [
        ("桥面板裂缝宽度", 0.99, True),
        ("桥面板裂缝宽度", 1.01, False),
        ("简化竖向基本频率", 0.99, True),
        ("简化竖向基本频率", 1.01, False),
    ],
)
def test_serviceability_boundaries_flip_at_099_and_101(
    check_name: str, factor: float, expected_passed: bool
) -> None:
    base_model = bridge_model()
    base = analyze_rc_pedestrian_bridge(base_model)
    if check_name == "桥面板裂缝宽度":
        demand = check(base, check_name).demand
        limits = replace(base_model.service_limits, crack_width_limit_mm=demand / factor)
    else:
        frequency = base.estimated_vertical_frequency_hz
        limits = replace(
            base_model.service_limits,
            minimum_vertical_frequency_hz=frequency * factor,
        )
    result = analyze_rc_pedestrian_bridge(replace(base_model, service_limits=limits))
    boundary = check(result, check_name)
    assert boundary.utilization == pytest.approx(factor)
    assert boundary.passed is expected_passed


@pytest.mark.parametrize(
    ("model", "code"),
    [
        (
            replace(
                bridge_model(2),
                loads=RCBridgeLoads(spans=(RCBridgeSpanLoad(1, 5),)),
            ),
            "span_load_count_mismatch",
        ),
        (
            replace(bridge_model(), supports=(RCBridgeSupport("only", 0, "shallow"),)),
            "invalid_support_layout",
        ),
        (
            replace(
                bridge_model(),
                geometry=replace(bridge_model().geometry, girder_count=1),
            ),
            "invalid_girder_count",
        ),
        (
            replace(
                bridge_model(),
                reinforcement=replace(
                    bridge_model().reinforcement, slab_bar_spacing_mm=0
                ),
            ),
            "non_positive_value",
        ),
        (
            replace(
                bridge_model(),
                loads=replace(
                    bridge_model().loads,
                    spans=(RCBridgeSpanLoad(1, -1),),
                ),
            ),
            "invalid_load",
        ),
    ],
)
def test_invalid_bridge_models_raise_structured_errors(
    model: RCBridgeModel, code: str
) -> None:
    with pytest.raises(CalculationInputError) as caught:
        analyze_rc_pedestrian_bridge(model)
    assert caught.value.code == code
