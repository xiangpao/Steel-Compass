import pytest
from pydantic import ValidationError

from app.core.design_profiles import ColumnBaseAssembly


def profile(**overrides):
    return dict(id="base", column_member_id="c", support_id="s",
                base_plate_length_mm=400, base_plate_width_mm=400,
                base_plate_thickness_mm=25, anchor_grade="Q235B",
                anchor_diameter_mm=20, anchor_count=2, anchor_embedment_mm=300,
                **overrides)


def test_legacy_column_base_remains_readable():
    assert ColumnBaseAssembly(**profile()).model_dump().get("anchor_springs") == []


def test_contact_profile_round_trip_preserves_explicit_stiffness_and_source():
    data = profile(contact_stiffness_kn_m3=1e7, contact_model_source="Project stiffness calculation rev A",
                   anchor_springs=[dict(x_m=-.15, y_m=0, stiffness_kn_m=1e5),
                                   dict(x_m=.15, y_m=0, stiffness_kn_m=1e5)])
    assert ColumnBaseAssembly(**data).model_dump()["anchor_springs"] == data["anchor_springs"]


@pytest.mark.parametrize("changes", [
    {"contact_stiffness_kn_m3": -1},
    {"contact_stiffness_kn_m3": float("inf")},
    {"anchor_springs": [dict(x_m=0, y_m=0, stiffness_kn_m=0)]},
    {"anchor_springs": [dict(x_m=float("nan"), y_m=0, stiffness_kn_m=10)]},
    {"contact_model_source": " "},
])
def test_contact_profile_rejects_invalid_values(changes):
    with pytest.raises(ValidationError):
        ColumnBaseAssembly(**profile(**changes))
