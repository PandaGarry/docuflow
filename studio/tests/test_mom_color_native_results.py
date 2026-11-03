"""Real R5/R6 source/build/saved-file provenance, not a likeness score."""
import gzip
import hashlib
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_face_finish_r5 as finish5
import mom_face_finish_r6 as finish6


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class MomColorNativeResultTests(unittest.TestCase):
    def test_original_recipe_and_frame_provenance(self):
        for rev in (5,6):
            with self.subTest(revision=rev):
                out=ROOT/f'studio/reviews/mom-head-form-r{rev}';r=read(out/'report.json')
                for name,digest in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/name),digest)
                self.assertEqual(r['spec_sha256'],sha(ROOT/f'studio/authoring/mom-head-form-r{rev}.json'))
                self.assertEqual(r['canonical_face_sha256'],sha(ROOT/'studio/characters/mom/master/face.png'))
                self.assertEqual(len(r['images']),11)
                for frame in r['images']:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
                self.assertTrue(r['source_topology_unchanged']);self.assertTrue(r['eye_globes_and_cornea_unchanged'])
                self.assertFalse(r['embedded_python_executed']);self.assertEqual(r['new_invalid_drivers'],[])

    def test_actual_native_basis_includes_cage_and_ear_adjustment(self):
        source=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
        for rev,finish in ((5,finish5),(6,finish6)):
            with self.subTest(revision=rev):
                out=ROOT/f'studio/reviews/mom-head-form-r{rev}';r=read(out/'report.json')
                spec,v,c=model.load_cage(ROOT/f'studio/authoring/mom-head-form-r{rev}.json')
                d=json.loads(gzip.decompress((out/'head-edit-data.json.gz').read_bytes()))
                self.assertEqual(sha(out/'head-edit-data.json.gz'),r['indexed_candidate_sha256'])
                # Rounded original/export arrays and float32 native coordinates.
                np.testing.assert_allclose(d['basis_vertices'],finish.finish_ears(c(v),source,spec['ear_finish']),atol=3e-7,rtol=0)
                for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):
                    self.assertEqual(d[key],source[key])
                self.assertLess(float(np.abs(np.array(d['basis_vertices'])[:,0]).max()),.131)

    def test_attached_colors_match_authored_palette_and_saved_materials(self):
        source=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
        for rev,finish in ((5,finish5),(6,finish6)):
            with self.subTest(revision=rev):
                out=ROOT/f'studio/reviews/mom-head-form-r{rev}';r=read(out/'report.json')
                spec=read(ROOT/f'studio/authoring/mom-head-form-r{rev}.json')
                colors,_=finish.complexion_colors(source,spec['palette_srgb'])
                digest=hashlib.sha256(colors.tobytes()).hexdigest()
                self.assertEqual(r['materials']['head_albedo_sha256'],digest)
                self.assertEqual(r['saved_material_state']['head_attribute_sha256'],digest)
                self.assertEqual(r['saved_material_state']['attribute_domain'],'POINT')
                self.assertEqual(r['saved_material_state']['attribute_points'],6395)
                self.assertEqual(r['materials']['palette_srgb']['skin'],'#E8B48F')
                self.assertEqual(r['materials']['palette_srgb']['iris'],'#73879A')

    def test_actual_saved_file_reopened_and_neutral_restore_is_exact(self):
        for rev in (5,6):
            with self.subTest(revision=rev):
                out=ROOT/f'studio/reviews/mom-head-form-r{rev}';r=read(out/'report.json');v=read(out/'reopen/verification.json')
                self.assertEqual(v['native_blend_sha256'],r['native_artifact']['sha256'])
                self.assertEqual(v['source_report_sha256'],sha(out/'report.json'))
                self.assertEqual(v['verify_script_sha256'],sha(ROOT/f'studio/tools/verify_mom_head_r{rev}_native.py'))
                self.assertEqual(v['saved_material_state'],r['saved_material_state'])
                for key in ('basis_max_coordinate_error_m','evaluated_neutral_max_coordinate_error_m','pose_restore_error_m','reopened_vs_original_rgb_mae_255'):
                    self.assertEqual(v[key],0)
                self.assertEqual(len(v['packed_images']),17);self.assertTrue(all(x['packed'] for x in v['packed_images']))
                for frame in (v['render'],v['warm_smile_render']):self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])

    def test_review_uses_identical_clay_color_registration_not_face_warp(self):
        for rev in (5,6):
            with self.subTest(revision=rev):
                out=ROOT/f'studio/reviews/mom-head-form-r{rev}';r=read(out/'image-review.json')
                self.assertEqual(r['script_sha256'],sha(ROOT/f'studio/tools/mom_head_form_review_r{rev}.py'))
                for key in ('neutral_inputs','portrait_inputs'):
                    frames=r[key];self.assertEqual(frames[1]['similarity'],frames[2]['similarity'])
                    for frame in frames:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
                self.assertFalse(r['art_approved']);self.assertFalse(r['production_swap_allowed'])

    def test_limited_smile_and_blink_blocker_not_misrepresented(self):
        for rev in (5,6):
            with self.subTest(revision=rev):
                out=ROOT/f'studio/reviews/mom-head-form-r{rev}';r=read(out/'report.json');v=read(out/'reopen/verification.json')
                self.assertEqual(r['portrait_smile_amount'],.4)
                values=v['warm_smile']['final_keys']
                for key in ('Smile','LipsUp','LipsWide'):self.assertLess(abs(values[key+'.L']-values[key+'.R']),1e-4)
                self.assertTrue(r['known_blink_visual_failure']);self.assertFalse(r['blink_visual_approved'])
                self.assertFalse(r['art_approved']);self.assertFalse(r['user_approved']);self.assertFalse(r['production_swap_allowed'])


if __name__=='__main__':unittest.main()
