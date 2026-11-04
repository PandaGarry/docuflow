"""Surface sculpt of the ORIGINAL R12 nose: rounded guide + bounded fairing.

Not a replacement mesh. A frozen neutral residual is transported identically
across the original head keys; nostril collars and all non-nasal anatomy held.
"""
import numpy as np
from mom_face_anatomy_r12 import ear_mask,finish_ears
from mom_face_finish_r6 import smoothstep,group_sum
from mom_head_surface_r2 import vertex_normals

def nose_residual(neutral,data,settings):
    p=np.asarray(neutral,dtype=float);source=np.asarray(data['basis_vertices']);x,y,z=p.T
    normals=vertex_normals(p,data['polygons'])
    nose=group_sum(data,('DEF-NoseFront_','DEF-NoseRing_','DEF-NoseMidLine_','DEF-NoseBridge_',
                         'DEF-Nose_1.','DEF-Nose_2.','DEF-Nose_3.','DEF-Nose_4.','DEF-Nose_5.'))
    center=np.asarray(settings['guide_center_m']);radii=np.asarray(settings['guide_radii_m'])
    rho=(x/radii[0])**2+((z-center[2])/radii[2])**2
    weight=np.clip(nose,0,1)*smoothstep(-.05,-.65,normals[:,1])
    weight*=smoothstep(1.4185,1.426,z)*(1-smoothstep(1.443,1.451,z))
    weight*=1-smoothstep(.017,.026,np.abs(x))
    weight*=1-smoothstep(.85,1,rho)
    # Source nose groups also contain INNER nostril walls. Normals alone are
    # insufficient: select frontmost original skin by exact triangle rays in XZ.
    triangles=np.array([[f[0],f[j],f[j+1]] for f in data['polygons'] for j in range(1,len(f)-1)])
    t=p[triangles];t=t[(t[:,:,0].min(1)<.027)&(t[:,:,0].max(1)>-.027)&(t[:,:,2].min(1)<1.452)&(t[:,:,2].max(1)>1.418)]
    u=t[:,1]-t[:,0];v=t[:,2]-t[:,0];den=u[:,0]*v[:,2]-u[:,2]*v[:,0];valid=np.abs(den)>1e-14
    t=t[valid];u=u[valid];v=v[valid];den=den[valid]
    for i in np.flatnonzero(weight):
        offset=p[i]-t[:,0];b=(offset[:,0]*v[:,2]-offset[:,2]*v[:,0])/den
        c=(u[:,0]*offset[:,2]-u[:,2]*offset[:,0])/den;inside=(b>=-1e-7)&(c>=-1e-7)&(b+c<=1+1e-7)
        depths=t[:,0,1]+b*u[:,1]+c*v[:,1]
        front=min(p[i,1],float(depths[inside].min())) if inside.any() else p[i,1]
        weight[i]*=1-smoothstep(.0002,.0012,p[i,1]-front)
    pins=np.array(settings['protected_nostril_indices'],dtype=int)
    distance=np.linalg.norm(source[:,None]-source[pins][None],axis=2).min(axis=1)
    weight*=smoothstep(.003,.006,distance)
    target=center[1]-radii[1]*np.sqrt(np.maximum(0,1-rho))
    q=p.copy();limit=settings['maximum_guide_step_m'];q[:,1]+=np.clip(target-y,-limit,limit)*weight
    edges=set()
    for face in data['polygons']:
        for a,b in zip(face,face[1:]+face[:1]):edges.add(tuple(sorted((a,b))))
    edges=np.array(sorted(edges));a,b=edges.T;degree=np.bincount(edges.ravel(),minlength=len(p))
    def laplace(v):
        sums=np.zeros_like(v);np.add.at(sums,a,v[b]);np.add.at(sums,b,v[a])
        return sums/np.maximum(degree,1)[:,None]-v
    for _ in range(settings['fairing_cycles']):
        for coefficient in (.35,-.36):q+=coefficient*weight[:,None]*laplace(q)
    delta=q-p
    # Local orientation limiter, not a likeness metric. Do not pull a tiny
    # nostril-rim triangle through its held neighbour to fit the dome guide.
    original=p[triangles];n0=np.cross(original[:,1]-original[:,0],original[:,2]-original[:,0])
    area2=np.einsum('ij,ij->i',n0,n0);valid=area2>1e-24;scale=np.ones(len(p))
    for _ in range(64):
        changed=(p+delta*scale[:,None])[triangles]
        n1=np.cross(changed[:,1]-changed[:,0],changed[:,2]-changed[:,0])
        bad=valid&(np.einsum('ij,ij->i',n0,n1)<.1*area2)
        if not bad.any():break
        scale[np.unique(triangles[bad])]*=.5
    else:raise ValueError('Nasal orientation limiter failed')
    delta*=scale[:,None]
    if not np.isfinite(delta).all() or np.linalg.norm(delta,axis=1).max()>.0045:raise ValueError('Unbounded nasal surface sculpt')
    if np.any(delta[pins]!=0):raise ValueError('Nostril collar moved')
    return delta,weight
