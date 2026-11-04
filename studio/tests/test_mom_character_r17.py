"""Geometry/provenance checks, explicitly NOT a likeness/art approval."""
import unittest,sys,json,gzip
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_anatomy_r17 as face
import mom_groom_r17 as hair
import mom_hair_contours_r17 as contours
class R17(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s=json.loads((ROOT/'studio/authoring/mom-character-r17.json').read_text());cls.d=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r16/head-edit-data.json.gz').read_bytes()));cls.p=np.array(cls.d['basis_vertices'])
 def test_original_surface_orientation(self):
  p=self.p;q=p+face.head_residual(p,self.s);tri=np.array([[f[0],f[j],f[j+1]] for f in self.d['polygons'] for j in range(1,len(f)-1)]);a=p[tri];b=q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12;self.assertTrue((np.einsum('ij,ij->i',na[valid],nb[valid])>0).all());self.assertLess(np.linalg.norm(q-p,axis=1).max(),.006)
 def test_oral_lift_not_whole_head_translation(self):
  delta=face.oral_field(self.p,self.s['mouth'])-self.p;self.assertGreater(delta[3150,2],.004);self.assertLess(np.linalg.norm(delta[self.p[:,2]>1.5],axis=1).max(),1e-10)
 def test_new_hair_is_separate_volumetric_flows(self):
  guides=hair.guides(self.s['hair'])[len(hair.FRONT):];self.assertEqual(len(guides),11)
  for i,(_,path,w,d) in enumerate(guides):
   verts,faces,uv,_=hair.lock_geometry(path,w,d,i);v=np.array(verts);self.assertTrue(np.isfinite(v).all());self.assertEqual(len(uv),sum(map(len,faces)));edges={}
   for f in faces:
    for a,b in zip(f,f[1:]+f[:1]):edge=tuple(sorted((a,b)));edges[edge]=edges.get(edge,0)+1
   self.assertTrue(all(n==2 for n in edges.values()))
 def test_actual_front_tresses_are_closed_and_outward(self):
  flows=contours.tress_paths(self.s['hair']);self.assertEqual(len(flows),25)
  for _,path,radius in flows:
   p,faces,uv,_=contours.tube(path,radius);self.assertTrue(np.isfinite(p).all());self.assertEqual(len(p),3072);self.assertEqual(len(uv),sum(map(len,faces)));edges={}
   for f in faces:
    for a,b in zip(f,f[1:]+f[:1]):key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
   self.assertTrue(all(v==2 for v in edges.values()));f=faces[64*24+6];a,b,c=p[list(f[:3])];self.assertLess(np.cross(b-a,c-a)[1],0)
 def test_spatial_oral_transport_has_positive_local_jacobian(self):
  x,y,z=np.meshgrid(np.linspace(-.07,.07,15),np.linspace(-.17,-.065,9),np.linspace(1.36,1.43,23));p=np.stack((x.ravel(),y.ravel(),z.ravel()),axis=1);h=1e-6;columns=[]
  for axis in range(3):
   v=np.zeros(3);v[axis]=h;columns.append((face.oral_field(p+v,self.s['mouth'])-face.oral_field(p-v,self.s['mouth']))/(2*h))
  jac=np.stack(columns,axis=2);self.assertGreater(np.linalg.det(jac).min(),.35)
 def test_original_eye_depth_is_held(self):
  inspection=json.loads((ROOT/'studio/reviews/mom-character-r14/inspection.json').read_text());p=np.array(next(o for o in inspection['objects'] if o['name']=='GEO-rain-eyes')['basis_vertices']);q=face.iris_field(p,self.s['iris']);np.testing.assert_array_equal(p[:,1],q[:,1]);self.assertTrue(np.isfinite(q).all())
 def test_no_automatic_art_approval(self):
  self.assertFalse(self.s['art_approved']);self.assertFalse(self.s['production_swap_allowed'])
if __name__=='__main__':unittest.main()
