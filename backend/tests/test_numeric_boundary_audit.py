import pytest
from app.core.engine import calculate
from app.core.errors import CalculationInputError
from app.core.schemas import CalculationModule,CalculationRequest


@pytest.mark.parametrize("module",list(CalculationModule))
def test_no_module_accepts_nonfinite_legacy_numeric_input(module):
    with pytest.raises(CalculationInputError) as error:
        calculate(CalculationRequest(mode="quick",module=module,inputs={"h_mm":float("nan")}))
    assert error.value.code == "nonfinite_calculation_input"
