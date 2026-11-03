"""Actual R6 lower-lip color correction, no artistic acceptance score."""
import sys,json,gzip,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_finish_r7 as finish
import mom_head_cage as model

class FinishR7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=json.loads((ROOT/'studio/authoring/mom-head-form-r7.json').read_text())
        cls.data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']

    def test_geometry_and_ears_identical_to_r6(self):
        old=json.loads((ROOT/'studio/authoring/mom-head-form-r6.json').read_text())
        for key in ('controls','brow_curve','ear_finish','portrait_smile_amount'):self.assertEqual(old[key],self.spec[key])

    def test_lower_lip_is_not_cut_off_at_r6_chart(self):
        colors,mask=finish.complexion_colors(self.data,self.spec['palette_srgb'])
        self.assertGreater(mask[3177],.6)
        self.assertGreater(mask[6343],.99)
        np.testing.assert_allclose(colors[6343,:3],finish.linear(self.spec['palette_srgb']['lower_lip']),atol=1e-7)

    def test_upper_lip_boundary_and_skin_protected(self):
        _,mask=finish.complexion_colors(self.data,self.spec['palette_srgb'])
        for index in (3156,6334,6344,6375,6374):self.assertEqual(mask[index],0)
        self.assertGreater(mask[55],.9)

    def test_color_alpha_stays_opaque_and_roughness_range(self):
        colors,mask=finish.complexion_colors(self.data,self.spec['palette_srgb'])
        np.testing.assert_array_equal(colors[:,3],np.ones(len(colors)))
        self.assertTrue(np.isfinite(colors).all())
        rough=.47-.08*mask;self.assertGreaterEqual(float(rough.min()),.39-1e-9)
        self.assertLessEqual(float(rough.max()),.47)
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])
