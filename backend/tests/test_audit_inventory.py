from verification.audit_inventory import build_inventory
from app.core.scene_catalog import SCENE_FAMILIES
from test_milestone_scenes import _execute_public_variant
import pytest


def test_all_modules_and_scene_variants_have_consistent_registry_links():
    inventory=build_inventory()
    assert (inventory["module_count"], inventory["family_count"], inventory["variant_count"]) == (33,10,40)
    assert all(m["tests"] for m in inventory["modules"])
    assert all(m["verification_status"] == "unverified" for m in inventory["modules"])


@pytest.mark.parametrize("family,variant", [(f,v) for f in SCENE_FAMILIES for v in f.variants],
                         ids=[f"{f.id}/{v.id}" for f in SCENE_FAMILIES for v in f.variants])
def test_every_variant_reports_results_or_explicit_input_gaps(family,variant):
    result = _execute_public_variant(family.id,variant.id,
        {p.key:p.default for p in variant.parameters if p.default is not None})
    assert result.engineering_status in (None,"incomplete")
    assert result.verification_status == "unverified"
    for node in result.node_results.values():
        if node.calculation_result is None and node.applicability == "required":
            assert node.status in ("incomplete","not_applicable","completed")
