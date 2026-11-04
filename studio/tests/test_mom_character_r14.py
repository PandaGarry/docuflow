"""R14 source/safety contracts, never an artistic acceptance gate."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_face_anatomy_r14 as face
import mom_groom_r14 as groom
import mom_wardrobe_r14 as wardrobe
class R14Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.spec,cls.v,cls.c=model.load_cage(ROOT/'studio/authoring/mom-character-r14.json');cls.old=json.loads((ROOT/'studio/authoring/mom-head-form-r13.json').read_text());cls.delta=face.neutral_residual(cls.spec)
 def test_broad_proportion_pass_bound_to_original_indices(self):
  self.assertEqual(len(self.spec['controls']),87);self.assertEqual(len(self.spec['revision_deltas_from_r13_m']),36)
  self.assertEqual([c['source_vertex'] for c in self.spec['controls']],[c['source_vertex'] for c in self.old['controls']])
  self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])
 def test_cage_and_actual_r13_neutral_triangle_safety(self):
  self.assertGreater(np.linalg.det(self.c.jacobians(self.v)).min(),.05)
  d=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r13/head-edit-data.json.gz').read_bytes()));p=np.array(d['basis_vertices']);q=p+self.delta
  tri=np.array([[f[0],f[j],f[j+1]] for f in d['polygons'] for j in range(1,len(f)-1)]);a=p[tri];b=q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);ok=np.linalg.norm(na,axis=1)>1e-12
  self.assertTrue((np.einsum('ij,ij->i',na[ok],nb[ok])>0).all());self.assertLess(np.linalg.norm(self.delta,axis=1).max(),.009)
 def test_fuller_cheeks_softer_lower_oval_not_global_head_inflation(self):
  d=self.spec['revision_deltas_from_r13_m'];self.assertGreater(d['cheek-contour.L'][0],.003);self.assertLess(d['malar-front.L'][1],-.003)
  self.assertLess(d['jaw-angle.L'][0],0);self.assertGreater(d['jaw-chin-transition.L'][0],0);self.assertGreater(d['chin-tip'][2],0)
  for n in ('tip','columella','bridge-low','mouth-seam','crown'):self.assertNotIn(n,d)
 def test_more_compact_ears_brows_and_slight_eye_change(self):
  self.assertLess(self.spec['ear_finish']['scale_xyz'][0],self.old['ear_finish']['scale_xyz'][0])
  self.assertGreater(self.spec['brow_curve']['transverse_scale'],self.old['brow_curve']['transverse_scale'])
  self.assertAlmostEqual(1/self.spec['eye_finish']['iris_uv_scale'],1.08)
  p=np.array([[.046632,-.09,1.47326]]);q=face.globe(p,1.025);self.assertLess(np.linalg.norm(q-p),.001)
 def test_native_strand_source_is_bounded_deterministic_and_tapered(self):
  p,r,groups=groom.fibers(self.spec['groom']);p2,r2,_=groom.fibers(self.spec['groom']);np.testing.assert_array_equal(p,p2);np.testing.assert_array_equal(r,r2)
  self.assertEqual(p.shape,(5124,44,3));self.assertTrue(np.isfinite(p).all());self.assertTrue((r>0).all());self.assertTrue((r[:,-1]<r[:,0]).all())
  self.assertGreater(p[:,:,2].max(),1.64);self.assertLess(p[:,:,2].min(),1.20);self.assertLess(abs(p[:,:,0]).max(),.18)
  self.assertEqual(groups[-1]['name'],'fine crown flyaways')
 def test_part_and_swept_waves_no_crown_mesh_cap(self):
  for name,points,width in groom.guides():self.assertLess(abs(points[0][0]),.005);self.assertGreater(width,.01)
  text=(ROOT/'studio/tools/mom_groom_r14.py').read_text();self.assertIn('bpy.data.hair_curves.new',text);self.assertNotIn('from_pydata',text)
 def test_sleeves_are_actual_mesh_components(self):
  for side in (-1,1):
   p,f=wardrobe.sleeve(side);self.assertEqual(len(p),192);self.assertEqual(len(f),160);self.assertTrue(np.isfinite(p).all())
  self.assertEqual(self.spec['wardrobe']['vest_srgb'],'#69422E')
 def test_actual_downloaded_baseline_and_frozen_r13_scripts(self):
  r=json.loads((ROOT/'studio/reviews/mom-head-form-r13/report.json').read_text());p=json.loads((ROOT/'studio/reviews/mom-character-r14/inspection.json').read_text())
  self.assertEqual(p['downloaded_binary_sha256'],r['native_artifact']['sha256'])
  for name,digest in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
if __name__=='__main__':unittest.main()
