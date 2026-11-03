"""Pure geometry and motion gates. No bpy or rendered-media substitutions."""
from __future__ import annotations
import copy
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from studio.authoring.mesh import Mesh, pants, shoe, sweater, topology
from studio.tools.build_dad_rig import hand_mesh
from studio.pipeline.contracts import ROOT, ContractError, load_json
from studio.pipeline.packages import validate_bundle, bind
from studio.pipeline.kinematics import contact_audit, finger_audit


class IndexedMeshes(unittest.TestCase):
    def test_closed_connected_garments_without_unused_vertices(self):
        for mesh in (sweater(),pants()):
            t=topology(mesh.vertices,mesh.faces)
            self.assertEqual(t['components'],1)
            self.assertEqual(t['nonmanifold_edges'],0)
            self.assertGreater(t['quad_fraction'],.99)
            self.assertEqual(set(range(len(mesh.vertices))),{v for f in mesh.faces for v in f})

    def test_each_shoe_flat_four_probes_and_closed(self):
        for sign in (-1,1):
            m,ids=shoe(sign)
            self.assertEqual(len(ids),4)
            self.assertTrue(all(m.vertices[i][2]==0 for i in ids))
            self.assertEqual(topology(m.vertices,m.faces)['components'],1)
            self.assertEqual(topology(m.vertices,m.faces)['nonmanifold_edges'],0)

    def test_five_fingers_but_six_separate_hand_surfaces_are_explicit(self):
        for sign in (-1,1):
            m,tips=hand_mesh(sign)
            self.assertEqual(set(tips),{'thumb','index','middle','ring','pinky'})
            self.assertEqual(topology(m.vertices,m.faces)['components'],6)
            self.assertEqual(topology(m.vertices,m.faces)['nonmanifold_edges'],0)
            self.assertEqual(len({b for w in m.weights for b in w}),16)

    def test_weights_normalized_and_finite(self):
        for m in (sweater(),pants(),shoe(1)[0],hand_mesh(-1)[0]):
            self.assertEqual(len(m.vertices),len(m.weights))
            for w in m.weights:
                self.assertAlmostEqual(sum(w.values()),1)
                self.assertTrue(all(math.isfinite(v) and v>0 for v in w.values()))

    def test_compact_remaps_faces_and_weights(self):
        m=Mesh()
        for i in range(4):m.vertex((i,0,0),{f'b{i}':1})
        m.faces=[(1,2,3)];m.compact()
        self.assertEqual(m.faces,[(0,1,2)])
        self.assertEqual(m.weights[0],{'b1':1})

    def test_invalid_vertex_or_weights(self):
        for xyz,w in [((0,0,float('nan')),{'a':1}),((0,0,0),{'a':-1,'b':2}),((0,0,0),{'a':float('inf')}),((0,0,0),{})]:
            with self.assertRaises(ValueError):Mesh().vertex(xyz,w)

    def test_ring_mismatch(self):
        with self.assertRaises(ValueError):Mesh().bridge([0,1,2],[3,4])

    def test_bad_face_indices_and_degenerate_face(self):
        for face in [(0,0,1),(0,1,3)]:
            with self.assertRaises(ValueError):topology([(0,0,0)]*3,[face])

    def test_recipe_deterministic(self):
        a,b=sweater(),sweater()
        self.assertEqual((a.vertices,a.faces,a.weights),(b.vertices,b.faces,b.weights))


class MeasuredContacts(unittest.TestCase):
    def setUp(self):
        self.probes=[{'id':'sole.R','ground_z':0}]
        self.contacts=[{'probe':'sole.R','frame_range':[0,3]}]
        self.rows=[{'frame':f,'contact_points_world':{'sole.R':[[.1,0,0],[-.1,0,0]]},'fingertips_local':{'index':[0,0,0]}} for f in range(3)]

    def audit(self):return contact_audit(self.rows,self.contacts,self.probes,[0,3])

    def test_stationary_sole_passes(self):self.assertTrue(self.audit()['passed'])

    def test_world_sliding_rejected(self):
        self.rows[1]['contact_points_world']['sole.R'][0][0]+=.01
        self.assertFalse(self.audit()['passed'])

    def test_yaw_slip_even_with_unchanged_centroid_rejected(self):
        self.rows[1]['contact_points_world']['sole.R']=[[0,.1,0],[0,-.1,0]]
        self.assertFalse(self.audit()['passed'])

    def test_sole_hover_rejected(self):
        for p in self.rows[1]['contact_points_world']['sole.R']:p[2]=.01
        self.assertFalse(self.audit()['passed'])

    def test_penetration_during_swing_rejected(self):
        self.contacts[0]['frame_range']=[0,1]
        self.rows[2]['contact_points_world']['sole.R'][0][2]=-.01
        self.assertFalse(self.audit()['passed'])

    def test_legitimate_clearance_outside_stance(self):
        self.contacts[0]['frame_range']=[0,1]
        self.rows[2]['contact_points_world']['sole.R'][0][2]=.1
        self.assertTrue(self.audit()['passed'])

    def test_missing_nonfinite_points_rejected(self):
        for bad in ([],[[0,0,float('nan')]]):
            self.rows[1]['contact_points_world']['sole.R']=bad
            with self.assertRaises(ContractError):self.audit()

    def test_changed_probe_count_rejected(self):
        self.rows[1]['contact_points_world']['sole.R']=[[.1,0,0]]
        with self.assertRaises(ContractError):self.audit()

    def test_missing_or_duplicate_frame_rejected(self):
        self.rows[1]['frame']=0
        with self.assertRaises(ContractError):self.audit()

    def test_overlap_or_out_of_range_stance_rejected(self):
        for span in ([0,2],[0,4]):
            self.contacts.append({'probe':'sole.R','frame_range':span})
            with self.assertRaises(ContractError):self.audit()
            self.contacts.pop()

    def test_empty_stance_not_pass(self):
        self.contacts=[]
        with self.assertRaises(ContractError):self.audit()

    def test_actual_local_finger_span_passes(self):
        self.rows[1]['fingertips_local']['index']=[0,0,.03]
        self.assertTrue(finger_audit(self.rows,[{'probe':'index','min_span_m':.025}])['passed'])

    def test_static_fingers_not_faked_by_root_motion(self):
        # World root/sole changes do not constitute finger articulation.
        self.rows[1]['contact_points_world']['sole.R'][0][0]=10
        self.assertFalse(finger_audit(self.rows,[{'probe':'index','min_span_m':.025}])['passed'])

    def test_missing_nonfinite_finger_rejected(self):
        for bad in (None,[0,0,float('inf')]):
            if bad is None:self.rows[1]['fingertips_local']={}
            else:self.rows[1]['fingertips_local']={'index':bad}
            with self.assertRaises(ContractError):finger_audit(self.rows,[{'probe':'index','min_span_m':.025}])


