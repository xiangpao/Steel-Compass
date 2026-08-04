from __future__ import annotations

import pytest

from app.core.loads import line_load_envelope
from app.core.schemas import LoadDirection, LoadItem, LoadKind


def test_opposite_wind_directions_generate_separate_combinations() -> None:
    envelope = line_load_envelope(
        [
            LoadItem(
                kind=LoadKind.WIND,
                value=1.0,
                unit="kN/m",
                source="positive wind",
                direction=LoadDirection.X_POSITIVE,
            ),
            LoadItem(
                kind=LoadKind.WIND,
                value=1.4,
                unit="kN/m",
                source="negative wind",
                direction=LoadDirection.X_NEGATIVE,
            ),
        ]
    )
    sls = [item for item in envelope.combinations if item.limit_state == "SLS"]
    assert sorted(item.total.value for item in sls) == pytest.approx([-1.4, 1.0])
    assert {
        item.directions_by_kind["wind"][0] for item in sls
    } == {LoadDirection.X_POSITIVE, LoadDirection.X_NEGATIVE}
    assert envelope.governing_uls.total.value < 0


def test_uplift_direction_is_algebraically_negative() -> None:
    envelope = line_load_envelope(
        [
            LoadItem(
                kind=LoadKind.DEAD,
                value=0.5,
                unit="kN/m",
                source="dead",
            ),
            LoadItem(
                kind=LoadKind.WIND,
                value=2.0,
                unit="kN/m",
                source="uplift",
                direction=LoadDirection.UPLIFT,
            ),
        ]
    )
    assert envelope.governing_sls.total.value == pytest.approx(-1.5)
