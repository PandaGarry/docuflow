"""A3 edit-map contracts, not numerical likeness or animation approval."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import rain_mom_pass_a3 as face


class RainFaceTests(unittest.TestCase):
    def test_finite_bounded_field(self):
        points=np.stack(np.meshgrid(np.linspace(-.18,.18,35),np.linspace(-.17,.14,11),np.linspace(1.28,1.72,45)),axis=-1).reshape(-1,3)
        changed=face.face_field(points)
        self.assertTrue(np.isfinite(changed).all())
        self.assertLess(np.linalg.norm(changed-points,axis=1).max(),.025)

    def test_field_symmetry(self):
        rng=np.random.default_rng(42)
        p=rng.uniform([-.18,-.17,1.28],[.18,.14,1.72],size=(1000,3))
        other=p.copy();other[:,0]*=-1
        q=face.face_field(p);q[:,0]*=-1
        np.testing.assert_allclose(q,face.face_field(other),atol=1e-12)

    def test_nose_is_narrower_shorter_and_upturned(self):
        p=np.array([[.020,-.120,1.425]])
        q=face.face_field(p)
        self.assertLess(q[0,0],p[0,0]);self.assertGreater(q[0,1],p[0,1]);self.assertGreater(q[0,2],p[0,2])

    def test_lips_wider_less_pout(self):
        p=np.array([[.025,-.1,1.389]])
        q=face.face_field(p)
        self.assertGreater(q[0,0],p[0,0]);self.assertGreater(q[0,1],p[0,1]);self.assertGreater(q[0,2],p[0,2])

    def test_eye_centers_not_arbitrarily_respaced(self):
        p=np.array([[-.047,-.1,1.472],[.047,-.1,1.472]])
        self.assertLess(np.linalg.norm(face.face_field(p)-p,axis=1).max(),.0005)

    def test_no_body_redesign_in_face_pass(self):
        p=np.array([[.1,-.08,.9],[.13,-.05,.6],[.6,0,1.2],[0,0,.1]])
        np.testing.assert_allclose(face.face_field(p),p,atol=1e-7)

    def test_dense_local_jacobians_remain_positive(self):
        points=np.stack(np.meshgrid(np.linspace(-.15,.15,41),np.linspace(-.15,.05,11),np.linspace(1.32,1.57,41)),axis=-1).reshape(-1,3)
        columns=[]
        for axis in range(3):
            delta=np.zeros((1,3));delta[0,axis]=1e-6
            columns.append((face.face_field(points+delta)-face.face_field(points-delta))/2e-6)
        determinants=np.linalg.det(np.stack(columns,axis=2))
        self.assertTrue(np.isfinite(determinants).all())
        self.assertGreater(determinants.min(),.20)

    def test_no_midline_discontinuity(self):
        p=np.array([[-1e-8,-.12,1.47],[0,-.12,1.47],[1e-8,-.12,1.47]])
        q=face.face_field(p)
        self.assertLess(np.linalg.norm(q[2]-q[0]),1e-7)


if __name__=='__main__':
    unittest.main()
