import json

from verification import audit_public_cases


def test_public_evidence_command_fails_when_any_registered_metric_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_public_cases, "run", lambda: {"cases": [{"passed": False}]})
    destination = tmp_path / "evidence.json"
    assert audit_public_cases.main(["--output", str(destination)]) == 1
    assert json.loads(destination.read_text())["cases"][0]["passed"] is False


def test_public_evidence_command_requires_explicit_output(tmp_path, monkeypatch):
    import pytest
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        audit_public_cases.main([])
    assert list(tmp_path.iterdir()) == []
