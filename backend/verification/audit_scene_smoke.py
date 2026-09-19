"""Run every catalog variant with declared defaults; missing inputs remain gaps."""
import json
from pathlib import Path
import runpy

from app.core.scene_catalog import SCENE_FAMILIES
from app.core.scene_graph import validate_scene_graph


if __name__ == "__main__":
    backend=Path(__file__).resolve().parents[1]
    execute=runpy.run_path(str(backend/"tests/test_milestone_scenes.py"))["_execute_public_variant"]
    rows=[]
    for family in SCENE_FAMILIES:
        for variant in family.variants:
            row={"family":family.id,"variant":variant.id,"input_basis":"catalog defaults plus explicitly confirmed reference load fixture; not engineering input"}
            try:
                row["graph_order"]=validate_scene_graph(family,variant.id)
                values={p.key:p.default for p in variant.parameters if p.default is not None}
                result=execute(family.id,variant.id,values)
                row.update(workflow=result.workflow_status,engineering_status=result.engineering_status,
                    nodes={k:{"workflow":v.workflow_status,"status":v.status,"message":v.message,
                              "warnings":[w.code for w in v.calculation_result.warnings] if v.calculation_result else []}
                           for k,v in result.node_results.items()})
            except Exception as exc:
                row.update(error_type=type(exc).__name__,error=str(exc))
            rows.append(row)
    output=backend.parent/"docs/audit-20260919/scene-smoke.json"
    output.write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    print({"variants":len(rows),"exceptions":[(r["family"],r["variant"],r.get("error")) for r in rows if "error" in r]})
