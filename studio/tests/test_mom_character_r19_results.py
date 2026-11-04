"""Actual original-rig R19 receipt checks, independent of artistic judgment."""
import unittest,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-character-r19'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class R19Results(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=json.loads((OUT/'report.json').read_text());cls.v=json.loads((OUT/'verification.json').read_text());cls.old=json.loads((ROOT/'studio/reviews/mom-character-r18/report.json').read_text())
 def test_actual_source_scripts_and_native_scope(self):
  self.assertEqual(self.r['source_binary_sha256'],self.old['native_artifact']['sha256']);self.assertEqual(self.r['spec_sha256'],sha(ROOT/'studio/authoring/mom-character-r19.json'));self.assertEqual(self.r['native_runtime'],'4.5.0')
  for n,h in self.r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/n),h,n)
 def test_actual_physical_curves_persisted(self):
  state=self.r['saved_curve_state'];self.assertEqual(state['curves'],16000);self.assertEqual(state['points'],640000);self.assertEqual(state['parent_bone'],'DEF-Head');self.assertEqual(state['coordinate_sha256'],self.r['groom']['coordinate_sha256']);self.assertAlmostEqual(state['shader']['Melanin'],.48,places=6);self.assertGreater(self.r['groom']['actual_surface_guides'],1000)
 def test_original_face_eyes_uv_and_rest_unchanged(self):
  self.assertTrue(self.r['head_unchanged_from_r18']);self.assertEqual(self.r['head_edit_data_sha256'],self.old['head_edit_data_sha256']);self.assertEqual(sha(OUT/'head-edit-data.json.gz'),self.old['head_edit_data_sha256'])
  for k in ('saved_material_state','eye_coordinate_hashes','candidate_rest_signature'):self.assertEqual(self.r[k],self.old[k])
  self.assertEqual(self.r['new_invalid_drivers'],[]);self.assertEqual(self.r['pose_restore_error_m'],0)
 def test_fresh_portraits_and_anatomy_reuse_are_explicit(self):
  self.assertEqual(len(self.r['images']),9);reused=[f for f in self.r['images'] if f.get('reused_from')];self.assertEqual(len(reused),4)
  for f in self.r['images']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
  for f in reused:self.assertEqual(sha(ROOT/f['reused_from']),f['sha256']);self.assertIn('reuse',f['scope'])
 def test_actual_separate_process_reopen(self):
  self.assertEqual(self.v['status'],'actual_saved_binary_reopened_in_separate_process');self.assertEqual(self.v['native_sha256'],self.r['native_artifact']['sha256']);self.assertEqual(self.v['report_sha256'],sha(OUT/'report.json'));self.assertEqual(self.v['rgb_mae_255'],0);self.assertTrue(all(i['packed'] for i in self.v['packed_images']));self.assertFalse(self.v['independent_redownload']);self.assertEqual(sha(ROOT/self.v['render']['path']),self.v['render']['sha256'])
 def test_no_art_or_full_acting_acceptance_from_hair_density(self):
  self.assertTrue(self.r['known_blink_visual_failure']);self.assertFalse(self.r['blink_visual_approved'])
  for record in (self.r,self.v):
   for k in ('art_approved','user_approved','production_swap_allowed'):self.assertFalse(record[k])
if __name__=='__main__':unittest.main()
