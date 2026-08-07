from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.auth import require_ready_user
from app.core.errors import CalculationInputError
from app.core.schemas import CalculationModule, CalculationRequest
from app.routers.calculation_routes import router


def q(value: float, unit: str) -> dict[str, float | str]:
    return {"value": value, "unit": unit}


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v2")
    app.dependency_overrides[require_ready_user] = lambda: object()

    @app.exception_handler(CalculationInputError)
    async def handle_error(_: Request, exc: CalculationInputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})

    with TestClient(app) as api:
        yield api


def request(module: str, typed_inputs: dict, *, mode: str = "quick") -> dict:
    return {
        "schema_version": "3.2",
        "mode": mode,
        "module": module,
        "project_name": f"infrastructure-{module}",
        "standard_profile": "CN-2026.1",
        "typed_inputs": typed_inputs,
        "loads": [],
    }


def pool_inputs() -> dict:
    return {
        "module": "pool_structure",
        "geometry": {
            "inside_length": q(6, "m"),
            "inside_width": q(4, "m"),
            "wall_height": q(2.5, "m"),
            "wall_thickness": q(300, "mm"),
            "base_thickness": q(400, "mm"),
            "base_projection": q(0.2, "m"),
            "retained_soil_height": q(2.0, "m"),
            "wall_horizontal_span": q(4, "m"),
        },
        "materials": {
            "concrete_unit_weight": q(25, "kN/m3"),
            "water_unit_weight": q(10, "kN/m3"),
            "soil_unit_weight": q(18, "kN/m3"),
            "soil_friction_angle": q(30, "deg"),
            "surcharge": q(5, "kPa"),
            "allowable_bearing": q(120, "kPa"),
            "concrete_fc": q(14.3, "MPa"),
            "concrete_ft": q(1.43, "MPa"),
            "rebar_fy": q(360, "MPa"),
            "rebar_es": q(200000, "MPa"),
        },
        "reinforcement": {
            "wall_vertical_as": q(1600, "mm2/m"),
            "wall_horizontal_as": q(2400, "mm2/m"),
            "base_x_as": q(1800, "mm2/m"),
            "base_y_as": q(1800, "mm2/m"),
            "wall_bar_diameter": q(14, "mm"),
            "base_bar_diameter": q(16, "mm"),
            "wall_cover": q(35, "mm"),
            "base_cover": q(40, "mm"),
            "minimum_reinforcement_ratio": q(0.002, "1"),
            "crack_width_limit": q(0.2, "mm"),
        },
        "water_levels": {
            "full_internal_depth": q(2, "m"),
            "empty_external_head": q(1, "m"),
            "full_external_head": q(0.5, "m"),
        },
        "additional_ballast": q(0, "kN"),
        "antifloat_factor": q(1.05, "1"),
    }


def pile_inputs() -> dict:
    piles = [
        ("p1", -800, -800, "bored"),
        ("p2", 800, -800, "precast_pipe"),
        ("p3", 800, 800, "precast_square"),
        ("p4", -800, 800, "bored"),
    ]
    return {
        "module": "pile_group_cap",
        "combination_id": "ULS-1",
        "combination_name": "ULS column reaction",
        "limit_state": "ULS",
        "piles": [
            {
                "id": name,
                "x": q(x, "mm"),
                "y": q(y, "mm"),
                "diameter_or_side": q(400, "mm"),
                "pile_type": pile_type,
            }
            for name, x, y, pile_type in piles
        ],
        "capacities": {
            "compression": q(500, "kN"),
            "uplift": q(200, "kN"),
            "horizontal": q(100, "kN"),
            "source": "investigation report table 8",
        },
        "cap": {
            "length_x": q(3000, "mm"),
            "width_y": q(3000, "mm"),
            "thickness": q(500, "mm"),
            "column_x": q(500, "mm"),
            "column_y": q(500, "mm"),
            "cover": q(70, "mm"),
            "bar_diameter": q(20, "mm"),
        },
        "material": {
            "concrete_ft": q(1.43, "MPa"),
            "rebar_fy": q(360, "MPa"),
            "provided_rebar_x": q(2500, "mm2/m"),
            "provided_rebar_y": q(2500, "mm2/m"),
            "minimum_reinforcement_ratio": q(0.0015, "1"),
        },
        "effects": {
            "axial": q(800, "kN"),
            "shear_x": q(40, "kN"),
            "shear_y": q(20, "kN"),
            "moment_x": q(80, "kN*m"),
            "moment_y": q(40, "kN*m"),
            "torsion": q(30, "kN*m"),
        },
    }


