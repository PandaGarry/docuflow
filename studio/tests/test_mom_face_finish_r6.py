"""R6 corrects actual R5 lip pigment overspill, not a visual quality score."""
import gzip
import hashlib
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_finish_r5 as prior
import mom_face_finish_r6 as finish
import mom_head_cage as model


class FaceFinishR6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec,cls.vertices,cls.cage=model.load_cage(ROOT/'studio/authoring/mom-head-form-r6.json')
        cls.data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']

    def test_pigment_clipped_at_external_upper_border(self):
        colors,mask=finish.complexion_colors(self.data,self.spec['palette_srgb'])
        for index in (3156,6334,6344,6375,6374):self.assertEqual(mask[index],0)
        self.assertEqual(mask[3194],1);self.assertGreater(mask[55],.9)
        self.assertGreater(mask[6333],.3);self.assertLess(mask[6333],.5)
        self.assertLess(mask[2898],.3)
        _,old=prior.complexion_colors(self.data,self.spec['palette_srgb'])
        self.assertLess(int((mask>.01).sum()),int((old>.01).sum()))

    def test_alpha_is_attached_roughness_not_opacity(self):
        colors,mask=finish.complexion_colors(self.data,self.spec['palette_srgb'])
        self.assertTrue(np.isfinite(colors).all())
        np.testing.assert_allclose(colors[:,3],.47-.13*mask,atol=3e-8)
        self.assertGreaterEqual(float(colors.min()),0);self.assertLessEqual(float(colors.max()),1)

    def test_ear_transform_unchanged_from_requested_reduction(self):
        old=json.loads((ROOT/'studio/authoring/mom-head-form-r5.json').read_text())
        self.assertEqual(old['ear_finish'],self.spec['ear_finish'])
        p=self.cage(self.vertices)
        np.testing.assert_array_equal(prior.finish_ears(p,self.data,old['ear_finish']),finish.finish_ears(p,self.data,self.spec['ear_finish']))
        self.assertEqual(self.spec['portrait_smile_amount'],.4)

    def test_only_one_submillimetre_geometry_target_changes(self):
        old=json.loads((ROOT/'studio/authoring/mom-head-form-r5.json').read_text())
        changes=[a['name'] for a,b in zip(old['controls'],self.spec['controls']) if a!=b]
        self.assertEqual(changes,['lower-lip-volume'])
        self.assertEqual(old['brow_curve'],self.spec['brow_curve'])
        self.assertGreater(float(np.linalg.det(self.cage.jacobians(self.vertices)).min()),.4)
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])

    def test_r5_native_recipe_and_color_failure_evidence_preserved(self):
        report=json.loads((ROOT/'studio/reviews/mom-head-form-r5/report.json').read_text())
        for name,digest in report['scripts'].items():
            self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)


if __name__=='__main__':unittest.main()
