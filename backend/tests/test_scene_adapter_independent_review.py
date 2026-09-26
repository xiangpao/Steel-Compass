"""Independent audit regressions: expected values follow physical load balance."""
from math import sqrt

import pytest

from app.core.engine import calculate
from app.core.scene_graph import execute_scene
from app.core.scene_typed_adapters import apply_vertical_line
from app.core.schemas import PlanarFrameInputs
from test_scene_typed_adapters import fixture, typed_for


def vertical(result, node, case, component="N"):
    calculation = result.node_results[node].calculation_result
    assert calculation is not None, result.node_results[node].message
    return sum(e.components[component].value for e in calculation.reaction_envelopes
               if e.combination_id == case)


def test_independent_local_platform_line_reaches_only_adjacent_foundations():
    family, variant, nodes, loads = fixture("boardwalk-platform", "viewing-platform")
    baseline = execute_scene(family, variant.id, "quick", nodes, load_cases=loads)
    local = loads[0].model_copy(update={
        "id": "independent-edge-line", "value_type": "project_defined",
        "source_reference": "Independent audit: 10 kN/m on 3 m south edge",
        "application_target": "edge_south", "distribution": "line",
        "unit": "kN/m", "adopted_value": 10., "recommended_default": None,
    })
    changed = execute_scene(family, variant.id, "quick", nodes, load_cases=loads + [local])
    case = "SLS-scene-1-5"
    for corner in ("south_west", "south_east", "north_west", "north_east"):
        node = f"platform_foundation_{corner}"
        increment = vertical(changed, node, case) - vertical(baseline, node, case)
        assert increment == pytest.approx(15. if corner.startswith("south") else 0., abs=1e-7)
    packets = changed.node_results["edge_south"].calculation_result.reaction_envelopes
    assert sum(e.combination_id == case for e in packets) == 2


def test_independent_roof_increment_reaches_all_front_and_rear_foundations():
    family, variant, nodes, loads = fixture("pergola-pavilion", "mono-pitch")
    baseline = execute_scene(family, variant.id, "quick", nodes, load_cases=loads)
    changed_loads = [x.model_copy(update={"adopted_value": x.adopted_value + 1.,
        "override_reason": "Independent audit: 1 kPa over 4 by 3 m roof"})
        if x.kind == "dead" else x for x in loads]
    changed = execute_scene(family, variant.id, "quick", nodes, load_cases=changed_loads)
    foundations = [key for key in changed.node_results if "foundation" in key]
    assert len(foundations) == 4
    increment = sum(vertical(changed, key, "SLS-scene-1-5") -
                    vertical(baseline, key, "SLS-scene-1-5") for key in foundations)
    assert increment == pytest.approx(4 * 3 * 1., abs=1e-7)


def test_independent_cap_volume_increment_reaches_each_pile_group():
    family, variant, nodes, loads = fixture("landscape-bridge", "single-rc-pile")
    baseline = execute_scene(family, variant.id, "quick", nodes, load_cases=loads)
    changed_nodes = [x.model_copy(update={"calculation": x.calculation.model_copy(
        update={"inputs": {**x.calculation.inputs, "cap_thickness_mm": 1000.}})})
        if x.calculation.module.value == "pile_group_cap" else x for x in nodes]
    changed = execute_scene(family, variant.id, "quick", changed_nodes, load_cases=loads)
    for key in ("support_left", "support_right"):
        assert vertical(changed, key, "SLS-standard") - vertical(baseline, key, "SLS-standard") == pytest.approx(3 * 3 * .5 * 25)


def test_independent_inclined_simple_beam_recovers_distributed_axial_force():
    requests, _, _ = typed_for("entrance-frame", "unequal-columns", "planar_frame")
    request = requests[0]
    member = request.typed_inputs.members[-1].model_dump()
    member.update(id="slope", start="A", end="B")
    q = lambda value, unit: {"value": value, "unit": unit}
    typed = PlanarFrameInputs.model_validate({
        "module": "planar_frame", "combination_id": "independent", "combination_name": "independent", "limit_state": "ULS",
        "nodes": [{"id": "A", "x": q(0, "m"), "y": q(0, "m")},
                  {"id": "B", "x": q(4, "m"), "y": q(2, "m")}],
        "members": [member],
        "restraints": [{"node": "A", "ux": True, "uy": True, "rz": False},
                       {"node": "B", "ux": False, "uy": True, "rz": False}],
        "displacement_limit": q(100, "mm"),
    })
    result = calculate(request.model_copy(update={"typed_inputs": apply_vertical_line(typed, -7.)}))
    axial = next(c.demand.value for c in result.checks if "轴力" in c.name)
    moment = next(c.demand.value for c in result.checks if "弯矩" in c.name)
    assert axial == pytest.approx(14 * 2 / sqrt(20), abs=1e-8)
    assert moment == pytest.approx(14., abs=1e-8)
    assert all(e.components["Vy"].value == pytest.approx(14., abs=1e-8) for e in result.reaction_envelopes)
