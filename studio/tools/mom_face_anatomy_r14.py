"""Original-index R13→R14 neutral proportion residual; no replacement head."""
import gzip,json
import numpy as np
import mom_head_cage as model
from mom_face_anatomy_r12 import finish_ears
from mom_face_finish_r6 import smoothstep
ROOT=model.ROOT

def neutral_residual(spec):
 old,v,c0=model.load_cage(ROOT/'studio/authoring/mom-head-form-r13.json');_,_,c1=model.load_cage(ROOT/'studio/authoring/mom-character-r14.json')
 data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
 return finish_ears(c1(v),data,spec['ear_finish'])-finish_ears(c0(v),data,old['ear_finish'])

def aperture(points):
 p=np.asarray(points);q=p.copy();x,y,z=p.T
 w=np.exp(-((np.abs(x)-.0525)/.039)**6-((z-1.474)/.026)**6)*smoothstep(-.06,-.105,y)
 q[:,0]+=np.sign(x)*(np.abs(x)-.0525)*.025*w;q[:,2]+=(z-1.472)*.05*w
 return q

def globe(points,scale):
 p=np.asarray(points);center=np.tile([.046632,-.0903,1.47326],(len(p),1));center[:,0]*=np.sign(p[:,0])
 return center+(p-center)*scale