def section() -> dict:
    return {
        "area": q(9000, "mm2"),
        "inertia": q(600000000, "mm4"),
        "section_modulus": q(1200000, "mm3"),
        "shear_area": q(5000, "mm2"),
        "yield_strength": q(305, "MPa"),
        "elastic_modulus": q(206000, "MPa"),
        "unit_weight": q(78.5, "kN/m3"),
    }


def steel_bridge_inputs() -> dict:
    return {
        "module": "bridge_steel_timber",
        "geometry": {
            "span_count": q(2, "1"),
            "span_length": q(8, "m"),
            "deck_width": q(3, "m"),
            "crossbeam_spacing": q(1, "m"),
            "longitudinal_girder_count": q(3, "1"),
        },
        "actions": {
            "crowd_load": q(3.5, "kPa"),
            "additional_dead_load": q(0.8, "kPa"),
            "railing_dead_load_per_side": q(0.5, "kN/m"),
            "wind_line_load": q(0.8, "kN/m"),
            "span_live_load_factors": [q(1, "1"), q(0.5, "1")],
        },
        "timber_deck": {
            "thickness": q(80, "mm"),
            "elastic_modulus": q(11000, "MPa"),
            "bending_strength": q(18, "MPa"),
            "shear_strength": q(2, "MPa"),
            "unit_weight": q(6, "kN/m3"),
            "deflection_limit_ratio": q(300, "1"),
        },
        "crossbeam_section": section(),
        "longitudinal_section": section(),
        "comfort": {
            "damping_ratio": q(0.02, "1"),
            "walking_frequency": q(2, "Hz"),
            "pedestrian_dynamic_force": q(280, "N"),
            "acceleration_limit": q(0.5, "m/s2"),
        },
        "foundation_types": ["shallow", "pile", "shallow"],
    }


def rc_bridge_inputs() -> dict:
    return {
        "module": "bridge_rc",
        "geometry": {
            "span_count": q(2, "1"),
            "span_length": q(6, "m"),
            "deck_width": q(3, "m"),
            "deck_elevation": q(2, "m"),
            "slab_thickness": q(180, "mm"),
            "girder_count": q(3, "1"),
            "girder_width": q(300, "mm"),
            "girder_height": q(600, "mm"),
        },
        "material": {
            "concrete_elastic_modulus": q(30000, "MPa"),
            "concrete_compressive_strength": q(14.3, "MPa"),
            "concrete_tensile_strength": q(1.43, "MPa"),
            "rebar_yield_strength": q(360, "MPa"),
            "concrete_density": q(25, "kN/m3"),
            "minimum_reinforcement_ratio": q(0.0015, "1"),
            "maximum_reinforcement_ratio": q(0.04, "1"),
        },
        "reinforcement": {
            "cover": q(40, "mm"),
            "slab_bar_diameter": q(12, "mm"),
            "slab_bar_spacing": q(150, "mm"),
            "girder_bottom_area": q(4000, "mm2"),
            "girder_top_area": q(3000, "mm2"),
            "girder_stirrup_area": q(157, "mm2"),
            "girder_stirrup_spacing": q(150, "mm"),
        },
        "loads": {
            "spans": [
                {"additional_dead": q(1, "kPa"), "crowd": q(5, "kPa")},
                {"additional_dead": q(1, "kPa"), "crowd": q(2, "kPa")},
            ],
            "railing_left": q(1, "kN/m"),
            "railing_right": q(2, "kN/m"),
            "wind_pressure": q(0.8, "kPa"),
            "wind_exposed_height": q(1.2, "m"),
        },
        "supports": [
            {"id": "A", "node_index": q(0, "1"), "foundation_type": "shallow"},
            {"id": "B", "node_index": q(1, "1"), "foundation_type": "pile"},
            {"id": "C", "node_index": q(2, "1"), "foundation_type": "shallow"},
        ],
        "service_limits": {
            "crack_width_limit": q(0.3, "mm"),
            "minimum_vertical_frequency": q(3, "Hz"),
            "slab_deflection_ratio": q(250, "1"),
            "girder_deflection_ratio": q(400, "1"),
            "cracked_stiffness_factor": q(0.35, "1"),
        },
    }


