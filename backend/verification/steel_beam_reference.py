"""Independent closed-form mechanics used only by verification tests.

This module intentionally does not import the production calculation engine.
It verifies reactions, shear, bending moment and elastic deflection for the
strictly limited UDL beam cases supported by the first steel-beam gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BeamReferenceResult:
    reaction_left_kn: float
    reaction_right_kn: float
    maximum_shear_kn: float
    maximum_moment_kn_m: float
    maximum_deflection_mm: float


def solve_udl_beam(
    *,
    support: Literal["simple", "cantilever"],
    line_load_kn_m: float,
    span_m: float,
    elastic_modulus_mpa: float,
    inertia_mm4: float,
) -> BeamReferenceResult:
    if line_load_kn_m < 0 or span_m <= 0 or elastic_modulus_mpa <= 0 or inertia_mm4 <= 0:
        raise ValueError("reference beam inputs are outside the verified domain")

    span_mm = span_m * 1000
    line_load_n_mm = line_load_kn_m
    if support == "simple":
        reaction = line_load_kn_m * span_m / 2
        moment = line_load_kn_m * span_m**2 / 8
        deflection = (
            5
            * line_load_n_mm
            * span_mm**4
            / (384 * elastic_modulus_mpa * inertia_mm4)
        )
        return BeamReferenceResult(
            reaction_left_kn=reaction,
            reaction_right_kn=reaction,
            maximum_shear_kn=reaction,
            maximum_moment_kn_m=moment,
            maximum_deflection_mm=deflection,
        )

    reaction = line_load_kn_m * span_m
    moment = line_load_kn_m * span_m**2 / 2
    deflection = (
        line_load_n_mm * span_mm**4 / (8 * elastic_modulus_mpa * inertia_mm4)
    )
    return BeamReferenceResult(
        reaction_left_kn=reaction,
        reaction_right_kn=0.0,
        maximum_shear_kn=reaction,
        maximum_moment_kn_m=moment,
        maximum_deflection_mm=deflection,
    )
