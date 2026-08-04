from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import require_ready_user
from ..core.engine import calculate
from ..core.catalogs import climate_catalog, load_catalog, material_catalog
from ..core.scenarios import SCENARIOS
from ..core.schemas import (
    CalculationRequest,
    CalculationResult,
    ScenarioTemplate,
)
from ..models import User


router = APIRouter(tags=["calculations"])


@router.get("/scenarios", response_model=list[ScenarioTemplate])
def list_scenarios(_: User = Depends(require_ready_user)) -> list[ScenarioTemplate]:
    return SCENARIOS


@router.post("/calculate", response_model=CalculationResult)
def run_calculation(
    payload: CalculationRequest,
    _: User = Depends(require_ready_user),
) -> CalculationResult:
    return calculate(payload)


@router.get("/standards")
def standards(_: User = Depends(require_ready_user)) -> dict:
    return {
        "profile": "CN-2024",
        "status": "Beta mapping",
        "standards": [
            "GB 55001-2021",
            "GB 55005-2021",
            "GB 55006-2021",
            "GB 55008-2021",
            "GB 50009-2012",
            "GB 50017-2017",
            "GB 50005-2017",
            "GB/T 50010-2010（2024年局部修订）",
        ],
    }


@router.get("/catalogs/materials")
def materials(_: User = Depends(require_ready_user)) -> dict:
    return material_catalog()


@router.get("/catalogs/load-presets")
def load_presets(_: User = Depends(require_ready_user)) -> dict:
    return load_catalog()


@router.get("/catalogs/climate-locations")
def climate_locations(
    query: str = Query(default="", max_length=80),
    _: User = Depends(require_ready_user),
) -> dict:
    return climate_catalog(query)
