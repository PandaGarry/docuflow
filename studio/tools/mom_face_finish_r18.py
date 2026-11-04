"""Bounded broad nasal/cheek fairing; no replacement surface or hard rim pins."""
import numpy as np
from mom_face_finish_r7 import smoothstep

def fair(p,polygons,settings):
 p=np.asarray(p);q=p.copy();x,y,z=p.T;w=np.exp(-(x/.060)**4-((z-1.438)/.034)**4)*smoothstep(-.095,-.135,y)
 edges=set()
 for face in polygons:
  for a,b in zip(face,face[1:]+face[:1]):edges.add(tuple(sorted((a,b))))
 e=np.array(sorted(edges));a,b=e.T;degree=np.bincount(e.ravel(),minlength=len(p))
 for _ in range(settings['cycles']):
  for c in (.45,-.46):
   total=np.zeros(len(p));np.add.at(total,a,q[b,1]);np.add.at(total,b,q[a,1]);q[:,1]+=c*w*(total/np.maximum(degree,1)-q[:,1])
 q[:,1]-=settings['ala_roundness_m']*np.exp(-((abs(x)-.014)/.012)**4-((z-1.430)/.010)**4)*smoothstep(-.10,-.14,y)
 d=q-p;limit=settings['maximum_delta_m'];d[:,1]=limit*np.tanh(d[:,1]/limit)
 tri=np.array([[f[0],f[j],f[j+1]] for f in polygons for j in range(1,len(f)-1)]);a=p[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12
 for _ in range(16):
  b=(p+d)[tri];nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0])
  if (np.einsum('ij,ij->i',na[valid],nb[valid])>0).all():return p+d
  d*=.5
 raise ValueError('Surface fairing did not retain original corrective orientation')
