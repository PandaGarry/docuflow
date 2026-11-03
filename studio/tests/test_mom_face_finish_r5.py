"""R5 actual-mesh ear and palette intent. Not a likeness/film-quality gate."""
import gzip
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_finish_r5 as finish
import mom_head_cage as model


class FaceFinishR5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec,cls.vertices,cls.cage=model.load_cage(ROOT/'studio/authoring/mom-head-form-r5.json')
        cls.data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']

    def test_ears_smaller_without_shrinking_other_face(self):
        p=self.cage(self.vertices);q=finish.finish_ears(p,self.data,self.spec['ear_finish'])
        np.testing.assert_array_equal(p[np.abs(self.vertices[:,0])<=.091],q[np.abs(self.vertices[:,0])<=.091])
        self.assertGreater(p[:,0].max()-q[:,0].max(),.007)
        self.assertLess(p[:,0].max()-q[:,0].max(),.009)
        self.assertLess(float(np.linalg.norm(q-p,axis=1).max()),.009)
        self.assertTrue(np.isfinite(q).all())

    def test_ear_map_is_affine_per_vertex_for_key_transport(self):
        p=self.cage(self.vertices);offset=np.ones_like(p)*.0003
        f=lambda x:finish.finish_ears(x,self.data,self.spec['ear_finish'])
        np.testing.assert_allclose(f(p+offset)-f(p),f(p+2*offset)-f(p+offset),atol=1e-15)

    def test_no_oriented_head_triangle_reversal_in_ear_finish(self):
        p=self.cage(self.vertices);q=finish.finish_ears(p,self.data,self.spec['ear_finish'])
        triangles=np.array([(p[0],p[i],p[i+1]) for p in self.data['polygons'] for i in range(1,len(p)-1)])
        def cross(v):
            a,b,c=v[triangles].transpose(1,0,2);return np.cross(b-a,c-a)
        a=cross(p);b=cross(q);valid=np.linalg.norm(a,axis=1)>1e-12
        self.assertGreater(float((np.sum(a[valid]*b[valid],axis=1)/np.sum(a[valid]**2,axis=1)).min()),.5)

    def test_lips_are_attached_anatomical_mask_not_rectangular_paint(self):
        colors,mask=finish.complexion_colors(self.data,self.spec['palette_srgb'])
        self.assertEqual(colors.shape,(6395,4));self.assertEqual(colors.dtype,np.float32)
        self.assertTrue(np.isfinite(colors).all());self.assertGreaterEqual(float(colors.min()),0)
        self.assertLessEqual(float(colors.max()),1)
        self.assertEqual(mask[3150],1);self.assertEqual(mask[6343],1)
        for index in (3156,6375,6374):self.assertEqual(mask[index],0)
        self.assertGreater(mask[55],.4);self.assertLess(mask[69],.3)

    def test_palette_and_unchanged_eye_brow_design(self):
        self.assertEqual(self.spec['palette_srgb']['skin'],'#E8B48F')
        self.assertEqual(self.spec['palette_srgb']['iris'],'#73879A')
        old=json.loads((ROOT/'studio/authoring/mom-head-form-r4.json').read_text())
        self.assertEqual(self.spec['brow_curve'],old['brow_curve'])
        for a,b in zip(old['controls'],self.spec['controls']):
            if any(key in a['name'] for key in ('lid','canthus','brow')):self.assertEqual(a,b)
        self.assertEqual(self.spec['portrait_smile_amount'],.4)
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])

    def test_cage_sample_safety_and_srgb_transfer(self):
        self.assertGreater(float(np.linalg.det(self.cage.jacobians(self.vertices)).min()),.4)
        np.testing.assert_allclose(finish.linear('#FFFFFF'),[1,1,1])
        np.testing.assert_allclose(finish.linear('#000000'),[0,0,0])
        np.testing.assert_allclose(finish.linear('#808080'),[.2158605]*3,atol=1e-7)


if __name__=='__main__':unittest.main()