def gravity_wall_inputs() -> dict:
    return {
        "module": "gravity_retaining_wall",
        "combination_id": "ULS-GRW-1",
        "combination_name": "ULS soil pressure leading",
        "limit_state": "ULS",
        "retained_height": q(2.0, "m"),
        "base_width": q(2.4, "m"),
        "base_slab_thickness": q(0.3, "m"),
        "wall_bottom_thickness": q(1.2, "m"),
        "wall_top_thickness": q(0.5, "m"),
        "toe_projection": q(0.7, "m"),
        "wall_unit_weight": q(24, "kN/m3"),
        "soil_unit_weight": q(18, "kN/m3"),
        "soil_friction_angle": q(30, "deg"),
        "surcharge": q(5, "kPa"),
        "base_friction_coefficient": q(0.6, "1"),
        "soil_bearing_capacity": q(300, "kPa"),
        "material_compressive_design": q(1000, "kPa"),
        "water_depth_behind": q(0.8, "m"),
        "water_unit_weight": q(10, "kN/m3"),
        "uplift_head_toe": q(0, "m"),
        "uplift_head_heel": q(0.5, "m"),
        "sliding_safety_factor": q(1, "1"),
        "overturning_safety_factor": q(1, "1"),
    }


CASES = [
    ("pool_structure", pool_inputs),
    ("pile_group_cap", pile_inputs),
    ("bridge_steel_timber", steel_bridge_inputs),
    ("bridge_rc", rc_bridge_inputs),
    ("gravity_retaining_wall", gravity_wall_inputs),
]


@pytest.mark.parametrize(("module", "factory"), CASES)
def test_infrastructure_modules_run_through_api(
    client: TestClient, module: str, factory
) -> None:
    response = client.post("/api/v2/calculate", json=request(module, factory()))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["module"] == module
    assert result["verification_status"] == "unverified"
    assert result["combinations"]
    assert result["checks"]
    assert result["steps"]
    assert result["schema_version"] == "3.2"


def test_infrastructure_openapi_discriminator_is_complete() -> None:
    schema = CalculationRequest.model_json_schema()
    typed = schema["properties"]["typed_inputs"]["anyOf"][0]
    mapping = typed["discriminator"]["mapping"]
    assert {module for module, _ in CASES} <= mapping.keys()
    assert mapping["pool_structure"].endswith("PoolStructureInputs")
    assert mapping["pile_group_cap"].endswith("PileGroupCapInputs")
    assert mapping["bridge_steel_timber"].endswith("BridgeSteelTimberInputs")
    assert mapping["bridge_rc"].endswith("BridgeRCInputs")
    assert mapping["gravity_retaining_wall"].endswith(
        "GravityRetainingWallInputs"
    )


