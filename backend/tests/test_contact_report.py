from io import BytesIO
from pypdf import PdfReader

from app.report import build_scene_analysis_snapshot_pdf


def test_snapshot_report_preserves_contact_combination_units_and_pending_checks():
    snapshot = {"analysis": {"foundation_checks": {"items": [{
        "foundation_id": "FOOTING-42", "status": "incomplete",
        "pending_checks": ["top reinforcement missing"],
        "contact_solutions": [{"combination_name": "WIND-X-42", "contact_area_m2": 1.8,
            "qmin_kpa": 0, "qmax_kpa": 111.111111, "anchor_tensions_kn": [25, 25],
            "contact_model_source": "Stiffness report A-42"},
            {"combination_name": "UPLIFT-43", "status": "incomplete", "missing_inputs": ["anchor_springs"]}],
    }]}}}
    pdf = build_scene_analysis_snapshot_pdf(snapshot, "CONTACT-42")
    content = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    for expected in ["WIND-X-42", "111.111", "kPa", "1.8", "top reinforcement missing", "Stiffness report A-42", "UPLIFT-43", "incomplete", "anchor_springs"]:
        assert expected in content