class RigContracts(unittest.TestCase):
    def setUp(self):
        self.p=load_json(ROOT/'studio/production/dad-rig/project.json')
        self.s=load_json(ROOT/'studio/production/dad-rig/shot.json')
        # Persisted metadata only; no .blend needed for pure contracts.
        self.a=load_json(ROOT/'studio/production/dad-rig/package-r2.json')

    def bundle(self):return validate_bundle(self.p,self.a,self.s,verify_files=False)

    def test_recorded_r2_contracts(self):self.bundle()

    def test_duplicate_probe_ids_rejected(self):
        self.a['contact_probes']*=2
        with self.assertRaises(ContractError):self.bundle()

    def test_unknown_stance_probe_rejected(self):
        self.s['contacts'][0]['probe']='unknown'
        with self.assertRaises(ContractError):self.bundle()

    def test_contact_interval_outside_shot_rejected(self):
        self.s['contacts'][0]['frame_range']=[0,73]
        with self.assertRaises(ContractError):self.bundle()

    def test_overlapping_contact_interval_rejected(self):
        self.s['contacts'].append(copy.deepcopy(self.s['contacts'][0]))
        with self.assertRaises(ContractError):self.bundle()

    def test_unknown_finger_probe_rejected(self):
        self.s['finger_checks'][0]['probe']='unknown'
        with self.assertRaises(ContractError):self.bundle()

    def test_duplicate_vertex_indices_rejected(self):
        self.a['contact_probes'][0]['vertex_indices']=[0,0]
        with self.assertRaises(ContractError):self.bundle()

    def test_dependencies_must_match_real_bytes(self):
        self.a['provenance']['dependencies'][0]['sha256']='f'*64
        # Other absent generated files may also reject; the dependency is
        # isolated below using a tiny real fixture, not claimed as a blend.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'asset').write_text('unit fixture');(root/'builder').write_text('unit fixture')
            from studio.pipeline.contracts import file_hash
            self.a['blend'].update(path='asset',sha256=file_hash(root/'asset'))
            self.a['provenance'].update(authoring_script='builder',script_sha256=file_hash(root/'builder'),dependencies=[{'path':'missing','sha256':'f'*64}])
            with self.assertRaises(ContractError):validate_bundle(self.p,self.a,self.s,root=root)

    def test_probe_refuses_topology_changing_modifier(self):
        probe=self.a['contact_probes'][0]
        obj=SimpleNamespace(type='MESH',data=SimpleNamespace(vertices=list(range(200))),modifiers=[SimpleNamespace(type='SUBSURF')])
        with self.assertRaisesRegex(ContractError,'topology-preserving'):
            bind({probe['object']:obj},{'bindings':{},'ik_checks':[],'contact_probes':[probe]})

    def test_probe_index_outside_mesh(self):
        probe=self.a['contact_probes'][0]
        obj=SimpleNamespace(type='MESH',data=SimpleNamespace(vertices=[]),modifiers=[])
        with self.assertRaisesRegex(ContractError,'out-of-range'):
            bind({probe['object']:obj},{'bindings':{},'ik_checks':[],'contact_probes':[probe]})

    def test_missing_hand_reference_bone(self):
        probe=self.a['fingertip_probes'][0]
        obj=SimpleNamespace(type='MESH',data=SimpleNamespace(vertices=list(range(2000))),modifiers=[])
        with self.assertRaisesRegex(ContractError,'reference bone'):
            bind({probe['object']:obj},{'bindings':{},'ik_checks':[],'fingertip_probes':[probe]})

    def test_camera_scale_must_be_positive(self):
        self.p['camera']={'position':[0,7,2],'target':[0,0,1.4],'ortho_scale':0}
        with self.assertRaises(ContractError):self.bundle()


if __name__=='__main__':unittest.main()
