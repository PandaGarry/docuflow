"""Actual source-guided fine geometry, not artistic acceptance by strand count."""
import unittest,sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_groom_r19 as groom
class R19(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s=json.loads((ROOT/'studio/authoring/mom-character-r19.json').read_text());cls.fit=json.loads((ROOT/'studio/authoring/mom-character-r18.json').read_text())['hair_fit'];cls.p,cls.r,cls.receipt=groom.fibers(cls.fit,cls.s['fine_hair_curves'])
 def test_actual_fine_surface_hair_not_tube_geometry(self):
  self.assertEqual(self.p.shape,(16000,40,3));self.assertEqual(self.r.shape,(16000,40));self.assertTrue(np.isfinite(self.p).all());self.assertGreater(self.r.min(),0);self.assertLess(self.r.min(),.00001);self.assertLess(self.r.max(),.00007);self.assertGreater(self.receipt['actual_surface_guides'],1000);self.assertGreater(self.receipt['source_uv_islands'],20)
 def test_envelope_and_real_source_pins(self):
  self.assertLess(abs(self.p[:,:,0]).max(),.21);self.assertGreater(self.p[:,:,2].min(),1.29);self.assertLess(self.p[:,:,2].max(),1.66);self.assertEqual(hashlib.sha256((ROOT/'studio/authoring/mom-character-r18.json').read_bytes()).hexdigest(),self.s['fitting_spec_sha256']);self.assertEqual(self.receipt['source_license'],'CC0-1.0')
 def test_growth_repeatable(self):
  p,r,record=groom.fibers(self.fit,self.s['fine_hair_curves']);np.testing.assert_array_equal(p,self.p);np.testing.assert_array_equal(r,self.r);self.assertEqual(record,self.receipt)
 def test_no_art_acceptance_from_density(self):
  for k in ('art_approved','user_approved','production_swap_allowed'):self.assertFalse(self.s[k])
if __name__=='__main__':unittest.main()
