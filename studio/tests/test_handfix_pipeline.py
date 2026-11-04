"""R5 technical weight correction. No implicit visual/anatomy approval."""
from __future__ import annotations
from copy import deepcopy
import unittest
from studio.authoring.lookdev import hand as hand_r4
from studio.authoring.refined_hands import hand,smooth_thumb_weights
from studio.pipeline.contracts import ROOT,load_json,file_hash
from studio.pipeline.packages import validate_bundle


class ThumbWeightCorrection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old={s:hand_r4(s) for s in (-1,1)}
        cls.new={s:hand(s) for s in (-1,1)}

    def test_identical_geometry_topology_and_probe_ids(self):
        for s in (-1,1):
            old,tips=self.old[s];new,ids=self.new[s]
            self.assertEqual(new.vertices,old.vertices)
            self.assertEqual(new.faces,old.faces)
            self.assertEqual(ids,tips)

    def test_other_digits_and_forearm_anchors_unchanged(self):
        for s in (-1,1):
            old=self.old[s][0];new=self.new[s][0];palm='hand.'+('R' if s>0 else 'L')
            for a,b in zip(old.weights,new.weights):
                if any(k!=palm and not k.startswith('thumb.') for k in a):self.assertEqual(a,b)
                if a.get(palm,0)==0 or not any(k.startswith('thumb.') for k in a):self.assertEqual(a,b)

    def test_weights_finite_normalized_and_nonnegative(self):
        for mesh,_ in self.new.values():
            for w in mesh.weights:
                self.assertTrue(w)
                self.assertAlmostEqual(sum(w.values()),1,places=12)
                self.assertTrue(all(0<=v<=1 for v in w.values()))

    def test_change_is_local_not_whole_hand_reweighting(self):
        for s in (-1,1):
            a,b=self.old[s][0],self.new[s][0]
            changed=sum(x!=y for x,y in zip(a.weights,b.weights))
            self.assertGreater(changed,0)
            self.assertLess(changed,len(a.vertices)*.1)

    def test_mirrored_bone_weight_moments(self):
        def moments(s,bone):
            mesh=self.new[s][0];side='R' if s>0 else 'L';key=f'{bone}.{side}'
            return [sum(w.get(key,0)*(1 if k==-1 else p[k]*(-1 if k==0 and s<0 else 1))
                        for p,w in zip(mesh.vertices,mesh.weights)) for k in (-1,0,1,2)]
        for bone in ('thumb.01','hand'):
            for a,b in zip(moments(-1,bone),moments(1,bone)):self.assertAlmostEqual(a,b,places=7)

    def test_authoring_is_deterministic(self):
        mesh,tips=hand(1)
        self.assertEqual(mesh.weights,self.new[1][0].weights)
        self.assertEqual(tips,self.new[1][1])

    def test_invalid_solver_configuration_rejected(self):
        for side,n in [('bad',1),('R',-1),('R',201),('R',True),('R',1.5)]:
            with self.assertRaises(ValueError):smooth_thumb_weights(self.old[1][0],side,n)

    def test_zero_iterations_preserves_weights_to_float_precision(self):
        mesh=deepcopy(self.old[1][0]);before=deepcopy(mesh.weights)
        smooth_thumb_weights(mesh,'R',0)
        # Reconstructing normalized groups can change the final floating-point bit.
        for a,b in zip(mesh.weights,before):
            self.assertEqual(set(a),set(b))
            for key in a:self.assertAlmostEqual(a[key],b[key],places=12)


class HandfixEvidence(unittest.TestCase):
    def setUp(self):
        self.d=ROOT/'studio/production/dad-handfix'
        self.package=load_json(self.d/'package-r5.json')

    def test_recorded_contract_without_generated_binary(self):
        validate_bundle(load_json(self.d/'project.json'),self.package,load_json(self.d/'shot.json'),verify_files=False)
        self.assertEqual(self.package['revision'],'r5')
        self.assertEqual(self.package['art_status'],'unreviewed')

    def test_all_authoring_provenance_is_current(self):
        p=self.package['provenance']
        self.assertEqual(file_hash(ROOT/p['authoring_script']),p['script_sha256'])
        for item in p['dependencies']:self.assertEqual(file_hash(ROOT/item['path']),item['sha256'])

    def test_native_receipts_pass_every_original_case(self):
        limits={'min_area_ratio':.025,'max_area_ratio':6,'max_edge_ratio':3,'max_ik_error_m':.005}
        for name,count in [('extremes',17),('animated',72)]:
            r=load_json(ROOT/f'studio/production/dad-r5-{name}.json')
            self.assertEqual(r['status'],'passed')
            self.assertEqual(len(r['poses']),count)
            self.assertTrue(all(p['passed'] for p in r['poses']))
            self.assertEqual(r['limits'],limits)
            self.assertEqual(r['blend_sha256'],self.package['blend']['sha256'])

    def test_receipts_identify_current_checker(self):
        expected=file_hash(ROOT/'studio/tools/check_lookdev.py')
        for name in ('extremes','animated'):
            self.assertEqual(load_json(ROOT/f'studio/production/dad-r5-{name}.json')['checker_sha256'],expected)

    def test_motion_fixture_not_softened(self):
        a=load_json(ROOT/'studio/production/dad-lookdev/shot.json');b=load_json(self.d/'shot.json')
        for key in ('project_id','asset_revision','shot_id'):a.pop(key);b.pop(key)
        self.assertEqual(a,b)


if __name__=='__main__':unittest.main()
