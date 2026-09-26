"""Rigid rectangle / uniform compression-only Winkler bed, optionally tension anchors.

Units: m, kN, kPa. Compression N positive; Mx=integral(y*q), My=integral(x*q).
The pressure plane is clipped geometrically and integrated exactly (degree two),
not sampled or truncated after a full-contact solve. No capacity/code rules here.
"""
from dataclasses import dataclass
from math import isfinite
from typing import Any
import numpy as np


class ContactError(ValueError):
    """No finite stable equilibrium, invalid input, or non-convergence."""


def _clip(poly, a, b, c):
    out = []
    if not poly:
        return out
    prev = poly[-1]
    fp = a + b * prev[0] + c * prev[1]
    for cur in poly:
        fc = a + b * cur[0] + c * cur[1]
        if (fp >= 0) != (fc >= 0):
            t = fp / (fp-fc)
            out.append((prev[0]+t*(cur[0]-prev[0]),prev[1]+t*(cur[1]-prev[1])))
        if fc >= 0:
            out.append(cur)
        prev,fp=cur,fc
    return out


def _matrix(poly):
    """Integral outer([1,u,v],[1,u,v]) by exact triangle degree-2 rule."""
    mat=np.zeros((3,3))
    if len(poly)<3:
        return mat
    p=np.array(poly[0])
    for i in range(1,len(poly)-1):
        q,r=np.array(poly[i]),np.array(poly[i+1])
        area=abs((q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]))/2
        for point in ((p+q)/2,(q+r)/2,(r+p)/2):
            v=np.array([1,*point])
            mat+=area/3*np.outer(v,v)
    return mat


@dataclass
class ContactSolution:
    length_m: float
    width_m: float
    coefficients_kpa: list[float]  # q=a+b*(2x/L)+c*(2y/B)
    polygon_m: list[tuple[float,float]]
    area_m2: float
    qmin_kpa: float
    qmax_kpa: float
    anchor_springs: list[dict[str,float]]
    anchor_tensions_kn: list[float]
    residual_kn: list[float]  # [N, My/(L/2), Mx/(B/2)] residual
    iterations: int

    def pressure_plane(self,x_m,y_m):
        a,b,c=self.coefficients_kpa
        return a+b*2*x_m/self.length_m+c*2*y_m/self.width_m

    def integrate(self, bounds=None):
        """Return (force, first moment x, first moment y) on clipped rectangle."""
        poly=[(x*2/self.length_m,y*2/self.width_m) for x,y in self.polygon_m]
        if bounds is not None:
            x0,x1,y0,y1=bounds
            for halfplane in [(-2*x0/self.length_m,1,0),(2*x1/self.length_m,-1,0),(-2*y0/self.width_m,0,1),(2*y1/self.width_m,0,-1)]:
                poly=_clip(poly,*halfplane)
        values=_matrix(poly)@np.array(self.coefficients_kpa)*(self.length_m*self.width_m/4)
        return float(values[0]),float(values[1]*self.length_m/2),float(values[2]*self.width_m/2)

    def resultants(self):
        n,my,mx=self.integrate()
        for a,t in zip(self.anchor_springs,self.anchor_tensions_kn):
            n-=t
            my-=t*a['x_m']
            mx-=t*a['y_m']
        return n,mx,my

    def as_dict(self) -> dict[str,Any]:
        return {
            'model':'rigid_uniform_compression_only_bed_v1',
            'verification_status':'unverified',
            'pressure_coefficients_kpa':self.coefficients_kpa,
            'pressure_equation':'max(a+b*2*x/L+c*2*y/B,0)',
            'contact_polygon_m':self.polygon_m,
            'contact_area_m2':self.area_m2,
            'qmin_kpa':self.qmin_kpa,'qmax_kpa':self.qmax_kpa,
            'resultants_n_mx_my':list(self.resultants()),
            'scaled_equilibrium_residual_kn':self.residual_kn,
            'anchor_tensions_kn':self.anchor_tensions_kn,
            'anchor_springs':self.anchor_springs,
            'iterations':self.iterations,
        }


