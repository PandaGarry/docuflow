"""Bounded original-surface likeness corrections; same residual on all25 keys."""
import gzip,json
import numpy as np
import mom_head_cage as model
from mom_face_finish_r6 import smoothstep,group_sum
from mom_face_anatomy_r13 import nose_residual

def oral_field(p,settings):
 p=np.asarray(p,float);x,y,z=p.T;ax=abs(x);q=p.copy()
 w=(1-smoothstep(.039,.060,ax))*smoothstep(1.366,1.382,z)*(1-smoothstep(1.406,1.424,z))*smoothstep(-.070,-.120,y)
 lip=np.exp(-(x/.040)**6-((z-1.394)/.016)**6)*smoothstep(-.09,-.13,y)
 q[:,2]+=settings['lift_m']*w+(settings['vertical_scale']-1)*(z-1.3928)*lip
 q[:,2]-=settings['corner_relax_m']*smoothstep(.017,.035,ax)*lip
 q[:,1]+=settings['retreat_m']*w;q[:,0]+=(settings['horizontal_scale']-1)*x*lip
 return q

def head_residual(p,spec):
 data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source'];q=oral_field(p,spec['mouth'])
 x,y,z=np.asarray(p).T
 malar=np.exp(-((abs(x)-.060)/.029)**4-((z-1.438)/.024)**4)*smoothstep(-.065,-.115,y)
 q[:,1]-=.0013*malar
 nose,weights=nose_residual(q,data,spec['nose']);q+=nose
 # Reduce the whole naris rim and its inner wall together, not only the visible
 # front skin. Smooth spatial contraction preserves wall thickness in Y.
 x,y,z=q.T;side=np.where(x<0,-1,1);w=np.exp(-((abs(x)-.014)/.011)**6-((z-1.4215)/.0075)**6)*smoothstep(-.105,-.14,y)
 factor=spec['nose']['naris_radial_scale']-1
 q[:,0]+=factor*(x-side*.013)*w;q[:,2]+=factor*(z-1.4215)*w
 return q-np.asarray(p)

def safe_residual(blocks,delta,triangles):
 """One common residual limited against EVERY original corrective, not Basis only.

 Never disable the final orientation check. Only attenuate affected vertices;
 report the attenuation rather than claiming unmodified corrective acceptance.
 """
 blocks=np.asarray(blocks);tri=np.asarray(triangles);a=blocks[:,tri];na=np.cross(a[:,:,1]-a[:,:,0],a[:,:,2]-a[:,:,0]);area=np.einsum('kij,kij->ki',na,na);valid=area>1e-24;scale=np.ones(len(delta))
 for iteration in range(96):
  b=(blocks+delta*scale[:,None])[:,tri];nb=np.cross(b[:,:,1]-b[:,:,0],b[:,:,2]-b[:,:,0]);ratio=np.einsum('kij,kij->ki',na,nb)/np.maximum(area,1e-30);bad=valid&(ratio<.05)
  if not bad.any():break
  scale[np.unique(tri[np.any(bad,axis=0)])]*=.65
 else:raise ValueError('Joint corrective orientation limiter failed')
 return delta*scale[:,None],{'iterations':iteration,'attenuated_vertices':int((scale<1).sum()),'minimum_scale':float(scale.min()),'minimum_signed_area_ratio':float(ratio[valid].min()),'checked_blocks':len(blocks),'method':'One identical residual jointly limited against all source corrective orientations; no guard relaxed.'}

def iris_field(p,settings):
 p=np.asarray(p);q=p.copy();c=np.tile([.046632,-.0903,1.47326],(len(p),1));c[:,0]*=np.sign(p[:,0]);v=p-c;r=np.linalg.norm(v[:,[0,2]],axis=1)
 factor=settings['inner_radial_scale']+(settings['outer_radial_scale']-settings['inner_radial_scale'])*smoothstep(.009,.018,r)+(1-settings['outer_radial_scale'])*smoothstep(.018,.027,r)
 w=smoothstep(-.100,-.119,p[:,1]);q[:,0]+=v[:,0]*(factor-1)*w;q[:,2]+=v[:,2]*(factor-1)*w
 return q
