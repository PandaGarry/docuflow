"""Actual R18 receipts; never convert native persistence into art approval."""
import unittest,json,gzip,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-character-r18'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class R18Results(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=json.loads((OUT/'report.json').read_text());cls.v=json.loads((OUT/'verification.json').read_text())
 def test_actual_native_source_scripts_spec_and_frames(self):
  r=self.r;self.assertFalse(r['preview_only']);self.assertEqual(r['source_binary_sha256'],json.loads((ROOT/'studio/reviews/mom-character-r17/report.json').read_text())['native_artifact']['sha256']);self.assertEqual(r['spec_sha256'],sha(ROOT/'studio/authoring/mom-character-r18.json'))
  for n,digest in r['scripts'].items():self.assertEqual(sha(ROOT/'studio/tools'/n),digest,n)
  self.assertEqual(len(r['images']),9)
  for f in r['images']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
 def test_original_head_structure_preserved(self):
  old=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r17/head-edit-data.json.gz').read_bytes()));new=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()))
  for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):self.assertEqual(old[key],new[key],key)
  self.assertEqual(self.r['edits'][0]['original_blocks'],25);self.assertLess(self.r['edits'][0]['max_change_m'],.0035);self.assertEqual(self.r['new_invalid_drivers'],[]);self.assertEqual(self.r['pose_restore_error_m'],0)
 def test_reopened_actual_full_groom_and_images(self):
  self.assertEqual(self.v['status'],'actual_saved_binary_reopened_in_separate_process');self.assertEqual(self.v['native_sha256'],self.r['native_artifact']['sha256']);self.assertEqual(self.v['report_sha256'],sha(OUT/'report.json'));self.assertEqual(self.v['rgb_mae_255'],0);self.assertFalse(self.v['independent_redownload']);self.assertTrue(all(i['packed'] for i in self.v['packed_images']));self.assertEqual(sha(ROOT/self.v['render']['path']),self.v['render']['sha256'])
  for a in self.r['candidates'].values():
   state=a['saved_appearance_state'];self.assertEqual(state['packed_texture_sha256'],a['source_texture_sha256']);self.assertTrue(state['source_strand_micro_normal']['distance_m']>0);self.assertLess(state['shader']['Specular IOR Level'],.09)
 def test_original_uv_and_eye_coordinates_preserved(self):
  old=json.loads((ROOT/'studio/reviews/mom-character-r17/report.json').read_text());self.assertEqual(old['saved_material_state']['original_uv_sha256'],self.r['saved_material_state']['original_uv_sha256']);self.assertEqual(old['eye_coordinate_hashes'],self.r['eye_coordinate_hashes']);self.assertEqual(self.r['uv_paint']['linear_albedo_energy_scale'],.72)
 def test_frozen_rejected_preview_still_authentic(self):
  d=OUT/'preview';r=json.loads((d/'report.json').read_text());self.assertTrue(r['preview_only'])
  for n,h in r['scripts'].items():self.assertEqual(sha(d/'frozen-source'/n),h)
  self.assertEqual(sha(d/'frozen-source/mom-character-r18.json'),r['spec_sha256']);self.assertEqual(sha(d/'frozen-source/manifest.json'),r['asset_manifest_sha256'])
 def test_no_blink_art_production_acceptance(self):
  self.assertTrue(self.r['known_blink_visual_failure']);self.assertFalse(self.r['blink_visual_approved'])
  for record in (self.r,self.v):
   for k in ('art_approved','user_approved','production_swap_allowed'):self.assertFalse(record[k])
if __name__=='__main__':unittest.main()
