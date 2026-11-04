"""Geometry/provenance checks, explicitly NOT a likeness/art approval."""
import unittest,sys,json,gzip
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_anatomy_r17 as face
import mom_groom_r17 as hair
class R17(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s=json.loads((ROOT/'studio/authoring/mom-character-r17.json').read_text());cls.d=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r16/head-edit-data.json.gz').read_bytes()));cls.p=np.array(cls.d['basis_vertices'])
 def test_original_surface_orientation(self):
  p=self.p;q=p+face.head_residual(p,self.s);tri=np.array([[f[0],f[j],f[j+1]] for f in self.d['polygons'] for j in range(1,len(f)-1)]);a=p[tri];b=q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12;self.assertTrue((np.einsum('ij,ij->i',na[valid],nb[valid])>0).all());self.assertLess(np.linalg.norm(q-p,axis=1).max(),.006)
 def test_oral_lift_not_whole_head_translation(self):
  delta=face.oral_field(self.p,self.s['mouth'])-self.p;self.assertGreater(delta[3150,2],.004);self.assertLess(np.linalg.norm(delta[self.p[:,2]>1.5],axis=1).max(),1e-10)
 def test_new_hair_is_separate_volumetric_flows(self):
  guides=hair.guides(self.s['hair']);self.assertEqual(len(guides),17)
  for i,(_,path,w,d) in enumerate(guides):
   verts,faces,uv,_=hair.lock_geometry(path,w,d,i);v=np.array(verts);self.assertTrue(np.isfinite(v).all());self.assertEqual(len(uv),sum(map(len,faces)));edges={}
   for f in faces:
    for a,b in zip(f,f[1:]+f[:1]):edge=tuple(sorted((a,b)));edges[edge]=edges.get(edge,0)+1
   self.assertTrue(all(n==2 for n in edges.values()))
 def test_no_automatic_art_approval(self):
  self.assertFalse(self.s['art_approved']);self.assertFalse(self.s['production_swap_allowed'])
if __name__=='__main__':unittest.main()
