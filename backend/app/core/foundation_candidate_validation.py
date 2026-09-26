"""Check the selected scheme dimensions against every saved combination."""
from .design_profiles import DesignCandidateSet, PedestalProfile, recommend_spread_foundation_from_reaction


def validate_candidate_combinations(
    candidate: DesignCandidateSet, reaction_cases: list[dict], *,
    bearing_capacity_kpa: float, pedestal: PedestalProfile | None = None,
    base_friction_coefficient: float = 0.30,
) -> DesignCandidateSet:
    if not candidate.converged or not candidate.recommended:
        return candidate
    selected = candidate.recommended
    length, width, thickness = (float(selected[key]) for key in ("length_m", "width_m", "thickness_mm"))
    failed, checked = [], []
    for case in reaction_cases:
        result = recommend_spread_foundation_from_reaction(
            foundation_instance_id=candidate.target_node_id, reaction=case["reaction"],
            bearing_capacity_kpa=bearing_capacity_kpa, initial_length_m=length,
            initial_width_m=width, initial_thickness_mm=thickness, pedestal=pedestal,
            base_friction_coefficient=base_friction_coefficient, max_plan_m=max(length, width),
        )
        # The first iteration checks exactly the selected dimensions. A later
        # converged shape cannot be substituted as evidence for this candidate.
        first = result.iterations[0] if result.iterations else {}
        passed = bool(first) and all(first.get(key) is True for key in ("bearing_ok", "full_contact_ok", "sliding_ok"))
        checked.append({**first, "combination_id": case["combination_id"], "candidate_recheck": True})
        if not passed:
            failed.append(str(case["combination_id"]))
    if failed or not reaction_cases:
        return candidate.model_copy(update={
            "converged": False, "recommended": None,
            "iterations": [*candidate.iterations, *checked],
            "failure_reason": "同一基础尺寸未通过全部组合复算：" + ("、".join(failed) or "缺少组合") + "；请调整长宽后重新分析。",
            "governing_check": "同一尺寸的全部组合承压、全接触与抗滑复算",
        })
    return candidate.model_copy(update={
        "recommended": {**selected, "validated_combination_ids": [str(case["combination_id"]) for case in reaction_cases]},
        "iterations": [*candidate.iterations, *checked],
        "governing_check": "同一尺寸的全部组合承压、全接触与抗滑复算（其余验算待完成）",
    })