def solve_rectangular_contact(length_m,width_m,n_kn,mx_kn_m,my_kn_m,*,contact_stiffness_kn_m3=None,anchor_springs=None):
    vals=[length_m,width_m,n_kn,mx_kn_m,my_kn_m]
    if not all(isfinite(v) for v in vals) or min(length_m,width_m)<=0:
        raise ContactError('nonfinite or nonpositive geometry')
    anchors=anchor_springs or []
    if anchors and (contact_stiffness_kn_m3 is None or not isfinite(contact_stiffness_kn_m3) or contact_stiffness_kn_m3<=0):
        raise ContactError('explicit positive contact stiffness required with anchors')
    for a in anchors:
        if not all(isfinite(a[k]) for k in ('x_m','y_m','stiffness_kn_m')) or a['stiffness_kn_m']<=0 or abs(a['x_m'])>length_m/2 or abs(a['y_m'])>width_m/2:
            raise ContactError('invalid anchor coordinates or stiffness')
    if not anchors and (n_kn<=0 or abs(my_kn_m)>=n_kn*length_m/2 or abs(mx_kn_m)>=n_kn*width_m/2):
        raise ContactError('resultant outside open compression support polygon')
    rect=[(-1,-1),(1,-1),(1,1),(-1,1)]
    jac=length_m*width_m/4
    target=np.array([n_kn,2*my_kn_m/length_m,2*mx_kn_m/width_m])
    full=_matrix(rect)*jac
    vectors=[np.array([1,2*a['x_m']/length_m,2*a['y_m']/width_m]) for a in anchors]
    ratios=[a['stiffness_kn_m']/contact_stiffness_kn_m3 for a in anchors]

    def evaluate(v):
        poly=_clip(rect,*v)
        mat=_matrix(poly)*jac
        force=mat@v
        energy=float(v@force/2-target@v)
        tangent=mat.copy()
        tensions=[]
        for b,k in zip(vectors,ratios):
            value=float(b@v)
            tension=k*max(-value,0)
            tensions.append(tension)
            force-=tension*b
            energy+=k*min(value,0)**2/2
            if value<0:
                tangent+=k*np.outer(b,b)
        return force-target,tangent,energy,poly,tensions

    v=np.linalg.solve(full,target)
    tol=1e-10*max(float(np.max(np.abs(target))),1)
    for iteration in range(100):
        residual,tangent,energy,poly,tensions=evaluate(v)
        if np.max(np.abs(residual))<=tol:
            eigenvalues = np.linalg.eigvalsh(tangent)
            if eigenvalues[-1] <= 0 or eigenvalues[0] <= eigenvalues[-1] * 1e-12:
                raise ContactError('singular active support; equilibrium leaves a free rigid-body rotation')
            break
        try:
            step=np.linalg.solve(tangent,-residual)
        except np.linalg.LinAlgError as exc:
            raise ContactError('singular active support; no stable equilibrium') from exc
        alpha=1.0
        for _ in range(50):
            candidate=v+alpha*step
            r2,_,e2,_,_=evaluate(candidate)
            if np.max(np.abs(r2))<=tol or e2<=energy+1e-4*alpha*float(residual@step)+1e-13*max(abs(energy),1):
                v=candidate
                break
            alpha*=.5
        else:
            raise ContactError('contact line search failed')
    else:
        raise ContactError('contact equilibrium did not converge')
    corners=[max(float(v@np.array([1,*p])),0) for p in rect]
    return ContactSolution(length_m,width_m,v.tolist(),[(x*length_m/2,y*width_m/2) for x,y in poly],float(_matrix(poly)[0,0]*jac),min(corners),max(corners),anchors,tensions,residual.tolist(),iteration+1)

def anchor_shear_distribution(anchor_springs, vx_kn, vy_kn, torsion_kn_m):
    """Rigid plate, all anchors engaged in shear, equal shear stiffness, no slip.

    Coordinates need not be symmetric; torque is shifted to the anchor centroid.
    This does not infer shear stiffness from the supplied axial spring stiffness.
    """
    if not anchor_springs:
        raise ContactError('anchor coordinates required for torsional shear')
    count = len(anchor_springs)
    xc = sum(a['x_m'] for a in anchor_springs) / count
    yc = sum(a['y_m'] for a in anchor_springs) / count
    polar = sum((a['x_m']-xc)**2+(a['y_m']-yc)**2 for a in anchor_springs)
    torque = torsion_kn_m - xc*vy_kn + yc*vx_kn
    if polar <= 1e-18:
        raise ContactError('degenerate anchor shear group')
    return [(vx_kn/count-torque*(a['y_m']-yc)/polar,
             vy_kn/count+torque*(a['x_m']-xc)/polar) for a in anchor_springs]


def rectangular_weld_peak_line_force(depth_mm, width_mm, n_kn, vx_kn, vy_kn, mx_kn_m, my_kn_m, torsion_kn_m):
    """Continuous full-perimeter equal-throat elastic line weld group, N/mm.

    Normal and shear line forces are combined vectorially; no directional weld
    strength enhancement is assumed. Capacity is outside this mechanics helper.
    """
    from math import sqrt
    length = 2*(depth_mm+width_mm)
    ix = 2*depth_mm*(width_mm/2)**2 + width_mm**3/6
    iy = 2*width_mm*(depth_mm/2)**2 + depth_mm**3/6
    polar = ix+iy
    peaks=[]
    for x in (-depth_mm/2,depth_mm/2):
        for y in (-width_mm/2,width_mm/2):
            normal = n_kn*1000/length + mx_kn_m*1e6*y/ix + my_kn_m*1e6*x/iy
            sx = vx_kn*1000/length - torsion_kn_m*1e6*y/polar
            sy = vy_kn*1000/length + torsion_kn_m*1e6*x/polar
            peaks.append(sqrt(normal**2+sx**2+sy**2))
    return max(peaks)
