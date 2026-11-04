"""Actual R15 binary/frames/geometry receipts, NOT art or likeness approval."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_anatomy_r15 as face
OUT=ROOT/'studio/reviews/mom-character-r15'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class R15ResultTests(unittest.TestCase):
 def test_actual_source_recipe_and_cycles_frames(self):
  r=read(OUT/'report.json');self.assertEqual(r['revision'],'mom-character-r15');self.assertEqual(len(r['images']),8)
  for name,digest in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/name),digest)
  self.assertEqual(r['spec_sha256'],sha(ROOT/'studio/authoring/mom-character-r15.json'));self.assertEqual(r['inherited_r14_spec_sha256'],sha(ROOT/'studio/authoring/mom-character-r14.json'))
  old=read(ROOT/'studio/reviews/mom-head-form-r13/report.json');self.assertEqual(r['downloaded_r13_binary_sha256'],old['native_artifact']['sha256'])
  for f in r['images']:self.assertEqual(sha(ROOT/f['path']),f['sha256']);self.assertEqual(f['engine'],'CYCLES')
 def test_actual_original_mesh_keys_and_expected_neutral_residual(self):
  r=read(OUT/'report.json');self.assertEqual(sha(OUT/'head-edit-data.json.gz'),r['head_edit_data_sha256'])
  d=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()));old=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r13/head-edit-data.json.gz').read_bytes()))
  spec=read(ROOT/'studio/authoring/mom-character-r15.json');np.testing.assert_allclose(d['basis_vertices'],np.array(old['basis_vertices'])+face.neutral_residual(spec),atol=3e-7,rtol=0)
  for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):self.assertEqual(d[key],old[key])
  self.assertEqual(len(d['shape_keys']),25);self.assertTrue(r['original_head_topology_weights_keys_retained']);self.assertEqual(r['source_rest_signature'],r['candidate_rest_signature'])
 def test_head_materials_and_supported_eye_sampler_not_repainted(self):
  r=read(OUT/'report.json');old=read(ROOT/'studio/reviews/mom-head-form-r13/report.json');self.assertEqual(r['saved_material_state'],old['saved_material_state'])
  self.assertTrue(r['eye_finish']['original_uv_sampler_retained']);self.assertTrue(r['eye_finish']['cornea_and_dots_unchanged']);self.assertAlmostEqual(r['eye_finish']['iris_radial_scale'],1.08)
  edited={a['object'] for a in r['edits']};self.assertNotIn('GEO-rain-eye_cornea',edited);self.assertNotIn('GEO-rain-eye_dots',edited)
 def test_native_groom_clothes_and_act_only_roundtrip(self):
  r=read(OUT/'report.json');self.assertEqual(r['groom']['type'],'CURVES');self.assertEqual(r['groom']['curves'],13864);self.assertFalse(r['groom']['solid_crown_cap'])
  self.assertGreater(r['groom']['bounds_min_m'][2],1.25);self.assertGreater(len(r['wardrobe']['objects']),5);self.assertEqual(r['brows']['fibers'],440)
  for name in ('bare-smile-check.json','clothed-smile-check.json','rig-restore-check.json'):
   check=read(OUT/name);self.assertLessEqual(check['pose_restore_error_m'],1e-7);self.assertEqual(len(check['restored_controls']),2)
  self.assertEqual(r['new_invalid_drivers'],[]);self.assertLessEqual(r['pose_restore_error_m'],1e-7)
 def test_separate_process_actual_native_reopen(self):
  r=read(OUT/'report.json');v=read(OUT/'verification.json');self.assertEqual(v['native_sha256'],r['native_artifact']['sha256']);self.assertEqual(v['report_sha256'],sha(OUT/'report.json'))
  self.assertTrue(v['geometry_matches']);self.assertEqual(v['groom_curves'],13864);self.assertFalse(v['independent_redownload']);self.assertLessEqual(v['rgb_mae_255'],.5)
  self.assertTrue(all(p['packed'] for p in v['packed_images']));self.assertEqual(sha(ROOT/v['render']['path']),v['render']['sha256'])
  self.assertTrue(r['known_blink_visual_failure']);self.assertFalse(r['blink_visual_approved']);self.assertFalse(r['art_approved']);self.assertFalse(r['production_swap_allowed'])
 def test_review_boards_are_hash_bound_and_no_art_gate(self):
  r=read(OUT/'image-review.json');v=read(OUT/'visual-review.json');self.assertEqual(r['script_sha256'],sha(ROOT/'studio/tools/mom_character_review_r15.py'));self.assertEqual(r['source_report_sha256'],sha(OUT/'report.json'))
  for key in ('character_inputs','bare_inputs'):
   for f in r[key]:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
  for f in v['inspected_images']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
  self.assertFalse(v['art_approved']);self.assertFalse(v['user_approved']);self.assertFalse(v['production_swap_allowed'])
if __name__=='__main__':unittest.main()
