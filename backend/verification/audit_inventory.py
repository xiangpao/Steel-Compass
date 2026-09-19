"""Reproducible inventory; coverage links are discovery aids, not proof of correctness."""
from pathlib import Path
import inspect
import json
import re

from app.core import engine
from app.core.scene_catalog import SCENE_FAMILIES, instantiate_scene_graph
from app.core.schemas import CalculationModule


def build_inventory():
    backend = Path(__file__).resolve().parents[1]
    text = inspect.getsource(engine)
    handlers = dict(re.findall(r"CalculationModule\.(\w+): (\w+)", text))
    tests = {p.name: p.read_text(encoding="utf-8") for p in (backend / "tests").glob("test_*.py")}
    refs = {p.name: p.read_text(encoding="utf-8") for p in (backend / "verification").glob("*references.py")}
    groups = {
        "steel_timber": {"steel_beam","steel_column","portal_frame","steel_baseplate_anchor","steel_cantilever_post","timber_beam","timber_column","timber_deck_panel"},
        "rc_geotech": {"concrete_beam","concrete_slab","concrete_column","masonry_wall","rc_wall","spread_footing","strip_footing","retaining_wall"},
        "geotech_infrastructure": {"gravity_retaining_wall","pool_structure","pile_group_cap"},
    }
    modules = []
    for module in CalculationModule:
        handler = getattr(engine, handlers[module.name])
        modules.append(dict(module=module.value, handler=f"{handler.__module__}.{handler.__name__}",
            implementation=inspect.getsourcefile(handler).replace("\\", "/").split("/backend/")[-1],
            input_model="CalculationRequest / typed_inputs for nextgen", api="POST /api/v2/calculate",
            storage="ProjectVersion / ProjectRevision immutable snapshot", report="app/report.py",
            tests=[p for p,t in tests.items() if module.value in t or module.name in t],
            independent_reference_files=sorted(set([p for p,t in refs.items() if module.value in t]
                + [f"{group}_references.py" for group, members in groups.items() if module.value in members])),
            evidence_registers=[f"{group.upper()}_EVIDENCE.md" for group,members in groups.items() if module.value in members],
            external_same_model_comparison="not_completed",
            verification_status=engine.MODULE_VERIFICATION[module],
            remaining_evidence=["Chinese-standard clause and applicability review", "independent signed review", "applicable external same-model comparison"],
        ))
    variants=[]
    for family in SCENE_FAMILIES:
        for variant in family.variants:
            graph=instantiate_scene_graph(family,variant.id)
            ids={n.id for n in graph.nodes}
            assert len(ids)==len(graph.nodes)
            assert all(e.source_node_id in ids and e.target_node_id in ids for e in graph.connections)
            variants.append(dict(family=family.id, variant=variant.id, availability=variant.availability,
                nodes=[dict(id=n.id,module=n.calculation_module,applicability=n.applicability) for n in graph.nodes],
                connections=[e.model_dump(mode="json") for e in graph.connections],
                capability_gaps=variant.missing_capabilities,
                external_full_chain_verified=False, signed_review=False))
    return dict(module_count=len(modules),family_count=len(SCENE_FAMILIES),variant_count=len(variants),
        modules=modules,variants=variants)


if __name__ == "__main__":
    destination=Path(__file__).resolve().parents[2]/"docs"/"audit-20260919"
    destination.mkdir(parents=True,exist_ok=True)
    inventory=build_inventory()
    (destination/"inventory.json").write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print({k:v for k,v in inventory.items() if k.endswith("count")})
