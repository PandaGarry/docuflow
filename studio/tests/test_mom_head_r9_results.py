"""Actual R9 geometry/UV-map binary provenance. Not likeness or art approval."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_face_paint_r9 as paint
OUT=ROOT/'studio/reviews/mom-head-form-r9'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class HeadR9ResultTests(unittest.TestCase):
    def test_live_recipe_source_and_native_frames_provenance(self):
        r=read(OUT/'report.json')
        for name,digest in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/name),digest)
        self.assertEqual(r['spec_sha256'],sha(ROOT/'studio/authoring/mom-head-form-r9.json'))
        self.assertEqual(r['canonical_face_sha256'],sha(ROOT/'studio/characters/mom/master/face.png'))
        self.assertEqual(len(r['images']),11)
        for frame in r['images']:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
        self.assertTrue(r['source_topology_unchanged']);self.assertTrue(r['eye_globes_and_cornea_unchanged'])
        self.assertEqual(r['source_rest_signature'],r['candidate_rest_signature'])
        self.assertEqual(r['new_invalid_drivers'],[]);self.assertFalse(r['embedded_python_executed'])

    def test_actual_geometry_changes_and_matches_fresh_source_recipe(self):
        r=read(OUT/'report.json');path=OUT/'head-edit-data.json.gz'
        self.assertEqual(sha(path),r['indexed_candidate_sha256'])
        d=json.loads(gzip.decompress(path.read_bytes()))
        previous=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r7/head-edit-data.json.gz').read_bytes()))
        source=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
        spec,v,c=model.load_cage(ROOT/'studio/authoring/mom-head-form-r9.json')
        np.testing.assert_allclose(d['basis_vertices'],paint.finish_ears(c(v),source,spec['ear_finish']),atol=3e-7,rtol=0)
        difference=float(np.linalg.norm(np.array(d['basis_vertices'])-previous['basis_vertices'],axis=1).max())
        self.assertGreater(difference,.003);self.assertLess(difference,.004)
        for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):self.assertEqual(d[key],source[key])
        self.assertEqual(len(d['shape_keys']),25)

    def test_actual_original_uvs_packed_exrs_and_shader_links_persist(self):
        r=read(OUT/'report.json');v=read(OUT/'reopen/verification.json');layout=read(OUT/'original-uv-layout.json')
        state=r['saved_material_state'];receipt=r['materials']['uv_paint']
        self.assertEqual(state,v['saved_material_state'])
        self.assertEqual(r['original_uv_sha256'],state['original_uv_sha256'])
        self.assertEqual(layout['original_uv_sha256'],r['original_uv_sha256'])
        self.assertEqual(receipt['original_uv_sha256'],r['original_uv_sha256'])
        self.assertTrue(r['materials']['head_albedo_attribute_is_fallback'])
        self.assertEqual(receipt['resolution'],2048);self.assertGreater(receipt['covered_texels'],1000)
        for socket,key in (('Base Color','albedo_exr_sha256'),('Roughness','roughness_exr_sha256')):
            image=state['active_original_uv_maps'][socket]
            self.assertEqual(image['packed_file_sha256'],receipt[key])
            self.assertEqual(image['size'],[2048,2048]);self.assertEqual(image['colorspace'],'Non-Color')
            self.assertEqual(image['uv_map'],layout['render_uv'])
            self.assertAlmostEqual(image['uniform_domain_scale'][0],image['uniform_domain_scale'][1])
            self.assertAlmostEqual(image['uniform_domain_scale'][0],1/layout['domain']['extent'],places=6)
        self.assertEqual(len(v['packed_images']),19);self.assertTrue(all(x['packed'] for x in v['packed_images']))

    def test_actual_saved_file_and_pose_restoration(self):
        r=read(OUT/'report.json');v=read(OUT/'reopen/verification.json')
        self.assertEqual(v['native_blend_sha256'],r['native_artifact']['sha256'])
        self.assertEqual(v['source_report_sha256'],sha(OUT/'report.json'))
        self.assertEqual(v['verify_script_sha256'],sha(ROOT/'studio/tools/verify_mom_head_r9_native.py'))
        for key in ('basis_max_coordinate_error_m','evaluated_neutral_max_coordinate_error_m','pose_restore_error_m'):
            self.assertEqual(v[key],0)
        self.assertLessEqual(v['reopened_vs_original_rgb_mae_255'],.5)
        for frame in (v['render'],v['warm_smile_render']):self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
        values=v['warm_smile']['final_keys']
        for key in ('Smile','LipsUp','LipsWide'):self.assertLess(abs(values[key+'.L']-values[key+'.R']),1e-4)
        self.assertTrue(r['known_blink_visual_failure']);self.assertFalse(r['blink_visual_approved'])
        self.assertFalse(r['art_approved']);self.assertFalse(r['user_approved']);self.assertFalse(r['production_swap_allowed'])

    def test_local_upper_lip_revision_retains_r8_form_direction(self):
        old=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r8/head-edit-data.json.gz').read_bytes()))
        new=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()))
        change=float(np.linalg.norm(np.array(new['basis_vertices'])-old['basis_vertices'],axis=1).max())
        self.assertGreater(change,.001);self.assertLess(change,.0016)
        a=read(ROOT/'studio/authoring/mom-head-form-r8.json');b=read(ROOT/'studio/authoring/mom-head-form-r9.json')
        for x,y in zip(a['controls'],b['controls']):
            if x['name'] not in b['revision_deltas_from_r8_m']:self.assertEqual(x,y)
        self.assertEqual(a['ear_finish'],b['ear_finish']);self.assertEqual(a['brow_curve'],b['brow_curve'])
        self.assertEqual(read(OUT/'report.json')['original_uv_sha256'],read(ROOT/'studio/reviews/mom-head-form-r8/report.json')['original_uv_sha256'])

    def test_review_boards_do_not_replace_geometry_with_material_advantage(self):
        image=read(OUT/'image-review.json');visual=read(OUT/'visual-review.json')
        self.assertEqual(image['script_sha256'],sha(ROOT/'studio/tools/mom_head_form_review_r9.py'))
        self.assertTrue(image['geometry_changed_since_r7'])
        for key in ('color_inputs','form_inputs','portrait_inputs'):
            for frame in image[key]:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
        self.assertTrue(all('clay-' in f['path'] for f in image['form_inputs'][1:]))
        for frame in visual['inspected_images']:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
        detail=read(OUT/'lip-image-review.json')
        self.assertEqual(detail['script_sha256'],sha(ROOT/'studio/tools/mom_lip_review_r9.py'))
        for frame in detail['inputs']:self.assertEqual(sha(ROOT/frame['path']),frame['sha256'])
        self.assertEqual(detail['inputs'][0]['camera'],detail['inputs'][1]['camera'])
        self.assertEqual(detail['uniform_scale'],3)
        self.assertFalse(visual['art_approved']);self.assertFalse(visual['production_swap_allowed'])
        self.assertTrue((ROOT/'studio/reviews/mom-head-form-r8/attempt-1/native-failure.txt').is_file())

if __name__=='__main__':unittest.main()
