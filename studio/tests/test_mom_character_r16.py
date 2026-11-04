"""Appearance-only source contracts; native/visual result tested separately."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_groom_r16 as groom
class R16Tests(unittest.TestCase):
 def test_roots_attach_to_actual_retained_scalp(self):
  for name,points,width in groom.guides():
   x,y,z=points[0];self.assertAlmostEqual(z,groom.scalp_z(x,y)+.0003,places=10)
  self.assertGreater(groom.scalp_z(.003,-.038),1.60)
 def test_dense_finite_groom_and_no_single_point_tip_jump(self):
  s=json.loads((ROOT/'studio/authoring/mom-character-r16.json').read_text());p,r,g=groom.fibers(s['groom']);self.assertEqual(p.shape,(13864,44,3));self.assertTrue(np.isfinite(p).all());self.assertTrue((r[:,-1]<r[:,0]).all())
  text=(ROOT/'studio/tools/mom_groom_r16.py').read_text();self.assertIn('p[:,2]+=rng.uniform(-.008,.008)*t**4',text);self.assertNotIn('p[-1,2]+=',text)
 def test_actual_face_not_rebuilt_and_failed_versions_frozen(self):
  text=(ROOT/'studio/tools/mom_character_r16.py').read_text();self.assertIn('head_edits_this_revision',text);self.assertNotIn('edit_blocks(',text);self.assertIn('eye_before!=build.eye_fingerprints',text)
  for rev in (13,15):
   folder='mom-head-form-r13' if rev==13 else 'mom-character-r15';r=json.loads((ROOT/f'studio/reviews/{folder}/report.json').read_text())
   for n,d in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/n).read_bytes()).hexdigest(),d)
 def test_collar_flatter_and_jagged_piping_removed(self):
  text=(ROOT/'studio/tools/mom_wardrobe_r16.py').read_text();self.assertIn('keep=[list(reversed(f)) for f in keep]',text);self.assertIn('point[1]-=.002',text);self.assertNotIn("curve.bevel_depth=.0006",text)
if __name__=='__main__':unittest.main()
