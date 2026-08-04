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
    standard = [item for item in sls if item.sls_type == "standard"]
    assert min(item.total.value for item in standard) == pytest.approx(-1.4)
    assert max(item.total.value for item in standard) == pytest.approx(1.0)
    assert {item.sls_type for item in sls} == {
        "standard",
        "frequent",
        "quasi_permanent",
    }
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


def test_variable_actions_have_leading_and_accompanying_combinations() -> None:
    envelope = line_load_envelope(
        [
            LoadItem(kind=LoadKind.DEAD, value=1, unit="kN/m", source="dead"),
            LoadItem(kind=LoadKind.LIVE, value=2, unit="kN/m", source="live"),
            LoadItem(kind=LoadKind.WIND, value=3, unit="kN/m", source="wind"),
        ]
    )
    uls = [item for item in envelope.combinations if item.limit_state == "ULS"]
    assert {item.leading_action for item in uls} >= {"live", "wind", "uplift"}
    live_leading = next(item for item in uls if item.leading_action == "live")
    wind_leading = next(item for item in uls if item.leading_action == "wind")
    assert live_leading.factors["live"] == pytest.approx(1.5)
    assert live_leading.factors["wind"] == pytest.approx(0.9)
    assert wind_leading.factors["wind"] == pytest.approx(1.5)
    assert wind_leading.factors["live"] == pytest.approx(1.05)
