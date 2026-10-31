"""Check the selected scheme dimensions against every saved combination."""
from typing import Any

from .design_profiles import (
    FOUNDATION_SYSTEM_CATALOG_VERSION,
    DesignCandidateSet,
    FoundationTypeDefinition,
    PedestalProfile,
    ProjectGeotechnicalProfile,
    SceneGeometryProfile,
    recommend_spread_foundation_from_reaction,
)
from .errors import CalculationInputError
from .scene_foundation import evaluate_scene_foundation


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


# Failures that a larger plan relieves; one-way shear and punching need depth.
# Reinforcement is a design input the size search never changes.
_PLAN_CHECKS = {
    "地基承载力", "基底脱开区比例", "抗滑稳定", "抗倾覆稳定", "抗浮稳定",
    "地下水抗浮稳定系数", "地基沉降分层总和法（2:1应力扩散）",
}
_DEPTH_MARKERS = ("剪", "冲切")


def _candidate_failure(
    foundation_id: str, reason: str, iterations: list[dict[str, Any]], governing: str,
) -> DesignCandidateSet:
    return DesignCandidateSet(
        target_node_id=foundation_id,
        candidate_type="foundation",
        recommended=None,
        alternatives=iterations[-2:],
        iterations=iterations,
        governing_check=governing,
        converged=False,
        failure_reason=reason,
        catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION,
    )


def size_scene_foundation_candidate(
    geometry: SceneGeometryProfile,
    foundation_instance_id: str,
    support_reactions: dict[str, dict[str, Any]],
    geotechnical: ProjectGeotechnicalProfile | None,
    *,
    project_name: str,
    max_plan_m: float = 6.0,
    max_thickness_mm: float = 3000.0,
) -> DesignCandidateSet:
    """Size a spread footing by running the final foundation check per trial.

    Every trial size goes through ``evaluate_scene_foundation`` with all saved
    ULS/SLS combinations, soil cover, groundwater/anti-float level, pedestal
    and the project friction coefficient, so the recommended size cannot be
    rejected by the final check for a reason the search ignored. Plan grows in
    0.1 m steps for soil/stability failures (towards the governing moment
    axis), thickness in 50 mm steps for shear/punching. Reinforcement and
    missing inputs stop the search rather than being worked around.
    """
    instance = next(item for item in geometry.foundation_instances if item.id == foundation_instance_id)
    foundation_type = next(item for item in geometry.foundation_types if item.id == instance.foundation_type_id)
    support = next(item for item in geometry.supports if item.id == instance.support_id)
    column_base = next((item for item in geometry.column_bases if item.support_id == support.id), None)
    governing = "逐尺寸执行完整基础验算（全部组合、覆土、地下水、短柱与项目摩擦系数）"
    iterations: list[dict[str, Any]] = []
    trial = foundation_type
    while True:
        try:
            item = evaluate_scene_foundation(
                instance, trial, support, column_base, support_reactions, geotechnical,
                project_name=project_name,
            )
        except CalculationInputError as exc:
            return _candidate_failure(instance.id, f"试算尺寸不能形成有效基础验算：{exc.message}", iterations, governing)
        if item["status"] == "not_calculated":
            return _candidate_failure(
                instance.id, "基础验算缺少输入：" + "、".join(item["missing_inputs"]), iterations, governing)
        unresolved = any(warning.get("code") == "partial_contact" for warning in item["warnings"])
        failed = list(item["failed_checks"])
        iteration = {
            "length_m": round(trial.length_m, 1),
            "width_m": round(trial.width_m, 1),
            "thickness_mm": trial.thickness_mm,
            "final_check_status": item["status"],
            "failed_checks": failed,
            "contact_unresolved": unresolved,
            "calculation_trace_id": item["calculation_trace_id"],
            "pending_checks": item["pending_checks"],
            "incomplete_warning_codes": [
                warning["code"] for warning in item["warnings"] if warning.get("severity") == "critical"
            ],
        }
        iterations.append(iteration)
        if not failed and not unresolved:
            return DesignCandidateSet(
                target_node_id=instance.id,
                candidate_type="foundation",
                recommended={
                    **iteration,
                    "validated_combination_ids": [
                        record.get("combination_id") or record.get("combination_name")
                        for record in item["contact_solutions"]
                    ],
                },
                alternatives=iterations[-3:-1],
                iterations=iterations,
                governing_check=governing,
                converged=True,
                catalog_version=FOUNDATION_SYSTEM_CATALOG_VERSION,
            )
        plan_failure = unresolved or any(name in _PLAN_CHECKS for name in failed)
        depth_failure = any(marker in name for name in failed for marker in _DEPTH_MARKERS)
        update: dict[str, float]
        if plan_failure:
            # My eccentricity acts along x (length), Mx along y (width); with
            # no governing moment the shorter side grows.
            score_length = abs(float(item["reactions"]["My"]["value"])) / trial.length_m
            score_width = abs(float(item["reactions"]["Mx"]["value"])) / trial.width_m
            grow_length = (
                trial.length_m <= trial.width_m
                if abs(score_length - score_width) < 1e-9
                else score_length > score_width
            )
            update = (
                {"length_m": round(trial.length_m + 0.1, 10)}
                if grow_length
                else {"width_m": round(trial.width_m + 0.1, 10)}
            )
            if max(trial.length_m, trial.width_m, *update.values()) > max_plan_m + 1e-9:
                return _candidate_failure(
                    instance.id,
                    f"达到场景尺寸上限 {max_plan_m:.1f}m 仍未通过：" + "、".join(failed or ["接触平衡"])
                    + "；不会自动切换桩基。",
                    iterations, governing)
        elif depth_failure:
            update = {"thickness_mm": trial.thickness_mm + 50}
            if update["thickness_mm"] > max_thickness_mm:
                return _candidate_failure(
                    instance.id, f"基础厚度达到 {max_thickness_mm:.0f}mm 仍未通过：" + "、".join(failed),
                    iterations, governing)
        else:
            return _candidate_failure(
                instance.id,
                "以下验算不能靠调整基础尺寸解决，候选搜索不改变配筋：" + "、".join(failed) + "；请调整配筋后重新试算。",
                iterations, governing)
        trial = FoundationTypeDefinition.model_validate({**trial.model_dump(), **update})
