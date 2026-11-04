"""Actual R16 appearance-only binary, reused anatomy and fresh Cycles frames."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-character-r16'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class R16ResultTests(unittest.TestCase):
 def test_verified_native_parent_and_frozen_recipe(self):
  r=read(OUT/'report.json');old=read(ROOT/'studio/reviews/mom-character-r15/report.json');self.assertEqual(r['revision'],'mom-character-r16');self.assertEqual(r['downloaded_r15_binary_sha256'],old['native_artifact']['sha256']);self.assertEqual(r['source_r15_report_sha256'],sha(ROOT/'studio/reviews/mom-character-r15/report.json'))
  self.assertEqual(r['spec_sha256'],sha(ROOT/'studio/authoring/mom-character-r16.json'))
  for n,d in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/n),d)
  self.assertEqual(r['head_edits_this_revision'],[]);self.assertTrue(r['head_unchanged_since_r15']);self.assertTrue(r['eye_coordinates_unchanged_since_r15'])
  self.assertEqual((OUT/'head-edit-data.json.gz').read_bytes(),(ROOT/'studio/reviews/mom-character-r15/head-edit-data.json.gz').read_bytes());self.assertEqual(r['saved_material_state'],old['saved_material_state'])
 def test_actual_fresh_portraits_and_explicit_reused_anatomy(self):
  r=read(OUT/'report.json');self.assertEqual(len(r['images']),8);reuse=[f for f in r['images'] if 'reused_from' in f];self.assertEqual(len(reuse),4)
  for f in r['images']:self.assertEqual(sha(ROOT/f['path']),f['sha256']);self.assertEqual(f['engine'],'CYCLES')
  for f in reuse:self.assertEqual(sha(ROOT/f['reused_from']),f['sha256'])
  self.assertEqual(r['groom']['type'],'CURVES');self.assertEqual(r['groom']['curves'],13864);self.assertFalse(r['groom']['solid_crown_cap']);self.assertEqual(r['source_rest_signature'],r['candidate_rest_signature']);self.assertEqual(r['new_invalid_drivers'],[]);self.assertEqual(r['pose_restore_error_m'],0)
 def test_actual_separate_process_reopen(self):
  r=read(OUT/'report.json');v=read(OUT/'verification.json');self.assertEqual(v['native_sha256'],r['native_artifact']['sha256']);self.assertEqual(v['report_sha256'],sha(OUT/'report.json'));self.assertTrue(v['head_and_eyes_match']);self.assertEqual(v['groom_curves'],13864);self.assertLessEqual(v['rgb_mae_255'],.5)
  self.assertFalse(v['independent_redownload']);self.assertTrue(all(i['packed'] for i in v['packed_images']));self.assertEqual(sha(ROOT/v['render']['path']),v['render']['sha256']);self.assertFalse(r['art_approved']);self.assertTrue(r['known_blink_visual_failure'])
 def test_hash_bound_actual_review_not_likeness_score(self):
  r=read(OUT/'image-review.json');v=read(OUT/'visual-review.json');self.assertEqual(r['script_sha256'],sha(ROOT/'studio/tools/mom_character_review_r16.py'));self.assertEqual(r['source_report_sha256'],sha(OUT/'report.json'))
  for k in ('character_inputs','bare_inputs'):
   for f in r[k]:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
  for f in v['inspected_images']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
  self.assertFalse(v['art_approved']);self.assertFalse(v['user_approved']);self.assertFalse(v['production_swap_allowed'])
if __name__=='__main__':unittest.main()
