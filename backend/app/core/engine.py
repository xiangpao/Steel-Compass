from __future__ import annotations

from uuid import uuid4

from .concrete import calculate_concrete_column, calculate_concrete_member
from .frame import calculate_portal_frame
from .foundation import calculate_spread_footing, calculate_strip_footing
from .schemas import (
    CalculationMode,
    CalculationModule,
    CalculationRequest,
    CalculationResult,
    CalculationWarning,
)
from .steel import calculate_steel_beam, calculate_steel_column
from .timber import calculate_timber_beam, calculate_timber_column


# A module may move to independently_verified only when its immutable hand
# benchmark, independent script and standard mapping are all committed.  No
# current module meets that publication gate yet.
MODULE_VERIFICATION = {
    module: "unverified" for module in CalculationModule
}


def _apply_result_contract(
    request: CalculationRequest, result: CalculationResult
) -> CalculationResult:
    verification = MODULE_VERIFICATION[request.module]
    result.verification_status = verification  # type: ignore[assignment]
    result.result_class = (
        "quick_estimate"
        if request.mode is CalculationMode.QUICK
        else "professional_check"
    )

    hard_failure = any(not check.passed for check in result.checks)
    critical_warning = any(
        warning.severity == "critical" for warning in result.warnings
    )
    if hard_failure:
        result.status = "failed"
    elif request.mode is CalculationMode.PROFESSIONAL and (
        verification != "independently_verified" or critical_warning
    ):
        result.status = "incomplete"
    elif result.status not in {"incomplete", "not_applicable"}:
        result.status = "passed"

    if (
        request.mode is CalculationMode.PROFESSIONAL
        and verification != "independently_verified"
        and not any(
            warning.code == "independent_verification_pending"
            for warning in result.warnings
        )
    ):
        result.warnings.append(
            CalculationWarning(
                severity="critical",
                code="independent_verification_pending",
                message="该模块尚未完成手算、独立脚本及规范映射验收，专业模式不得形成通过结论。",
            )
        )
    return result


def calculate(request: CalculationRequest) -> CalculationResult:
    trace_id = str(uuid4())
    handlers = {
        CalculationModule.STEEL_BEAM: calculate_steel_beam,
        CalculationModule.STEEL_COLUMN: calculate_steel_column,
        CalculationModule.PORTAL_FRAME: calculate_portal_frame,
        CalculationModule.CONCRETE_BEAM: calculate_concrete_member,
        CalculationModule.CONCRETE_SLAB: calculate_concrete_member,
        CalculationModule.CONCRETE_COLUMN: calculate_concrete_column,
        CalculationModule.SPREAD_FOOTING: calculate_spread_footing,
        CalculationModule.STRIP_FOOTING: calculate_strip_footing,
        CalculationModule.TIMBER_BEAM: calculate_timber_beam,
        CalculationModule.TIMBER_COLUMN: calculate_timber_column,
    }
    result = handlers[request.module](request, trace_id)
    result.load_provenance = [item.model_copy(deep=True) for item in request.loads]
    result.catalog_versions.setdefault("schema", request.schema_version)
    return _apply_result_contract(request, result)
