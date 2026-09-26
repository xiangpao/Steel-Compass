import json
from pathlib import Path

import pytest

from app.core.contact import solve_rectangular_contact


def test_dlubal_2041_pressure_matches_published_metric_with_fixed_units():
    data = json.loads((Path(__file__).parents[1] / "verification/completion_reference_values.json").read_text())
    case = data["case"]
    ft_m, kip_kn = .3048, 4.4482216152605
    result = solve_rectangular_contact(
        case["geometry"]["length_ft"] * ft_m,
        case["geometry"]["width_ft"] * ft_m,
        case["loads"]["n_kip"] * kip_kn,
        case["loads"]["mx_kipft"] * kip_kn * ft_m,
        case["loads"]["my_kipft"] * kip_kn * ft_m,
    )
    actual = {"qmin": result.qmin_kpa * ft_m**2 / kip_kn,
              "qmax": result.qmax_kpa * ft_m**2 / kip_kn}
    for metric in case["metrics"]:
        assert actual[metric["metric"]] == pytest.approx(metric["reference"], abs=metric["absolute_tolerance"])
