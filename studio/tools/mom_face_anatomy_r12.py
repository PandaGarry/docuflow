"""R12 anatomical ear adduction on original indexed mesh/key coordinates.

Frozen source weights and a wider lateral transition protect the central face.
Same bilateral affine field on every head key; not final ear-rest rig migration.
"""
import numpy as np
from mom_face_finish_r6 import smoothstep,group_sum

def ear_mask(data):
    p=np.asarray(data['basis_vertices']);ear=group_sum(data,('DEF-Ear_',))
    return np.clip(ear,0,1)*smoothstep(.087,.124,np.abs(p[:,0]))

def finish_ears(points,data,settings):
    p=np.asarray(points,dtype=float);source=np.asarray(data['basis_vertices']);w=ear_mask(data)
    signs=np.sign(source[:,0]);pivot=np.tile(np.asarray(settings['pivot_m'],dtype=float),(len(p),1));pivot[:,0]*=signs
    local=p-pivot;angle=np.deg2rad(settings['adduction_degrees'])*signs
    c=np.cos(angle);s=np.sin(angle)
    rotated=local.copy();rotated[:,0]=c*local[:,0]-s*local[:,1];rotated[:,1]=s*local[:,0]+c*local[:,1]
    changed=pivot+rotated*np.asarray(settings['scale_xyz'])
    changed[:,0]-=signs*settings['lateral_tuck_m'];changed[:,1]+=settings['posterior_tuck_m']
    return p+w[:,None]*(changed-p)
