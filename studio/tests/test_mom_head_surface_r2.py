"""R2 surface binding/math checks; not identity or anatomical approval."""
from pathlib import Path
import gzip
import json
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as cage
import mom_head_surface_r2 as surface


class HeadSurfaceR2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec,cls.vertices,cls.cage=cage.load_cage(ROOT/'studio/authoring/mom-head-form-r2.json')
        cls.polygons=json.loads(gzip.decompress(cage.DATA.read_bytes()))['official-source']['polygons']

    def test_exact_controls_and_sampled_safety(self):
        np.testing.assert_allclose(self.cage(self.cage.centers),self.cage.centers+self.cage.displacements,atol=1e-12,rtol=0)
        self.assertGreater(float(np.linalg.det(self.cage.jacobians(self.vertices)).min()),0)

    def test_lip_controls_really_on_external_surface(self):
        normals=surface.vertex_normals(self.vertices,self.polygons);checked=[]
        for control in self.spec['controls']:
            if control.get('binding_kind')=='verified outward-facing lip surface':
                self.assertLess(normals[control['source_vertex'],1],-.25);checked.append(control['name'])
        self.assertIn('upper-lip-center',checked);self.assertIn('lower-lip-volume',checked)
        self.assertNotIn(3147,[c['source_vertex'] for c in self.spec['controls']])
        self.assertNotIn(3115,[c['source_vertex'] for c in self.spec['controls']])

    def test_front_ray_chooses_first_surface_not_inside(self):
        vertices=np.array([[-1,-2,-1],[1,-2,-1],[1,-2,1],[-1,-2,1],[-1,0,-1],[1,0,-1],[1,0,1],[-1,0,1]])
        np.testing.assert_allclose(surface.front_surface_y([[0,99,0]],vertices,[[0,1,2,3],[4,5,6,7]]),[-2])
        with self.assertRaises(ValueError):surface.front_surface_y([[5,0,0]],vertices,[[0,1,2,3]])

    def test_brow_curve_interpolates_and_no_overshoot(self):
        settings=self.spec['brow_curve'];x=settings['abscissae_m'];y=settings['heights_m']
        np.testing.assert_allclose(surface.cubic_curve(x,x,y),y,atol=1e-12,rtol=0)
        values=surface.cubic_curve(np.linspace(x[0],x[-1],501),x,y)
        self.assertGreaterEqual(values.min(),min(y)-1e-12);self.assertLessEqual(values.max(),max(y)+1e-12)

    def test_brow_curve_c1_at_inner_knots(self):
        settings=self.spec['brow_curve'];x=settings['abscissae_m'];y=settings['heights_m'];h=1e-7
        for point in x[1:-1]:
            left=(surface.cubic_curve(point,x,y)-surface.cubic_curve(point-h,x,y))/h
            right=(surface.cubic_curve(point+h,x,y)-surface.cubic_curve(point,x,y))/h
            self.assertAlmostEqual(float(left),float(right),places=4)

    def test_brow_geometry_attaches_above_real_surface(self):
        x=np.repeat(np.linspace(.023,.085,20),2);z=1.518-4*(x-.05)**2+np.tile([-.002,.002],20)
        original=np.column_stack((x,-.15+4*(x-.02)**2,z))
        head=self.cage(self.vertices);changed=surface.author_brows(original,head,self.polygons,self.spec['brow_curve'])
        projected=surface.front_surface_y(changed,head,self.polygons)
        offsets=projected-changed[:,1]
        self.assertTrue(np.isfinite(changed).all());self.assertGreaterEqual(offsets.min(),.0007-1e-10)
        self.assertLessEqual(offsets.max(),.0032+1e-10)


if __name__=='__main__':
    unittest.main()
