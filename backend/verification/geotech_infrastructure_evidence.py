"""Release-gate evidence for gravity walls, pools, and pile groups."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClauseCandidate:
    check: str
    standard: str
    topic: str
    status: str = "candidate_pending_clause_review"


@dataclass(frozen=True)
class InfrastructureEvidence:
    module: str
    applicability: tuple[str, ...]
    boundaries: tuple[str, ...]
    mappings: tuple[ClauseCandidate, ...]
    independent_case: str
    threshold_evidence: str
    evidence_date: str
    remaining_gaps: tuple[str, ...]
    reviewer: str | None = None
    human_review_date: str | None = None
    verification_status: str = "unverified"


GEOTECH_INFRASTRUCTURE_EVIDENCE: dict[str, InfrastructureEvidence] = {
    "gravity_retaining": InfrastructureEvidence(
        module="gravity_retaining",
        applicability=("straight gravity wall per metre", "level single-layer backfill", "static soil and water actions"),
        boundaries=("no seismic action", "no global stability or settlement", "no passive resistance credit", "no material-specific masonry detailing"),
        mappings=(
            ClauseCandidate("Rankine active pressure", "GB 50007-2011", "earth pressure and foundation stability"),
            ClauseCandidate("sliding, overturning and base pressure", "GB 55003-2021 / GB 50007-2011", "foundation stability and bearing"),
            ClauseCandidate("wall material compression", "material standard not yet selected", "material resistance and detailing"),
        ),
        independent_case="GI-GRW-001 closed-form soil/water integration and base equilibrium",
        threshold_evidence="material compression and sliding decisions exercised at 0.99 and 1.01 utilization",
        evidence_date="2026-08-04",
        remaining_gaps=("exact clause/table review", "material-specific resistance mapping", "groundwater/drainage assumptions review", "signed human calculation review"),
    ),
    "pool_structure": InfrastructureEvidence(
        module="pool_structure",
        applicability=("rectangular RC pool", "single soil layer", "static internal/external water", "one-metre wall strips and simplified two-way base"),
        boundaries=("no construction-joint or watertight detailing", "no nonlinear soil contact", "no seismic or thermal action", "no irregular geometry"),
        mappings=(
            ClauseCandidate("RC flexure, shear and minimum reinforcement", "GB/T 50010-2010 (2024 amendment)", "RC resistance and detailing"),
            ClauseCandidate("crack width", "GB/T 50010-2010 (2024 amendment) / GB 55008-2021", "serviceability and durability"),
            ClauseCandidate("uplift and bearing", "GB 55003-2021 / GB 50007-2011", "foundation stability and bearing"),
        ),
        independent_case="GI-POOL-001 empty/full action combinations, RC strip capacity and uplift",
        threshold_evidence="antifloat decision exercised at 0.99 and 1.01 utilization",
        evidence_date="2026-08-04",
        remaining_gaps=("exact clause/table review", "crack-width equation validation", "two-way base distribution validation", "watertight detailing checks", "signed human calculation review"),
    ),
    "pile_group": InfrastructureEvidence(
        module="pile_group",
        applicability=("centred rigid pile cap", "input geotechnical pile capacities", "static six-component action allocation", "shallow cap screening"),
        boundaries=("no capacity derivation from soil layers", "no settlement or group-soil interaction", "no pile structural design", "no deep-cap strut-and-tie or seismic checks"),
        mappings=(
            ClauseCandidate("single-pile capacity input and group checks", "JGJ 94-2008 / GB 50007-2011", "pile foundation design"),
            ClauseCandidate("foundation mandatory requirements", "GB 55003-2021", "pile and cap safety"),
            ClauseCandidate("cap punching, shear and flexure", "GB/T 50010-2010 (2024 amendment)", "RC pile-cap resistance"),
        ),
        independent_case="GI-PILE-001 rigid-cap force allocation and cap checks",
        threshold_evidence="compression, uplift and horizontal pile decisions exercised at 0.99 and 1.01 utilization",
        evidence_date="2026-08-04",
        remaining_gaps=("exact clause/table review", "pile-group soil interaction and settlement", "lateral group and axial-horizontal interaction", "deep-cap and anchorage checks", "signed human calculation review"),
    ),
}


def can_promote(record: InfrastructureEvidence) -> bool:
    """Require every verification gate; formula agreement alone is insufficient."""

    return (
        record.verification_status == "independently_verified"
        and record.reviewer is not None
        and record.human_review_date is not None
        and not record.remaining_gaps
        and all(mapping.status == "reviewed_and_signed" for mapping in record.mappings)
    )
