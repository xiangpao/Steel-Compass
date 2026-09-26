from app.core.design_profiles import recommend_spread_foundation_from_reaction
from app.core.foundation_candidate_validation import validate_candidate_combinations


def test_largest_volume_candidate_is_not_accepted_for_orthogonal_moments():
    cases = [{"combination_id": "X", "reaction": {"fz_kn":60,"mx_kn_m":40}},
             {"combination_id": "Y", "reaction": {"fz_kn":60,"my_kn_m":40}}]
    candidate = recommend_spread_foundation_from_reaction(foundation_instance_id="F", reaction=cases[0]["reaction"],
        bearing_capacity_kpa=120, initial_length_m=1, initial_width_m=1, initial_thickness_mm=300)
    # Both separate optima have volume .9 m3 (1x3x.3 / 3x1x.3), but neither
    # contains the other. At 1x3 under Y, qmin=27.5-80=-52.5 kPa.
    assert candidate.converged
    result = validate_candidate_combinations(candidate, cases, bearing_capacity_kpa=120)
    assert not result.converged
    assert result.recommended is None
    assert "Y" in result.failure_reason


def test_single_geometry_must_meet_every_case_before_candidate_is_offered():
    cases = [{"combination_id": "X", "reaction": {"fz_kn":60,"mx_kn_m":40}},
             {"combination_id": "Y", "reaction": {"fz_kn":60,"my_kn_m":40}}]
    candidate = recommend_spread_foundation_from_reaction(foundation_instance_id="F", reaction=cases[0]["reaction"],
        bearing_capacity_kpa=120, initial_length_m=3, initial_width_m=3, initial_thickness_mm=300)
    result = validate_candidate_combinations(candidate, cases, bearing_capacity_kpa=120)
    assert result.converged
    assert result.recommended["validated_combination_ids"] == ["X","Y"]
