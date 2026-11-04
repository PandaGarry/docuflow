"""A shared key value must not justify mixing different actuator axes."""
import sys
from pathlib import Path
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_controls as controls
import mom_head_cage as model


class FaceControlTests(unittest.TestCase):
    def test_common_axis_and_final_bilateral_readback(self):
        state={'L':0.,'R':0.};axes=[]
        def evaluate(side,axis,value):
            axes.append(axis);return value*80 if axis==2 else value*40
        def commit(side,axis,value):state[side]=value*80;axes.append(axis)
        result=controls.calibrate_pair(evaluate,commit,lambda s:state[s],.6)
        self.assertEqual(set(axes),{2});self.assertAlmostEqual(state['L'],state['R'])
        self.assertTrue(all(abs(v-.6)<1e-4 for v in result['final_key_values'].values()))

    def test_coupled_final_readback_is_not_silently_accepted(self):
        state={'L':0.,'R':0.}
        def commit(side,axis,value):
            state[side]=value*80
            if side=='R':state['L']=0
        with self.assertRaises(ValueError):controls.calibrate_pair(lambda s,a,v:v*80,commit,lambda s:state[s],.6)

    def test_invalid_axis(self):
        with self.assertRaises(ValueError):controls.calibrate_pair(None,None,None,.6,4)

    def test_r3_changes_only_three_authored_lip_targets(self):
        a,v,c2=model.load_cage(ROOT/'studio/authoring/mom-head-form-r2.json')
        b,_,c3=model.load_cage(ROOT/'studio/authoring/mom-head-form-r3.json')
        changed=[x['name'] for x,y in zip(a['controls'],b['controls']) if x!=y]
        self.assertEqual(set(changed),{'cupid-peak.L','cupid-peak.R','upper-lip-border'})
        self.assertEqual(a['brow_curve'],b['brow_curve'])
        self.assertLess(float(np.linalg.norm(c2(v)-c3(v),axis=1).max()),.002)
        self.assertGreater(float(np.linalg.det(c3.jacobians(v)).min()),0)


if __name__=='__main__':unittest.main()
