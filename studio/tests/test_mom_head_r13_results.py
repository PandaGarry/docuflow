"""Actual R13 geometry/material-held native evidence, not artistic acceptance."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_face_paint_r13 as paint
OUT=ROOT/'studio/reviews/mom-head-form-r13'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class HeadR13ResultTests(unittest.TestCase):
    def test_actual_recipe_reference_and_native_frames(self):
        r=read(OUT/'report.json');self.assertEqual(r['revision'],'mom-head-form-r13')
        for name,digest in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/name),digest)
        self.assertEqual(r['spec_sha256'],sha(ROOT/'studio/authoring/mom-head-form-r13.json'))
        self.assertEqual(r['canonical_face_sha256'],sha(ROOT/'studio/characters/mom/master/face.png'))
        self.assertEqual(len(r['images']),4);self.assertEqual(len(r['held_portrait']['images']),3)
        for frame in r['images']+r['held_portrait']['images']:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])

    def test_actual_rebuild_matches_fresh_87control_cage(self):
        r=read(OUT/'report.json');p=OUT/'head-edit-data.json.gz';self.assertEqual(sha(p),r['indexed_candidate_sha256'])
        d=json.loads(gzip.decompress(p.read_bytes()))
        old=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r12/head-edit-data.json.gz').read_bytes()))
        source=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
        spec,v,c=model.load_cage(ROOT/'studio/authoring/mom-head-form-r13.json')
        np.testing.assert_allclose(d['basis_vertices'],paint.finish_ears(c(v),source,spec['ear_finish'])+paint.nose_residual(paint.finish_ears(c(v),source,spec['ear_finish']),source,spec['nose_surface_finish'])[0],atol=3e-7,rtol=0)
        change=float(np.linalg.norm(np.array(d['basis_vertices'])-old['basis_vertices'],axis=1).max())
        self.assertGreater(change,.0035);self.assertLess(change,.0045)
        for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):self.assertEqual(d[key],source[key])
        self.assertEqual(len(d['shape_keys']),25);self.assertEqual(r['cage_safety']['controls'],87)
        self.assertTrue(r['eye_globes_and_cornea_unchanged']);self.assertTrue(r['source_topology_unchanged'])
        self.assertEqual(r['source_rest_signature'],r['candidate_rest_signature']);self.assertEqual(r['new_invalid_drivers'],[])

    def test_actual_original_uv_and_exr_bytes_identical_to_r12(self):
        r=read(OUT/'report.json');old=read(ROOT/'studio/reviews/mom-head-form-r12/report.json')
        a=old['materials']['uv_paint'];b=r['materials']['uv_paint']
        self.assertEqual(r['materials']['palette_srgb'],old['materials']['palette_srgb'])
        self.assertEqual(r['original_uv_sha256'],old['original_uv_sha256'])
        for key in ('albedo_exr_sha256','roughness_exr_sha256','original_uv_domain'):self.assertEqual(a[key],b[key])
        self.assertEqual(r['saved_material_state'],old['saved_material_state'])
        self.assertEqual(r['materials']['held_material_library']['downloaded_binary_sha256'],read(ROOT/'studio/reviews/mom-head-form-r11/report.json')['native_artifact']['sha256'])
        state=r['saved_material_state'];self.assertEqual(state,read(OUT/'reopen/verification.json')['saved_material_state'])
        for socket,key in (('Base Color','albedo_exr_sha256'),('Roughness','roughness_exr_sha256'),('Coat Weight','roughness_exr_sha256'),('Coat Roughness','roughness_exr_sha256')):
            im=state['active_original_uv_maps'][socket]
            self.assertEqual(im['packed_file_sha256'],b[key]);self.assertEqual(im['size'],[2048,2048])
            self.assertEqual(im['colorspace'],'Non-Color')
        self.assertEqual(state['head_attribute_sha256'],old['saved_material_state']['head_attribute_sha256'])

    def test_saved_neutral_binary_reopened_not_portrait_stage(self):
        r=read(OUT/'report.json');v=read(OUT/'reopen/verification.json')
        self.assertEqual(r['native_artifact']['sha256'],v['native_blend_sha256'])
        self.assertEqual(v['source_report_sha256'],sha(OUT/'report.json'))
        self.assertEqual(v['verify_script_sha256'],sha(ROOT/'studio/tools/verify_mom_head_r13_native.py'))
        for key in ('basis_max_coordinate_error_m','evaluated_neutral_max_coordinate_error_m','pose_restore_error_m'):self.assertEqual(v[key],0)
        self.assertLessEqual(v['reopened_vs_original_rgb_mae_255'],.5)
        for f in (v['render'],v['warm_smile_render']):self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        self.assertEqual(len(v['packed_images']),19);self.assertTrue(all(i['packed'] for i in v['packed_images']))
        self.assertTrue(r['known_blink_visual_failure']);self.assertFalse(r['blink_visual_approved'])
        self.assertFalse(r['embedded_python_executed']);self.assertFalse(r['art_approved']);self.assertFalse(r['user_approved']);self.assertFalse(r['production_swap_allowed'])

    def test_exact_frozen_r10_portrait_light_and_smile(self):
        r=read(OUT/'report.json');p=r['held_portrait'];old=read(ROOT/'studio/reviews/mom-head-lookdev-r10/report.json')
        self.assertEqual(p['lights'],old['lights']);self.assertEqual(p['lighting_script_sha256'],old['script_sha256'])
        self.assertEqual(p['pose_restore_error_m'],0);self.assertEqual(r['portrait_smile_amount'],.4)
        self.assertEqual(p['smile']['final_keys'],old['sources']['10']['warm_smile']['final_keys'])
        for f in p['images']:self.assertEqual(f['dimensions'],[1024,1024]);self.assertEqual(f['samples'],96)
        self.assertEqual(p['images'][0]['camera'],next(f for f in old['images'] if f['path'].endswith('r10-warm-front.png'))['camera'])

    def test_review_sources_and_no_art_gate(self):
        r=read(OUT/'image-review.json');v=read(OUT/'visual-review.json')
        self.assertEqual(r['script_sha256'],sha(ROOT/'studio/tools/mom_head_form_review_r13.py'))
        self.assertTrue(r['geometry_changed_since_r11']);self.assertTrue(r['material_and_light_values_held'])
        self.assertTrue(all(r['packed_exr_hashes_equal_r11'].values()))
        for key in ('neutral_inputs','form_inputs','portrait_inputs'):
            for f in r[key]:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        for detail in r['detail_inputs']:
            self.assertEqual(detail['uniform_scale'],3);a,b=detail['inputs'];self.assertEqual(a['camera'],b['camera'])
            for f in detail['inputs']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        for f in v['inspected_images']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        self.assertFalse(v['art_approved']);self.assertFalse(v['production_swap_allowed'])

if __name__=='__main__':unittest.main()
