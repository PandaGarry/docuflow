"""Actual R4 result provenance/persistence. Never a visual likeness test."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
OUT=ROOT/'studio/reviews/mom-head-form-r4'


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class HeadR4ResultTests(unittest.TestCase):
    def test_native_provenance_and_unapproved_scope(self):
        r=read(OUT/'report.json')
        for name,digest in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/name),digest)
        self.assertEqual(sha(ROOT/'studio/authoring/mom-head-form-r4.json'),r['spec_sha256'])
        self.assertEqual(sha(ROOT/'studio/characters/mom/master/face.png'),r['canonical_face_sha256'])
        self.assertFalse(r['embedded_python_executed'])
        self.assertFalse(r['art_approved']);self.assertFalse(r['production_swap_allowed'])
        self.assertTrue(r['source_topology_unchanged']);self.assertTrue(r['eye_globes_and_cornea_unchanged'])
        self.assertEqual(r['source_rest_signature'],r['candidate_rest_signature'])
        self.assertEqual(r['new_invalid_drivers'],[])
        self.assertEqual(r['neutral_restore_error_m'],0)
        self.assertTrue(r['known_blink_visual_failure']);self.assertFalse(r['blink_visual_approved'])

    def test_actual_basis_matches_fresh_source_recipe(self):
        r=read(OUT/'report.json');data_path=OUT/'head-edit-data.json.gz'
        self.assertEqual(sha(data_path),r['indexed_candidate_sha256'])
        d=json.loads(gzip.decompress(data_path.read_bytes()))
        _,v,c=model.load_cage(ROOT/'studio/authoring/mom-head-form-r4.json')
        # Export rounds to 7 decimals; source index is also rounded while native
        # Blender writes float32. Bound their combined error below 0.3 micrometre.
        np.testing.assert_allclose(d['basis_vertices'],c(v),atol=3e-7,rtol=0)
        previous=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r3/head-edit-data.json.gz').read_bytes()))
        for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):
            self.assertEqual(d[key],previous[key])
        self.assertGreater(float(np.linalg.norm(np.array(d['basis_vertices'])-previous['basis_vertices'],axis=1).max()),.003)

    def test_saved_binary_reopened_and_balanced_pose_restores(self):
        r=read(OUT/'report.json');v=read(OUT/'reopen/verification.json')
        self.assertEqual(v['native_blend_sha256'],r['native_artifact']['sha256'])
        self.assertEqual(v['source_report_sha256'],sha(OUT/'report.json'))
        self.assertEqual(v['verify_script_sha256'],sha(ROOT/'studio/tools/verify_mom_head_r4_native.py'))
        for key in ('basis_max_coordinate_error_m','evaluated_neutral_max_coordinate_error_m','pose_restore_error_m','reopened_vs_original_rgb_mae_255'):
            self.assertEqual(v[key],0)
        self.assertEqual(len(v['packed_images']),17)
        self.assertTrue(all(x['packed'] for x in v['packed_images']))
        for key in ('Smile','LipsUp','LipsWide'):
            values=v['warm_smile']['final_keys']
            self.assertLess(abs(values[key+'.L']-values[key+'.R']),1e-4)
        self.assertFalse(v['embedded_python_executed']);self.assertFalse(v['art_approved'])

    def test_native_frames_and_uniform_review_inputs_hashes(self):
        r=read(OUT/'report.json');v=read(OUT/'reopen/verification.json');board=read(OUT/'image-review.json')
        self.assertEqual(len(r['images']),8)
        for frame in r['images']+[v['render'],v['warm_smile_render']]+board['neutral_inputs']+board['warm_inputs']:
            self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
        self.assertEqual(board['script_sha256'],sha(ROOT/'studio/tools/mom_head_form_review_r4.py'))
        self.assertFalse(board['art_approved']);self.assertFalse(board['production_swap_allowed'])


if __name__=='__main__':unittest.main()
