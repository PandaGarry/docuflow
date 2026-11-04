"""Audit alignment/integrity tests. Never an art or anatomical approval score."""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_form_review as review


class MomFormAuditTests(unittest.TestCase):
    def test_similarity_hits_eye_anchors(self):
        t=review.similarity((2,3),(7,8))
        for actual,expected in ((review.point(t,(2,3)),(190,220)),(review.point(t,(7,8)),(410,220))):
            for a,b in zip(actual,expected):self.assertAlmostEqual(a,b)

    def test_transform_is_similarity_not_anisotropic_or_warp(self):
        t=review.similarity((2,3),(7,8))
        origin=review.point(t,(0,0))
        ex=[v-o for v,o in zip(review.point(t,(1,0)),origin)]
        ey=[v-o for v,o in zip(review.point(t,(0,1)),origin)]
        self.assertAlmostEqual(math.hypot(*ex),math.hypot(*ey))
        self.assertAlmostEqual(sum(x*y for x,y in zip(ex,ey)),0)
        self.assertGreater(ex[0]*ey[1]-ex[1]*ey[0],0)

    def test_inverse_round_trip(self):
        t=review.similarity((2,3),(7,8));a,b,c,d,e,f=review.inverse_affine(t)
        for p in ((0,0),(100,20),(-1,7)):
            x,y=review.point(t,p)
            self.assertAlmostEqual(a*x+b*y+c,p[0]);self.assertAlmostEqual(d*x+e*y+f,p[1])

    def test_coincident_eyes_rejected(self):
        with self.assertRaisesRegex(ValueError,'Coincident'):review.similarity((1,1),(1,1))

    def test_ratios_invariant_to_similarity(self):
        spec=json.loads((ROOT/'studio/reviews/mom-form-audit/landmarks.json').read_text())
        points=spec['images']['a7']['points']
        moved={k:review.point((2,.7,40,-10),p) for k,p in points.items()}
        for key,value in review.ratios(points).items():self.assertAlmostEqual(value,review.ratios(moved)[key])

    def test_only_public_canonical_and_existing_native_inputs(self):
        spec=json.loads((ROOT/'studio/reviews/mom-form-audit/landmarks.json').read_text())
        self.assertEqual(spec['images']['canonical_portrait']['path'],'studio/characters/mom/master/face.png')
        for entry in spec['images'].values():
            self.assertNotIn('studio/reference',entry['path'])
            self.assertNotIn('arena-coding-uploads',entry['path'])
            self.assertTrue((ROOT/entry['path']).is_file())
            self.assertGreater(entry['manual_uncertainty_px'],0)
        tracked=subprocess.check_output(['git','ls-files','--','studio/reference'],cwd=ROOT,text=True).splitlines()
        self.assertEqual(tracked,['studio/reference/README.md'])

    def test_report_not_new_design_or_approval(self):
        report=json.loads((ROOT/'studio/reviews/mom-form-audit/image-audit.json').read_text())
        self.assertFalse(report['new_geometry_created']);self.assertFalse(report['art_approved'])
        self.assertFalse(report['production_swap_allowed'])
        self.assertEqual(report['status'],'rejected_requires_major_rework')
        for entry in report['aligned_inputs'].values():
            self.assertEqual(entry['sha256'],hashlib.sha256((ROOT/entry['input']).read_bytes()).hexdigest())

    def test_canonical_masters_and_a7_recipes_not_rewritten(self):
        report=json.loads((ROOT/'studio/reviews/rain-mom-a7/report.json').read_text())
        for name,expected in report['scripts'].items():
            self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),expected)
        self.assertEqual(hashlib.sha256((ROOT/'studio/characters/mom/master/turnaround.png').read_bytes()).hexdigest(),report['canonical_style_reference_sha256'])


if __name__=='__main__':
    unittest.main()
