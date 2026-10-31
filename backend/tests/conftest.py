import pytest

from app.core import pergola_analysis


@pytest.fixture(autouse=True)
def serial_pergola_analysis(monkeypatch):
    # Tests monkeypatch solver functions in this process; worker processes
    # would not see those patches. test_parallel_analysis opts back in.
    monkeypatch.setattr(pergola_analysis, "_analysis_workers", lambda: 1)
