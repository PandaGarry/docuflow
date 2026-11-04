"""Local response to inspected R8 upper-lip weight, not a likeness score."""
import json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_paint_r8 as old_paint
import mom_face_paint_r9 as paint
import mom_head_cage as model

class FacePaintR9Tests(unittest.TestCase):
    def test_four_lip_targets_only_preserve_found_nose_cheeks_eyes_ears(self):
        old=json.loads((ROOT/'studio/authoring/mom-head-form-r8.json').read_text())
        new=json.loads((ROOT/'studio/authoring/mom-head-form-r9.json').read_text())
        changed=[a['name'] for a,b in zip(old['controls'],new['controls']) if a!=b]
        self.assertEqual(set(changed),{'cupid-peak.L','cupid-peak.R','upper-lip-center','upper-lip-border'})
        for key in ('brow_curve','ear_finish','portrait_smile_amount'):self.assertEqual(old[key],new[key])
        self.assertFalse(new['art_approved']);self.assertFalse(new['production_swap_allowed'])

    def test_upper_pigment_thinner_lower_pigment_retained(self):
        palette=json.loads((ROOT/'studio/authoring/mom-head-form-r9.json').read_text())['palette_srgb']
        p=np.array([[0,-.16,1.402],[0,-.16,1.3815]])
        _,old=old_paint.paint_samples(p,np.array([1,0]),np.array([0,1]),palette)
        color,new=paint.paint_samples(p,np.array([1,0]),np.array([0,1]),palette)
        self.assertGreater(new[0,0],old[0,0])
        np.testing.assert_allclose(color[1,:3],paint.linear(palette['lower_lip']),atol=1e-7)
        self.assertAlmostEqual(float(new[1,0]),.34,places=6)

    def test_local_cage_safe_and_limited_not_another_reset(self):
        _,v,a=model.load_cage(ROOT/'studio/authoring/mom-head-form-r8.json')
        _,_,b=model.load_cage(ROOT/'studio/authoring/mom-head-form-r9.json')
        self.assertGreater(float(np.linalg.det(b.jacobians(v)).min()),.3)
        self.assertLess(float(np.linalg.norm(a(v)-b(v),axis=1).max()),.0016)

if __name__=='__main__':unittest.main()
