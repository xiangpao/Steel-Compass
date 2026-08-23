from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.auth import require_ready_user
from app.core.errors import CalculationInputError
from app.routers.calculation_routes import router


def q(value: float, unit: str) -> dict[str, float | str]:
    return {"value": value, "unit": unit}


@pytest.fixture()
def client() -> Iterator[TestClient]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v2")
    test_app.dependency_overrides[require_ready_user] = lambda: object()

    @test_app.exception_handler(CalculationInputError)
    async def handle_input_error(_: Request, exc: CalculationInputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})

    with TestClient(test_app) as api:
        yield api


def cases() -> list[dict]:
    return [
        {
            "combination_id": "ULS-W+",
            "combination_name": "positive wind",
            "limit_state": "ULS",
            "wind_pressure": q(0.8, "kPa"),
            "additional_dead_load": q(0.2, "kPa"),
        },
        {
            "combination_id": "ULS-W-",
            "combination_name": "negative wind",
            "limit_state": "ULS",
            "wind_pressure": q(-0.6, "kN/m2"),
            "additional_dead_load": q(0.2, "kN/m2"),
        },
    ]


def rc_inputs() -> dict:
    return {
        "module": "site_rc_wall",
        "height": q(1.8, "m"),
        "length": q(6, "m"),
        "thickness": q(180, "mm"),
        "support_spacing": q(3, "m"),
        "opening_ratio": q(0.1, "1"),
        "concrete_unit_weight": q(25, "kN/m3"),
        "concrete_fc": q(14.3, "MPa"),
        "concrete_ft": q(1.43, "MPa"),
        "rebar_fy": q(360, "MPa"),
        "vertical_rebar": q(1200, "mm2/m"),
        "horizontal_rebar": q(1200, "mm2/m"),
        "cover": q(30, "mm"),
        "bar_diameter": q(12, "mm"),
        "minimum_reinforcement_ratio": q(0.0015, "1"),
        "slenderness_limit": q(25, "1"),
        "load_cases": cases(),
    }


def steel_inputs() -> dict:
    return {
        "module": "steel_infill_wall",
        "height": q(2, "m"),
        "length": q(8, "m"),
        "support_spacing": q(2, "m"),
        "opening_ratio": q(0.1, "1"),
        "infill_dead_load": q(0.5, "kPa"),
        "post_self_weight": q(0.12, "kN/m"),
        "post_area": q(3000, "mm2"),
        "post_inertia": q(8e6, "mm4"),
        "post_section_modulus": q(8e4, "mm3"),
        "steel_elastic_modulus": q(206, "GPa"),
        "steel_yield_strength": q(235, "MPa"),
        "effective_length_factor": q(1, "1"),
        "slenderness_limit": q(150, "1"),
        "maximum_post_spacing": q(3, "m"),
        "load_cases": cases(),
    }


def masonry_inputs() -> dict:
    return {
        "module": "plain_masonry_wall",
        "height": q(1, "m"),
        "length": q(6, "m"),
        "thickness": q(240, "mm"),
        "support_spacing": q(3, "m"),
        "opening_ratio": q(0.1, "1"),
        "masonry_unit_weight": q(19, "kN/m3"),
        "masonry_bending_strength": q(0.4, "MPa"),
        "masonry_shear_strength": q(0.15, "MPa"),
        "masonry_compression_strength": q(2, "MPa"),
        "slenderness_limit": q(15, "1"),
        "minimum_thickness": q(120, "mm"),
        "maximum_height": q(1.5, "m"),
        "load_cases": cases(),
    }


def request(module: str, typed_inputs: dict, *, mode: str = "quick", schema: str = "3.3") -> dict:
    return {
        "schema_version": schema,
        "mode": mode,
        "module": module,
        "project_name": module,
        "standard_profile": "CN-2026.2",
        "typed_inputs": typed_inputs,
        "loads": [],
    }


@pytest.mark.parametrize(
    "module, inputs",
    [
        ("site_rc_wall", rc_inputs),
        ("steel_infill_wall", steel_inputs),
        ("plain_masonry_wall", masonry_inputs),
    ],
)
def test_site_wall_modules_expose_typed_api_and_same_combination_equilibrium(
    client: TestClient, module: str, inputs,
) -> None:
    response = client.post("/api/v2/calculate", json=request(module, inputs()))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["module"] == module
    assert result["schema_version"] == "3.3"
    assert result["verification_status"] == "unverified"
    assert result["result_class"] == "quick_estimate"
    assert result["engineering_status"] is None
    assert result["quick_outcome"] in {"screening_passed", "screening_failed"}
    assert len(result["combinations"]) == len(result["reaction_envelopes"]) == 2
    envelopes = {item["combination_id"]: item for item in result["reaction_envelopes"]}
    for combination in result["combinations"]:
        reaction = envelopes[combination["combination_id"]]
        assert set(reaction["components"]) == {"N", "Vx", "Vy", "Mx", "My", "T"}
        for component in ("N", "Vx", "Vy", "Mx", "My", "T"):
            external = combination["effect_components"][component]["value"]
            support = reaction["components"][component]["value"]
            assert external + support == pytest.approx(0.0, abs=1e-12)
    assert envelopes["ULS-W+"]["components"]["Vx"]["value"] < 0
    assert envelopes["ULS-W-"]["components"]["Vx"]["value"] > 0


def test_professional_unverified_failure_is_incomplete_with_provisional_checks(
    client: TestClient,
) -> None:
    inputs = rc_inputs()
    inputs["vertical_rebar"] = q(100, "mm2/m")
    response = client.post(
        "/api/v2/calculate",
        json=request("site_rc_wall", inputs, mode="professional"),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "incomplete"
    assert result["workflow_status"] == "capability_unavailable"
    assert result["engineering_status"] == "incomplete"
    assert result["quick_outcome"] is None
    assert result["verification_status"] == "unverified"
    assert result["provisional_checks"]
    assert all(not item["passed"] for item in result["provisional_checks"])


def test_explicit_units_reject_incompatible_values(client: TestClient) -> None:
    inputs = steel_inputs()
    inputs["post_inertia"] = q(8e6, "mm3")
    response = client.post(
        "/api/v2/calculate",
        json=request("steel_infill_wall", inputs),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_unit"
    assert response.json()["error"]["field"] == "post_inertia"


def test_openapi_contains_three_discriminated_site_wall_contracts(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    request_schema = schema["components"]["schemas"]["CalculationRequest"]
    typed = request_schema["properties"]["typed_inputs"]["anyOf"][0]
    refs = {item["$ref"].rsplit("/", 1)[-1] for item in typed["oneOf"]}
    assert {"SiteRCWallInputs", "SteelInfillWallInputs", "PlainMasonryWallInputs"} <= refs
    assert typed["discriminator"]["propertyName"] == "module"


def test_schema31_request_parses_but_calculation_endpoint_is_read_only(client: TestClient) -> None:
    response = client.post(
        "/api/v2/calculate",
        json=request("site_rc_wall", rc_inputs(), schema="3.1"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "legacy_schema_read_only"
