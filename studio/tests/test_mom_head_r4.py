"""R4 authored intent/safety, not a likeness or anatomy score."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model


class HeadR4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous,cls.vertices,cls.old=model.load_cage(ROOT/'studio/authoring/mom-head-form-r3.json')
        cls.spec,_,cls.cage=model.load_cage(ROOT/'studio/authoring/mom-head-form-r4.json')

    def test_only_declared_art_controls_changed(self):
        deltas=self.spec['revision_deltas_from_r3_m']
        self.assertEqual(len(self.spec['controls']),83)
        for old,new in zip(self.previous['controls'],self.spec['controls']):
            self.assertEqual(old['name'],new['name'])
            self.assertEqual(old['source_vertex'],new['source_vertex'])
            actual=np.array(new['target_world_m'])-old['target_world_m']
            np.testing.assert_allclose(actual,deltas.get(new['name'],[0,0,0]),atol=1e-12)
        self.assertEqual(self.spec['brow_curve'],self.previous['brow_curve'])

    def test_mouth_raised_and_widened_not_eye_compensation(self):
        d=self.spec['revision_deltas_from_r3_m']
        self.assertAlmostEqual(d['mouth-seam'][2],.0035)
        self.assertGreater(d['mouth-corner.L'][0],0)
        self.assertLess(d['mouth-corner.R'][0],0)
        self.assertFalse(any('lid' in n or 'canthus' in n or 'brow' in n for n in d))
        self.assertLess(d['jaw-angle.L'][0],0)
        self.assertGreater(d['tip-shoulder.L'][0],0)

    def test_bilateral_authored_deltas(self):
        d=self.spec['revision_deltas_from_r3_m']
        for name,delta in d.items():
            if name.endswith('.L'):
                np.testing.assert_allclose(d[name[:-1]+'R'],[-delta[0],delta[1],delta[2]],atol=1e-12)

    def test_sampled_nonfolding_and_bounded_revision(self):
        v=self.vertices;c=self.cage
        self.assertGreater(float(np.linalg.det(c.jacobians(v)).min()),.2)
        self.assertLess(float(np.linalg.norm(c(v)-self.old(v),axis=1).max()),.006)
        self.assertGreater(float(np.linalg.norm(c(v)-self.old(v),axis=1).max()),.003)
        np.testing.assert_allclose(c(c.centers)-c.centers,c.displacements,atol=1e-12)

    def test_not_approval_and_historical_recipe_frozen(self):
        self.assertFalse(self.spec['art_approved'])
        self.assertFalse(self.spec['production_swap_allowed'])
        import hashlib
        report=json.loads((ROOT/'studio/reviews/mom-head-form-r3/report.json').read_text())
        path=ROOT/'studio/tools/mom_head_form_r3.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),report['scripts'][path.name])


if __name__=='__main__':unittest.main()
