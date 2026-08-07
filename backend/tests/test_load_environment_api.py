from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.auth import require_ready_user
from app.core.errors import CalculationInputError
from app.core.schemas import CalculationRequest
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


def request(module: str, typed_inputs: dict, *, mode: str = "quick", schema: str = "3.2") -> dict:
    return {
        "schema_version": schema,
        "mode": mode,
        "module": module,
        "project_name": f"load-environment-{module}",
        "standard_profile": "CN-2026.1",
        "typed_inputs": typed_inputs,
        "loads": [],
    }


def combination_inputs() -> dict:
    return {
        "module": "load_combinations",
        "cases": [
            {
                "id": "G",
                "label": "permanent",
                "category": "permanent",
                "characteristic": q(100, "kN"),
                "direction": "gravity",
                "distribution": "point",
                "target": "base",
                "source_reference": "geometry and material takeoff",
            },
            {
                "id": "W+",
                "label": "positive wind",
                "category": "wind",
                "characteristic": q(40, "kN"),
                "direction": "x_positive",
                "distribution": "point",
                "target": "base",
                "source_reference": "reviewed wind guide",
                "exclusive_group": "wind-direction",
                "psi0": q(0.6, "1"),
                "psi1": q(0.2, "1"),
                "psi2": q(0, "1"),
            },
            {
                "id": "W-UP",
                "label": "wind uplift",
                "category": "wind",
                "characteristic": q(80, "kN"),
                "direction": "uplift",
                "distribution": "point",
                "target": "base",
                "source_reference": "reviewed uplift guide",
                "exclusive_group": "wind-direction",
                "psi0": q(0.6, "1"),
                "psi1": q(0.2, "1"),
                "psi2": q(0, "1"),
            },
        ],
    }


def wind_snow_inputs(*, no_snow: bool = False) -> dict:
    return {
        "module": "wind_snow_guide",
        "basic_wind_pressure": q(0.45, "kPa"),
        "wind_source_reference": "reviewed GB 50009 wind table",
        "recurrence_period": q(50, "year"),
        "recurrence_factor": q(1, "1"),
        "terrain_roughness": "B",
        "terrain_height_factor": q(1.2, "1"),
        "shape_coefficient_positive": q(0.8, "1"),
        "shape_coefficient_negative": q(-0.6, "1"),
        "wind_area": q(10, "m2"),
        "snow_applicability": "not_applicable" if no_snow else "applicable",
        "basic_snow_pressure": None if no_snow else q(0, "kPa"),
        "snow_source_reference": None if no_snow else "reviewed snow table",
        "roof_snow_coefficient": None if no_snow else q(0.8, "1"),
        "snow_area": None if no_snow else q(12, "m2"),
        "no_snow_basis": "reviewed climate record: no snow" if no_snow else None,
        "target": "roof",
    }


def soil_water_inputs() -> dict:
    return {
        "module": "soil_water_actions",
        "wall_height": q(3, "m"),
        "earth_pressure_state": "active",
        "soil_unit_weight_dry": q(18, "kN/m3"),
        "soil_unit_weight_saturated": q(20, "kN/m3"),
        "soil_friction_angle": q(30, "deg"),
        "surcharge": q(5, "kPa"),
        "groundwater_depth_below_top": q(1, "m"),
        "water_unit_weight": q(10, "kN/m3"),
        "internal_water_depth": q(1, "m"),
        "external_water_depth": q(2, "m"),
        "base_area": q(6, "m2"),
        "source_reference": "investigation report and operating water levels",
        "target": "pool-wall-base",
    }


@pytest.mark.parametrize(
    ("module", "factory"),
    [
        ("load_combinations", combination_inputs),
        ("wind_snow_guide", wind_snow_inputs),
        ("soil_water_actions", soil_water_inputs),
    ],
)
def test_load_environment_modules_run_through_schema32_api(
    client: TestClient, module: str, factory
) -> None:
    response = client.post("/api/v2/calculate", json=request(module, factory()))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["module"] == module
    assert result["schema_version"] == "3.2"
    assert result["verification_status"] == "unverified"
    assert result["status"] == "passed"
    assert result["quick_outcome"] == "screening_passed"
    assert result["combinations"]
    assert result["steps"]
    assert result["trace_id"]


