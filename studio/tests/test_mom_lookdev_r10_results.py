"""Actual independent downloaded-binary/controlled-light receipts, NOT art gates."""
import hashlib,json,sys,unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_lookdev_r10 as look
OUT=ROOT/'studio/reviews/mom-head-lookdev-r10'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class LookdevR10ResultTests(unittest.TestCase):
    def test_downloaded_binaries_match_published_assets_without_source_rebuild(self):
        r=read(OUT/'report.json');self.assertEqual(r['script_sha256'],sha(ROOT/'studio/tools/mom_head_lookdev_r10.py'))
        self.assertTrue(r['independently_downloaded_artifacts']);self.assertFalse(r['original_source_acquired'])
        for rev in ('9','10'):
            primary=ROOT/f'studio/reviews/mom-head-form-r{rev}/report.json';p=read(primary);s=r['sources'][rev]
            self.assertEqual(s['downloaded_binary_sha256'],p['native_artifact']['sha256'])
            self.assertEqual(s['committed_report_sha256'],sha(primary))
            self.assertFalse(s['source_acquired']);self.assertFalse(s['embedded_python_executed'])
            self.assertEqual(s['saved_material_state'],p['saved_material_state'])
            self.assertEqual(s['rest_signature'],p['candidate_rest_signature'])
            self.assertLessEqual(s['geometry_max_coordinate_error_m'],3e-7)
            self.assertEqual(len(s['packed_images']),19);self.assertTrue(all(i['packed'] for i in s['packed_images']))

    def test_independent_r10_neutral_pixels_before_lookdev_not_beauty_score(self):
        s=read(OUT/'report.json')['sources']['10'];f=s['independent_neutral_render']
        self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        self.assertLessEqual(s['independent_neutral_rgb_mae_255'],.5)
        self.assertLessEqual(s['independent_neutral_rgb_p99_255'],4)
        with Image.open(ROOT/f['path']) as im:self.assertEqual(im.size,(768,768))

    def test_both_poses_restore_and_same_native_smile_amount(self):
        r=read(OUT/'report.json');self.assertEqual(r['portrait_smile_amount'],.4)
        for s in r['sources'].values():
            self.assertLessEqual(s['pose_restore_error_m'],1e-7)
            values=s['warm_smile']['final_keys']
            for key in ('Smile','LipsUp','LipsWide'):self.assertLess(abs(values[key+'.L']-values[key+'.R']),1e-4)
        self.assertEqual(r['sources']['9']['warm_smile']['final_keys'],r['sources']['10']['warm_smile']['final_keys'])
        self.assertFalse(r['asset_materials_changed_by_lookdev'])

    def test_actual_higher_sample_frames_and_controlled_light(self):
        r=read(OUT/'report.json');self.assertEqual(r['lights'],look.LIGHTS);self.assertEqual(len(r['images']),5)
        frames={Path(f['path']).name:f for f in r['images']}
        self.assertEqual(frames['r9-warm-front.png']['camera'],frames['r10-warm-front.png']['camera'])
        self.assertEqual(frames['r10-neutral-front.png']['camera'],frames['r10-warm-front.png']['camera'])
        for f in r['images']:
            self.assertEqual(sha(ROOT/f['path']),f['sha256']);self.assertEqual(f['samples'],96)
            self.assertEqual(f['dimensions'],[1024,1024]);self.assertEqual(f['view_transform'],'AgX')
            with Image.open(ROOT/f['path']) as im:self.assertEqual(im.size,(1024,1024))
        self.assertFalse(r['art_approved']);self.assertFalse(r['user_approved']);self.assertFalse(r['production_swap_allowed'])

    def test_review_distinguishes_lighting_from_geometry_and_retains_failures(self):
        r=read(OUT/'image-review.json');v=read(OUT/'visual-review.json')
        self.assertEqual(r['script_sha256'],sha(ROOT/'studio/tools/mom_head_lookdev_review_r10.py'))
        self.assertEqual(r['source_report_sha256'],sha(OUT/'report.json'));self.assertFalse(r['new_geometry_created_by_lookdev'])
        for key in ('portrait_inputs','lighting_inputs'):
            for f in r[key]:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        self.assertIn('candidate-front',r['lighting_inputs'][0]['path'])
        self.assertIn('r10-neutral-front',r['lighting_inputs'][1]['path'])
        for f in v['inspected_images']:self.assertEqual(sha(ROOT/f['path']),f['sha256'])
        for rev in ('9','10'):self.assertTrue(read(ROOT/f'studio/reviews/mom-head-form-r{rev}/report.json')['known_blink_visual_failure'])
        self.assertFalse(v['art_approved']);self.assertFalse(v['production_swap_allowed'])

if __name__=='__main__':unittest.main()
