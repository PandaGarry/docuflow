"""Numerical safety of authored deformation, never art/likeness approval."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model


class HeadCageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec,cls.vertices,cls.cage=model.load_cage()

    def test_controls_interpolated(self):
        np.testing.assert_allclose(self.cage(self.cage.centers),self.cage.centers+self.cage.displacements,atol=1e-12,rtol=0)

    def test_identity_outside_compact_support(self):
        points=np.array([[0,0,0],[1,2,3],[-2,1,0]])
        np.testing.assert_array_equal(self.cage(points),points)

    def test_no_eye_only_iris_trick_or_a7_stack_in_spec(self):
        self.assertIn('official Rain',self.spec['base'])
        self.assertIn('NOT stacked',self.spec['base'])
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])
        self.assertGreaterEqual(len(self.spec['controls']),70)
        self.assertTrue(all(isinstance(c['source_vertex'],int) for c in self.spec['controls']))

    def test_mirror_symmetry(self):
        points=self.vertices[::7];mirror=points*np.array([-1,1,1])
        np.testing.assert_allclose(self.cage(points)*[-1,1,1],self.cage(mirror),atol=2e-6,rtol=0)

    def test_analytic_jacobian(self):
        points=self.vertices[::317];analytic=self.cage.jacobians(points);h=1e-6
        for axis in range(3):
            delta=np.zeros(3);delta[axis]=h
            numeric=(self.cage(points+delta)-self.cage(points-delta))/(2*h)
            np.testing.assert_allclose(analytic[:,:,axis],numeric,atol=1e-7,rtol=1e-6)

    def test_sampled_no_folds_not_anatomy_approval(self):
        report=model.inspect_cage()
        self.assertGreater(report['min_sampled_jacobian_determinant'],0)
        self.assertLess(report['maximum_basis_change_m'],.04)
        self.assertIn('not continuous',report['scope'])

    def test_fixed_neck_cranium_ear_constraints(self):
        for control in self.spec['controls']:
            if 'boundary' in control['purpose']:
                np.testing.assert_allclose(control['source_world_m'],control['target_world_m'],atol=1e-10,rtol=0)

    def test_invalid_inputs_rejected(self):
        for radius in (0,-1,float('nan')):
            with self.assertRaises(ValueError):model.ControlCage([[0,0,0]],[[0,0,0]],radius)
        with self.assertRaises(ValueError):model.ControlCage([[0,0,0],[0,0,0]],[[0,0,0],[1,0,0]],1)
        with self.assertRaises(ValueError):self.cage([[float('nan'),0,0]])

    def test_kernel_support_and_center(self):
        np.testing.assert_array_equal(model.kernel([0,1,2]),[1,0,0])

    def test_lip_chin_not_previous_a7_shortening(self):
        by_name={c['name']:c for c in self.spec['controls']}
        self.assertLess(by_name['chin-tip']['target_world_m'][2],by_name['chin-tip']['source_world_m'][2])
        self.assertLess(by_name['brow-arch.L']['target_world_m'][2],by_name['brow-arch.L']['source_world_m'][2])


if __name__=='__main__':
    unittest.main()