@pytest.mark.parametrize(
    ("module", "factory"),
    [
        ("pool_structure", pool_inputs),
        ("bridge_steel_timber", steel_bridge_inputs),
        ("bridge_rc", rc_bridge_inputs),
        ("gravity_retaining_wall", gravity_wall_inputs),
    ],
)
def test_reaction_envelopes_preserve_complete_combination_effects(
    client: TestClient, module: str, factory
) -> None:
    response = client.post("/api/v2/calculate", json=request(module, factory()))
    assert response.status_code == 200, response.text
    result = response.json()
    combinations = {
        item["combination_id"]: item for item in result["combinations"]
    }
    for combination_id, combination in combinations.items():
        assert set(combination["effect_components"]) == {
            "N",
            "Vx",
            "Vy",
            "Mx",
            "My",
            "T",
        }
        envelopes = [
            item
            for item in result["reaction_envelopes"]
            if item["combination_id"] == combination_id
        ]
        assert envelopes
        assert all(
            set(item["components"]) == {"N", "Vx", "Vy", "Mx", "My", "T"}
            for item in envelopes
        )
        for component in ("N", "Vx", "Vy", "Mx", "My", "T"):
            total = sum(item["components"][component]["value"] for item in envelopes)
            external = combination["effect_components"][component]["value"]
            assert total + external == pytest.approx(0.0, abs=1e-8)


def test_infrastructure_module_rejects_another_modules_typed_shape(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v2/calculate",
        json=request("pile_group_cap", pool_inputs()),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "typed_input_module_mismatch"


def test_professional_unverified_failure_is_incomplete_with_provisional_checks(
    client: TestClient,
) -> None:
    typed = pile_inputs()
    typed["capacities"]["compression"] = q(100, "kN")
    response = client.post(
        "/api/v2/calculate",
        json=request("pile_group_cap", typed, mode="professional"),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "incomplete"
    assert result["engineering_status"] == "incomplete"
    assert result["workflow_status"] == "capability_unavailable"
    assert result["provisional_checks"]
    assert any(not item["passed"] for item in result["provisional_checks"])


def test_gravity_wall_professional_failure_is_provisional_until_verified(
    client: TestClient,
) -> None:
    typed = gravity_wall_inputs()
    typed["soil_bearing_capacity"] = q(1, "kPa")
    response = client.post(
        "/api/v2/calculate",
        json=request("gravity_retaining_wall", typed, mode="professional"),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "incomplete"
    assert result["engineering_status"] == "incomplete"
    assert result["workflow_status"] == "capability_unavailable"
    assert result["provisional_checks"]
    assert any(not item["passed"] for item in result["provisional_checks"])


def test_invalid_nested_unit_is_structured_422(client: TestClient) -> None:
    typed = deepcopy(pool_inputs())
    typed["geometry"]["inside_length"] = q(6, "kg")
    response = client.post(
        "/api/v2/calculate", json=request("pool_structure", typed)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_unit"
    assert response.json()["error"]["field"] == "geometry.inside_length"


def test_gravity_wall_invalid_unit_is_structured_422(client: TestClient) -> None:
    typed = gravity_wall_inputs()
    typed["retained_height"] = q(2, "kg")
    response = client.post(
        "/api/v2/calculate", json=request("gravity_retaining_wall", typed)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_unit"
    assert response.json()["error"]["field"] == "retained_height"


@pytest.mark.parametrize(
    ("module", "project_name"),
    [
        ("pool_structure", "legacy pool"),
        ("gravity_retaining_wall", "legacy gravity wall"),
    ],
)
def test_schema31_infrastructure_request_remains_parseable_but_read_only(
    client: TestClient, module: str, project_name: str
) -> None:
    legacy = {
        "schema_version": "3.1",
        "mode": "quick",
        "module": module,
        "project_name": project_name,
        "inputs": {"legacy_snapshot": True},
        "loads": [],
    }
    parsed = CalculationRequest.model_validate(legacy)
    assert parsed.schema_version == "3.1"
    assert parsed.module.value == module
    response = client.post("/api/v2/calculate", json=legacy)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "legacy_schema_read_only"
