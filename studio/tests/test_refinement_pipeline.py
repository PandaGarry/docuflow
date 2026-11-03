"""R3 pure authoring regression, not image/animation approval."""
from __future__ import annotations
import math
from pathlib import Path
import tempfile
import unittest
from studio.authoring.mesh import Mesh, sweater, topology
from studio.authoring.refined_body import digits, hand, shoulders, subdivide
from studio.tools.build_deformation_test import build
from studio.tools.check_body_extremes import poses
from studio.pipeline.contracts import ROOT, file_hash, load_json
from studio.pipeline.packages import validate_bundle


class ConnectedHands(unittest.TestCase):
    def test_closed_single_surface_before_and_after_subdivision(self):
        for sign in (-1,1):
            for refined in (False,True):
                mesh,tips=hand(sign,refined);audit=topology(mesh.vertices,mesh.faces)
                self.assertEqual(audit['components'],1)
                self.assertEqual(audit['nonmanifold_edges'],0)
                self.assertEqual(set(range(len(mesh.vertices))),{v for f in mesh.faces for v in f})
                if refined:self.assertEqual(audit['quad_fraction'],1)

    def test_tip_indices_survive_authoring_subdivision(self):
        raw,tips=hand(1,False);refined,new_tips=hand(1)
        self.assertEqual(tips,new_tips)
        for ring in tips.values():
            self.assertEqual(len(ring),8)
            self.assertTrue(all(i<len(raw.vertices) for i in ring))
            self.assertTrue(all(i<len(refined.vertices) for i in ring))

    def test_no_runtime_subdivision_needed_for_probe_correspondence(self):
        mesh,tips=hand(1)
        self.assertEqual(len(mesh.vertices),4898)
        self.assertEqual(len(mesh.faces),4896)

    def test_left_index_is_next_to_left_thumb_not_pinky(self):
        for sign in (-1,1):
            d=digits(sign)
            self.assertLess(abs(d['index'][0][0]-d['thumb'][0][0]),abs(d['pinky'][0][0]-d['thumb'][0][0]))

    def test_rest_bones_mirror_anatomically(self):
        left,right=digits(-1),digits(1)
        for name in right:
            for a,b in zip(left[name],right[name]):
                self.assertAlmostEqual(a[0],-b[0]);self.assertEqual(a[1:],b[1:])

    def test_weights_finite_normalized_nonnegative(self):
        for mesh in (hand(-1)[0],hand(1)[0],shoulders()):
            for weights in mesh.weights:
                self.assertAlmostEqual(sum(weights.values()),1)
                self.assertTrue(all(math.isfinite(v) and v>0 for v in weights.values()))

    def test_hand_rejects_invalid_side(self):
        with self.assertRaises(ValueError):hand(0)

    def test_subdivision_rejects_open_mesh(self):
        m=Mesh()
        for p in ((0,0,0),(1,0,0),(0,1,0)):m.vertex(p,{'a':1})
        m.faces=[(0,1,2)]
        with self.assertRaises(ValueError):subdivide(m)

    def test_subdivision_cube_has_known_limit_step_and_normalized_weights(self):
        m=Mesh()
        for p in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]:m.vertex(p,{'a':1})
        m.faces=[(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        new=subdivide(m)
        self.assertEqual((len(new.vertices),len(new.faces)),(26,24))
        for p in new.vertices[:8]:
            for value in p:self.assertAlmostEqual(abs(value),5/9)
        self.assertTrue(all(w=={'a':1} for w in new.weights))

    def test_shoulders_keep_closed_connectivity(self):
        old,new=sweater(),shoulders()
        self.assertEqual(old.faces,new.faces)
        self.assertEqual(topology(new.vertices,new.faces)['components'],1)
        self.assertEqual(topology(new.vertices,new.faces)['nonmanifold_edges'],0)
        self.assertNotEqual(old.vertices,new.vertices)

    def test_clavicle_weights_exist_on_both_sides(self):
        groups={b for w in shoulders().weights for b in w}
        self.assertIn('clavicle.R',groups);self.assertIn('clavicle.L',groups)

    def test_elbow_helper_weights_are_normalized_and_present_on_both_sides(self):
        mesh=shoulders()
        for side in ('R','L'):
            values=[w.get(f'elbow_deform.{side}',0) for w in mesh.weights]
            self.assertGreater(max(values),.65)
            self.assertLessEqual(max(values),.8+1e-9)

    def test_authoring_is_deterministic(self):
        a,_=hand(1);b,_=hand(1)
        self.assertEqual((a.vertices,a.faces,a.weights),(b.vertices,b.faces,b.weights))


class DeformationFixture(unittest.TestCase):
    def test_seventeen_static_cases_cover_both_sides(self):
        cases=poses();self.assertEqual(len(cases),17);self.assertEqual(len({name for name,_ in cases}),17)
        for side in ('R','L'):
            for suffix in ('forward','overhead','abduction','elbow_fold','wrist_flexion','wrist_extension','wrist_deviation','curl'):
                self.assertIn(f'{side}_{suffix}',dict(cases))

    def test_r3_recorded_bundle(self):
        d=ROOT/'studio/production/dad-refined'
        validate_bundle(load_json(d/'project.json'),load_json(d/'package-r3.json'),load_json(d/'shot.json'),verify_files=False)

    def test_generated_fixture_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);build(path);before=(path/'shot.json').read_bytes();build(path)
            self.assertEqual(before,(path/'shot.json').read_bytes())
            self.assertEqual(load_json(path/'shot.json')['frame_range'],[0,72])

    def test_return_to_rest_and_no_root_translation(self):
        shot=load_json(ROOT/'studio/production/dad-refined/shot.json')
        for track in shot['tracks']:
            self.assertNotEqual(track['control'],'body.translation')
            self.assertEqual(track['keys'][0]['value'],track['keys'][-1]['value'])

    def test_reach_follows_spatial_arc_not_straight_wrist_translation(self):
        s=load_json(ROOT/'studio/production/dad-refined/shot.json')
        track=next(t for t in s['tracks'] if t['control']=='arm.R.target')
        self.assertGreater(max(k['value'][0] for k in track['keys']),.9)

    def test_historical_r2_recipes_still_match_persisted_provenance(self):
        a=load_json(ROOT/'studio/production/dad-rig/package-r2.json')
        p=a['provenance'];self.assertEqual(file_hash(ROOT/p['authoring_script']),p['script_sha256'])
        for dep in p['dependencies']:self.assertEqual(file_hash(ROOT/dep['path']),dep['sha256'])


if __name__=='__main__':unittest.main()
