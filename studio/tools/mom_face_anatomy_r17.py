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
 return q-np.asarray(p)

def iris_field(p,settings):
 p=np.asarray(p);q=p.copy();c=np.tile([.046632,-.0903,1.47326],(len(p),1));c[:,0]*=np.sign(p[:,0]);v=p-c;r=np.linalg.norm(v[:,[0,2]],axis=1)
 factor=settings['inner_radial_scale']+(settings['outer_radial_scale']-settings['inner_radial_scale'])*smoothstep(.009,.018,r)+(1-settings['outer_radial_scale'])*smoothstep(.018,.027,r)
 w=smoothstep(-.100,-.119,p[:,1]);q[:,0]+=v[:,0]*(factor-1)*w;q[:,2]+=v[:,2]*(factor-1)*w
 return q
