"""Pure R8 anatomy intent and original-UV rasterizer; not likeness approval."""
import hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_face_paint_r8 as paint
import mom_head_cage as model

class FacePaintR8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec,cls.vertices,cls.cage=model.load_cage(ROOT/'studio/authoring/mom-head-form-r8.json')
        cls.old,_,cls.previous=model.load_cage(ROOT/'studio/authoring/mom-head-form-r7.json')

    def test_only_declared_anatomical_targets_changed(self):
        deltas=self.spec['revision_deltas_from_r7_m']
        for a,b in zip(self.old['controls'],self.spec['controls']):
            np.testing.assert_allclose(np.array(b['target_world_m'])-a['target_world_m'],deltas.get(a['name'],[0,0,0]),atol=1e-12)
            self.assertEqual(a['source_vertex'],b['source_vertex'])
        self.assertEqual(self.old['brow_curve'],self.spec['brow_curve'])
        self.assertEqual(self.old['ear_finish'],self.spec['ear_finish'])
        self.assertFalse(any('lid' in n or 'canthus' in n or 'brow' in n for n in deltas))
        self.assertEqual(self.spec['palette_srgb']['skin'],'#E8B48F')

    def test_pair_symmetry_and_real_feature_movement(self):
        d=self.spec['revision_deltas_from_r7_m']
        for name,delta in d.items():
            if name.endswith('.L'):np.testing.assert_allclose(d[name[:-1]+'R'],[-delta[0],delta[1],delta[2]])
        self.assertGreater(d['mouth-seam'][2],.002)
        self.assertGreater(d['tip'][2],.002);self.assertLess(d['tip'][1],0)
        self.assertLess(d['malar-front.L'][1],0)
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])

    def test_sampled_cage_safe_and_not_a_color_only_revision(self):
        self.assertGreater(float(np.linalg.det(self.cage.jacobians(self.vertices)).min()),.3)
        difference=float(np.linalg.norm(self.cage(self.vertices)-self.previous(self.vertices),axis=1).max())
        self.assertGreater(difference,.003);self.assertLess(difference,.004)

    def test_surface_color_boundary_not_a_vertex_resolution_limit(self):
        palette=self.spec['palette_srgb']
        p=np.array([[0,-.16,1.4035],[0,-.16,1.4020],[0,-.16,1.3815]])
        colors,rough=paint.paint_samples(p,np.array([1,1,0]),np.array([0,0,1]),palette)
        self.assertTrue(np.isfinite(colors).all());np.testing.assert_array_equal(colors[:,3],1)
        self.assertGreater(float(rough[0,0]),float(rough[1,0]))
        np.testing.assert_allclose(colors[2,:3],paint.linear(palette['lower_lip']),atol=1e-7)
        self.assertGreaterEqual(float(colors.min()),0);self.assertLessEqual(float(colors.max()),1)

    def test_original_uv_triangle_rasterization(self):
        p=np.array([[-.01,-.16,1.389],[.01,-.16,1.389],[.01,-.16,1.405],[-.01,-.16,1.405]])
        uv=np.array([[0,0],[1,0],[1,1],[0,1]])
        tri=np.array([[0,1,2],[0,2,3]])
        a,r,receipt=paint.rasterize(p,uv,tri,tri,np.ones(4),np.zeros(4),self.spec['palette_srgb'],32)
        self.assertEqual(a.shape,(32,32,4));self.assertEqual(receipt['covered_texels'],1024)
        self.assertEqual(receipt['rasterized_triangles'],2)
        self.assertTrue(np.isfinite(a).all());self.assertTrue(np.isfinite(r).all())
        np.testing.assert_array_equal(a[:,:,3],1)
        # Bottom-left image origin: the upper rows are above pigment border.
        self.assertGreater(float(r[-1,16,0]),float(r[0,16,0]))

    def test_unsupported_uv_layout_rejected(self):
        p=np.zeros((3,3));tri=np.array([[0,1,2]])
        for uv in (np.array([[0,0],[2,0],[0,1]]),np.full((3,2),np.nan)):
            with self.assertRaises(ValueError):paint.rasterize(p,uv,tri,tri,np.zeros(3),np.zeros(3),self.spec['palette_srgb'],16)
        with self.assertRaises(ValueError):paint.rasterize(p,np.zeros((3,2)),tri,tri,np.zeros(3),np.zeros(3),self.spec['palette_srgb'],8192)

    def test_island_padding_does_not_wrap_at_image_border(self):
        image=np.zeros((12,12,4),dtype=np.float32);mask=np.zeros((12,12),dtype=bool)
        image[5,0]=1;mask[5,0]=True
        result=paint.pad_islands(image,mask,2)
        np.testing.assert_array_equal(result[:,11],0)
        np.testing.assert_array_equal(result[5,2],1)

    def test_historical_native_recipes_stay_frozen(self):
        report=json.loads((ROOT/'studio/reviews/mom-head-form-r7/report.json').read_text())
        for name,digest in report['scripts'].items():
            self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main()