def test_load_combination_api_preserves_direction_source_distribution_and_uplift() -> None:
    parsed = CalculationRequest.model_validate(
        request("load_combinations", combination_inputs())
    )
    assert parsed.typed_inputs.cases[1].distribution == "point"
    assert parsed.typed_inputs.cases[1].source_reference == "reviewed wind guide"

    from app.core.engine import calculate

    result = calculate(parsed)
    uplift = next(
        item for item in result.combinations if item.leading_action == "W-UP"
    )
    assert uplift.factors["G"] == pytest.approx(0.9)
    assert uplift.effect_components["N"].value == pytest.approx(-30)
    assert uplift.directions_by_kind["W-UP"] == ["uplift"]
    assert result.input_summary["distribution.W-UP"] == "point"
    assert result.input_summary["source.W-UP"] == "reviewed uplift guide"


def test_zero_snow_and_not_applicable_snow_are_distinct_api_results(
    client: TestClient,
) -> None:
    zero = client.post(
        "/api/v2/calculate",
        json=request("wind_snow_guide", wind_snow_inputs()),
    )
    assert zero.status_code == 200, zero.text
    zero_result = zero.json()
    snow = next(item for item in zero_result["combinations"] if item["name"] == "roof-snow")
    assert snow["total"]["value"] == 0
    assert zero_result["input_summary"]["snow_status"] == "calculated"

    no_snow = client.post(
        "/api/v2/calculate",
        json=request("wind_snow_guide", wind_snow_inputs(no_snow=True)),
    )
    assert no_snow.status_code == 200, no_snow.text
    result = no_snow.json()
    assert result["input_summary"]["snow_status"] == "not_applicable"
    assert result["input_summary"]["no_snow_basis"]
    assert {item["name"] for item in result["combinations"]} == {
        "wind-positive",
        "wind-negative",
    }


def test_soil_water_api_outputs_signed_pressure_and_buoyancy_actions(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v2/calculate",
        json=request("soil_water_actions", soil_water_inputs()),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    combinations = {item["name"]: item for item in result["combinations"]}
    assert combinations["external-water"]["effect_components"]["Vx"]["value"] > 0
    assert combinations["internal-water"]["effect_components"]["Vx"]["value"] < 0
    assert combinations["base-uplift"]["effect_components"]["N"]["value"] < 0
    assert result["input_summary"]["source"] == (
        "investigation report and operating water levels"
    )


@pytest.mark.parametrize(
    ("module", "typed", "field"),
    [
        (
            "wind_snow_guide",
            {**wind_snow_inputs(), "wind_area": q(10, "kN")},
            "wind_area",
        ),
        (
            "soil_water_actions",
            {**soil_water_inputs(), "wall_height": q(3, "kPa")},
            "wall_height",
        ),
    ],
)
def test_load_environment_api_rejects_wrong_units(
    client: TestClient, module: str, typed: dict, field: str
) -> None:
    response = client.post("/api/v2/calculate", json=request(module, typed))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_unit"
    assert response.json()["error"]["field"] == field


@pytest.mark.parametrize(
    ("module", "factory"),
    [
        ("load_combinations", combination_inputs),
        ("wind_snow_guide", wind_snow_inputs),
        ("soil_water_actions", soil_water_inputs),
    ],
)
def test_professional_load_environment_modules_remain_incomplete_until_verified(
    client: TestClient, module: str, factory
) -> None:
    response = client.post(
        "/api/v2/calculate",
        json=request(module, factory(), mode="professional"),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "incomplete"
    assert result["engineering_status"] == "incomplete"
    assert result["workflow_status"] == "capability_unavailable"
    assert result["verification_status"] == "unverified"
    assert any(
        warning["code"] == "independent_verification_pending"
        for warning in result["warnings"]
    )
    assert all(not item["passed"] for item in result["provisional_checks"])


def test_openapi_discriminator_and_legacy_read_only_contract(client: TestClient) -> None:
    schema = CalculationRequest.model_json_schema()
    typed = schema["properties"]["typed_inputs"]["anyOf"][0]
    mapping = typed["discriminator"]["mapping"]
    assert mapping["load_combinations"].endswith("LoadCombinationsInputs")
    assert mapping["wind_snow_guide"].endswith("WindSnowGuideInputs")
    assert mapping["soil_water_actions"].endswith("SoilWaterActionsInputs")

    legacy = CalculationRequest.model_validate(
        request(
            "load_combinations",
            combination_inputs(),
            schema="3.1",
        )
    )
    assert legacy.schema_version == "3.1"
    response = client.post(
        "/api/v2/calculate",
        json=request("load_combinations", combination_inputs(), schema="3.1"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "legacy_schema_read_only"
