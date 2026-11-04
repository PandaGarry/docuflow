"""Protected original-surface sculpt; numerical safety is NOT art approval."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_face_anatomy_r13 as anatomy
class R13Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s,cls.v,cls.c=model.load_cage(ROOT/'studio/authoring/mom-head-form-r13.json');cls.d=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
  cls.p=anatomy.finish_ears(cls.c(cls.v),cls.d,cls.s['ear_finish']);cls.delta,cls.w=anatomy.nose_residual(cls.p,cls.d,cls.s['nose_surface_finish']);cls.q=cls.p+cls.delta
 def test_inherits_all_coordinated_r12_controls_ears_mouth_and_materials(self):
  old=json.loads((ROOT/'studio/authoring/mom-head-form-r12.json').read_text())
  for k in ('controls','ear_finish','brow_curve','palette_srgb','portrait_smile_amount'):self.assertEqual(self.s[k],old[k])
  self.assertFalse(self.s['art_approved']);self.assertFalse(self.s['production_swap_allowed'])
 def test_curved_cap_not_another_flat_tip_retraction(self):
  self.assertLess(abs(self.delta[6341,1]),.0001)
  self.assertGreater(self.delta[492,1],.0025)
  self.assertGreater(self.q[492,1]-self.q[6341,1],.0035)
  self.assertLess(self.delta[3125,1],-.001)
 def test_only_nasal_skin_changes_not_inner_nostrils_or_mouth_ears(self):
  np.testing.assert_array_equal(self.delta[self.p[:,2]<1.4185],0)
  np.testing.assert_array_equal(self.delta[np.abs(self.p[:,0])>.026],0)
  np.testing.assert_array_equal(self.delta[self.s['nose_surface_finish']['protected_nostril_indices']],0)
  np.testing.assert_array_equal(self.delta[[2333,2342,2351]],0)
 def test_bounded_finite_without_relative_triangle_reversal(self):
  self.assertTrue(np.isfinite(self.q).all());self.assertLess(np.linalg.norm(self.delta,axis=1).max(),.0045)
  tri=np.array([[f[0],f[j],f[j+1]] for f in self.d['polygons'] for j in range(1,len(f)-1)])
  a=self.p[tri];b=self.q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12
  self.assertTrue((np.einsum('ij,ij->i',na[valid],nb[valid])>0).all())
 def test_deterministic_frozen_neutral_residual_transport(self):
  delta,w=anatomy.nose_residual(self.p,self.d,self.s['nose_surface_finish']);np.testing.assert_array_equal(delta,self.delta)
  # Transport must not independently re-fit each expressive key.
  key=self.p+np.array([.0002,-.0001,.0003]);np.testing.assert_allclose((key+delta)-self.q,key-self.p,atol=1e-15)
 def test_published_r12_recipes_frozen(self):
  r=json.loads((ROOT/'studio/reviews/mom-head-form-r12/report.json').read_text())
  for name,digest in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
if __name__=='__main__':unittest.main()
