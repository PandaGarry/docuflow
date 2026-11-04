"""Committed actual-native receipt integrity, not local render or art approval."""
import unittest,sys,json,gzip,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-character-r17'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class R17NativeReceipts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=read(OUT/'report.json');cls.v=read(OUT/'verification.json')
 def test_actual_source_binding(self):
  r=self.r;self.assertFalse(r['preview_only']);self.assertEqual(r['spec_sha256'],sha(ROOT/'studio/authoring/mom-character-r17.json'));self.assertEqual(r['canonical_face_sha256'],sha(ROOT/'studio/characters/mom/master/face.png'))
  for name,digest in r['scripts'].items():self.assertEqual(digest,sha(ROOT/'studio/tools'/name))
 def test_original_structure_uv_rest_and_cornea_retained(self):
  r=self.r;old=read(ROOT/'studio/reviews/mom-character-r16/report.json');a=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r16/head-edit-data.json.gz').read_bytes()));b=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()))
  for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):self.assertEqual(a[key],b[key])
  self.assertEqual(r['original_head_key_count'],25);self.assertEqual(r['candidate_rest_signature'],old['candidate_rest_signature']);self.assertEqual(r['saved_material_state']['original_uv_sha256'],old['saved_material_state']['original_uv_sha256']);self.assertEqual(r['eye_coordinate_hashes']['GEO-rain-eye_cornea'],old['eye_coordinate_hashes']['GEO-rain-eye_cornea']);self.assertEqual(r['pose_restore_error_m'],0);self.assertEqual(r['new_invalid_drivers'],[])
 def test_fresh_actual_frames_not_retouched(self):
  r=self.r;self.assertEqual(len(r['images']),9);self.assertIn('source-r16-held-light-bare-front.png',[Path(f['path']).name for f in r['images']])
  for f in r['images']+[self.v['render']]:self.assertEqual(f['sha256'],sha(ROOT/f['path']));self.assertNotIn('reused_from',f)
  self.assertEqual(r['head_edit_data_sha256'],sha(OUT/'head-edit-data.json.gz'))
 def test_reopen_does_not_override_explicit_visual_rejection(self):
  r=self.r;v=self.v;visual=read(OUT/'visual-review.json');self.assertEqual(v['native_sha256'],r['native_artifact']['sha256']);self.assertEqual(v['report_sha256'],sha(OUT/'report.json'));self.assertEqual(v['rgb_mae_255'],0);self.assertEqual(len(v['packed_images']),17);self.assertTrue(all(i['packed'] for i in v['packed_images']));self.assertTrue(visual['native_technical_success']);self.assertFalse(visual['hair_accepted']);self.assertFalse(visual['canonical_identity_finished'])
  for receipt in (r,v,visual):
   for key in ('art_approved','user_approved','production_swap_allowed'):self.assertFalse(receipt[key])
if __name__=='__main__':unittest.main()
