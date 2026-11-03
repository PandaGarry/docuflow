"""Native R3/source evidence and persistence, not aesthetic acceptance."""
from pathlib import Path
import gzip
import hashlib
import json
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
F=ROOT/'studio/reviews/mom-head-form-r3'


class FaceResultTests(unittest.TestCase):
    def test_real_native_image_and_script_receipts(self):
        report=json.loads((F/'report.json').read_text())
        for item in report['images']+report['paired_source_diagnostics']['images']:
            self.assertEqual(hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest(),item['sha256'])
        for name,digest in report['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(report['spec_sha256'],hashlib.sha256((ROOT/'studio/authoring/mom-head-form-r3.json').read_bytes()).hexdigest())

    def test_source_reproduces_mixed_axis_problem_without_mesh_edits(self):
        report=json.loads((F/'report.json').read_text())
        poses={p['pose']:p for p in report['paired_source_diagnostics']['poses']}
        old=poses['legacy-mixed-smile'];new=poses['paired-z-smile']
        for side in ('L','R'):self.assertAlmostEqual(old['final_keys'][f'Smile.{side}'],.6,places=4)
        self.assertGreater(abs(old['final_keys']['LipsUp.L']-old['final_keys']['LipsUp.R']),.5)
        for key in ('Smile','LipsUp','LipsWide'):self.assertAlmostEqual(new['final_keys'][key+'.L'],new['final_keys'][key+'.R'],places=4)
        self.assertGreater(old['mouth_displacement_symmetry']['mean_displacement_asymmetry_m'],.001)
        self.assertLess(new['mouth_displacement_symmetry']['mean_displacement_asymmetry_m'],.0001)
        self.assertLess(report['smile_displacement_symmetry']['mean_displacement_asymmetry_m'],.0001)

    def test_actual_r3_refinement_small_and_source_compatible(self):
        a=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r2/head-edit-data.json.gz').read_bytes()))
        b=json.loads(gzip.decompress((F/'head-edit-data.json.gz').read_bytes()))
        for key in ('polygons','vertex_weights','shape_keys'):self.assertEqual(a[key],b[key])
        delta=np.linalg.norm(np.asarray(a['basis_vertices'])-b['basis_vertices'],axis=1)
        self.assertGreater(delta.max(),.0005);self.assertLess(delta.max(),.002)

    def test_reopened_real_binary_and_balanced_pose_restore(self):
        v=json.loads((F/'reopen/verification.json').read_text());report=json.loads((F/'report.json').read_text())
        self.assertEqual(v['native_blend_sha256'],report['native_artifact']['sha256'])
        self.assertEqual(v['source_report_sha256'],hashlib.sha256((F/'report.json').read_bytes()).hexdigest())
        self.assertEqual(v['verify_script_sha256'],hashlib.sha256((ROOT/'studio/tools/verify_mom_head_r3_native.py').read_bytes()).hexdigest())
        self.assertEqual(v['pose_helper_sha256'],hashlib.sha256((ROOT/'studio/tools/mom_smile_pose_r3.py').read_bytes()).hexdigest())
        for key in ('basis_max_coordinate_error_m','evaluated_neutral_max_coordinate_error_m','pose_restore_error_m'):self.assertEqual(v[key],0)
        self.assertTrue(all(i['packed'] for i in v['packed_images']))
        for entry in (v['render'],v['warm_smile_render']):self.assertEqual(hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest(),entry['sha256'])
        keys=v['warm_smile']['final_keys']
        for side in ('L','R'):
            self.assertAlmostEqual(keys['Smile.'+side],.6,places=4)
            self.assertAlmostEqual(keys['LipsUp.'+side],.3,places=4)
        self.assertFalse(v['art_approved'])

    def test_blink_not_promoted_from_incomplete_legacy_probe(self):
        report=json.loads((F/'report.json').read_text());review=json.loads((F/'visual-review.json').read_text())
        blink=next(p for p in report['paired_source_diagnostics']['poses'] if p['pose']=='blink-70-30')
        self.assertAlmostEqual(blink['final_keys']['EyelidsClose.L'],.7,places=5)
        self.assertFalse(review['blink_status']['visually_approved']);self.assertFalse(review['production_swap_allowed'])
        for image in review['inspected_images']:self.assertEqual(hashlib.sha256((ROOT/image['path']).read_bytes()).hexdigest(),image['sha256'])


if __name__=='__main__':unittest.main()
