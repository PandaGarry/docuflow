"""Corrections of observed rejected R14 faults; NOT visual acceptance."""
import hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_anatomy_r15 as face
import mom_groom_r15 as groom
class R15Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.s=json.loads((ROOT/'studio/authoring/mom-character-r15.json').read_text())
 def test_retains_coordinated_face_targets(self):
  old=json.loads((ROOT/'studio/authoring/mom-character-r14.json').read_text())
  for k in ('controls','ear_finish','brow_curve'):self.assertEqual(self.s[k],old[k])
 def test_actual_frozen_failed_attempt_preserved(self):
  r=json.loads((ROOT/'studio/reviews/mom-character-r14/attempt-review.json').read_text())
  for n,d in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/n).read_bytes()).hexdigest(),d)
  self.assertFalse(r['art_approved']);self.assertIn('failed',r['status'])
 def test_iris_radial_only_no_depth_change_and_outer_globe_held(self):
  p=np.array([[.055,-.122,1.47326],[.080,-.08,1.48]]);q=face.iris_radial(p,1.08)
  np.testing.assert_array_equal(q[:,1],p[:,1]);np.testing.assert_array_equal(q[1],p[1]);self.assertGreater(q[0,0],p[0,0])
  self.assertEqual(self.s['eye_finish']['globe_scale'],1);self.assertEqual(self.s['eye_finish']['iris_uv_scale'],1)
 def test_denser_shoulder_length_groom_no_solid_cap(self):
  p,r,groups=groom.fibers(self.s['groom']);self.assertEqual(len(p),13864);self.assertGreater(p[:,:,2].min(),1.25);self.assertLess(p[:,:,2].min(),1.28)
  self.assertTrue(np.isfinite(p).all());self.assertTrue((r[:,-1]<r[:,0]).all());self.assertIn("hair.parametrization='MELANIN'",(ROOT/'studio/tools/mom_groom_r15.py').read_text())
 def test_only_changed_act_controls_restored_before_full_renders(self):
  text=(ROOT/'studio/tools/mom_character_r15.py').read_text();self.assertNotIn('controls.restore(bpy,rig,matrices)',text)
  self.assertIn("check_smile_roundtrip(bpy,rig,'clothed')",text);self.assertIn('pre-render-integrity.json',text)
 def test_outward_vest_offset_and_connected_sleeves(self):
  text=(ROOT/'studio/tools/mom_wardrobe_r15.py').read_text();self.assertIn('vest=p+normal*.014',text);self.assertIn('x=side*(.100+.126*t)',text);self.assertIn('matching body skin',text)
if __name__=='__main__':unittest.main()
