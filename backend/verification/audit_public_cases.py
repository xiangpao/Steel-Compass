"""Published reference values are literals transcribed before production execution."""
import json
from pathlib import Path
from app.core.space_frame import SpaceFrameModel,SpaceNode,SpaceMember,SpaceRestraint,SpaceNodalLoad,analyze_space_frame_stability


def run():
    rows=[]
    for count,expected in [(1,12.000),(2,9.944),(3,9.885),(4,9.875),(5,9.872),(6,9.871)]:
        model=SpaceFrameModel(
            tuple(SpaceNode(str(i),i*10/count,0,0) for i in range(count+1)),
            tuple(SpaceMember(str(i),str(i),str(i+1),1000,1e5,1e5,1e5,elastic_modulus_mpa=1000,shear_modulus_mpa=400) for i in range(count)),
            (SpaceRestraint("0",ux=True,uy=True,uz=True,rx=True),SpaceRestraint(str(count),uy=True,uz=True)),
            (SpaceNodalLoad(str(count),fx_kn=-0.001),))
        actual=analyze_space_frame_stability(model).buckling_factors[0]
        rows.append(dict(case=f"Tekla-Euler-{count}-elements",source="https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderbucklingeulerstrutbuckling",
            version="2026",location=f"Overall Buckling Factor, {count-1} internal nodes",method="Euler-Bernoulli elastic initial-stress eigenproblem, shear deformation excluded",
            geometry="L=10m pinned ends; one axial restraint and torsion restraint",material="EI=100 N m2; source specifies rigidity, not Chinese grade",
            loads="axial compression 1N",metric="lowest positive buckling multiplier",unit="1",reference=expected,actual=actual,
            tolerance_mode="absolute",tolerance=0.0006,tolerance_basis="published three-decimal rounding plus 0.0001 numerical allowance; registered before execution",
            error=abs(actual-expected),passed=abs(actual-expected)<=0.0006))
    model=SpaceFrameModel((SpaceNode("A",0,0,0),SpaceNode("B",10,0,0)),
        (SpaceMember("m","A","B",10000,2.5e11/206000,2.5e11/206000,1e7),),
        (SpaceRestraint("A",True,True,True,True,True,True),),(SpaceNodalLoad("B",fx_kn=-4,fy_kn=-0.045),))
    result=analyze_space_frame_stability(model).second_order
    for metric,unit,expected,actual,tolerance in [
        ("tip displacement","mm",-167.7,result.displacements["B"].uy_mm,.05),
        ("root moment magnitude","kN m",1.121,abs(result.reactions["A"].mz_kn_m),.0005)]:
        rows.append(dict(case="Tekla-second-order-cantilever",source="https://support.tekla.com/doc/tekla-structural-designer/2026/ref_2ndorderlinearsimplecantilever",
            version="2026",location="Displacements and Support reactions table, model with one element",geometry="L=10m; fixed root/free tip",
            material="EI=250000 N m2; no shear deformation",loads="axial compression 4000N; transverse force45N",metric=metric,unit=unit,
            reference=expected,actual=actual,tolerance_mode="absolute",tolerance=tolerance,tolerance_basis="half of the last published decimal after unit conversion; registered before execution",
            error=abs(actual-expected),passed=abs(actual-expected)<=tolerance))
    return {"evidence_kind":"public_reference","evidence_status":"unreviewed","verification_status":"unverified",
            "scope":"elastic mechanics only; not Chinese code capacities, commercial export, or signed engineering approval","cases":rows}


if __name__=="__main__":
    result=run()
    path=Path(__file__).resolve().parents[2]/"docs/audit-20260919/public-cases.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print({"metrics":len(result["cases"]),"all_within_registered_tolerance":all(r["passed"] for r in result["cases"])})
