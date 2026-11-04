"""R10 local oral form and independently packed surface responses; not likeness."""
import hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_face_paint_r10 as paint

class FacePaintR10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old,cls.v,cls.a=model.load_cage(ROOT/'studio/authoring/mom-head-form-r9.json')
        cls.spec,_,cls.b=model.load_cage(ROOT/'studio/authoring/mom-head-form-r10.json')

    def test_only_eight_declared_oral_targets_changed(self):
        d=self.spec['revision_deltas_from_r9_m'];self.assertEqual(len(d),8)
        for a,b in zip(self.old['controls'],self.spec['controls']):
            self.assertEqual(a['source_vertex'],b['source_vertex']);self.assertEqual(a['name'],b['name'])
            np.testing.assert_allclose(np.array(b['target_world_m'])-a['target_world_m'],d.get(a['name'],[0,0,0]),atol=1e-12)
        for key in ('ear_finish','brow_curve','portrait_smile_amount'):self.assertEqual(self.old[key],self.spec[key])
        self.assertEqual(self.spec['palette_srgb']['skin'],'#E8B48F')
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])

    def test_corner_lift_and_projection_not_stronger_smile_actuator(self):
        d=self.spec['revision_deltas_from_r9_m']
        self.assertGreater(d['mouth-corner.L'][2],d['mouth-seam'][2])
        self.assertGreater(d['lower-lip-volume'][1],.002)
        self.assertGreater(d['lower-lip-volume'][2],.002)
        for name,delta in d.items():
            if name.endswith('.L'):np.testing.assert_allclose(d[name[:-1]+'R'],[-delta[0],delta[1],delta[2]])
        self.assertEqual(self.spec['portrait_smile_amount'],.4)

    def test_sampled_nonfolding_exact_and_bounded_revision(self):
        self.assertGreater(float(np.linalg.det(self.b.jacobians(self.v)).min()),.15)
        change=np.linalg.norm(self.b(self.v)-self.a(self.v),axis=1).max()
        self.assertGreater(float(change),.003);self.assertLess(float(change),.004)
        np.testing.assert_allclose(self.b(self.b.centers)-self.b.centers,self.b.displacements,atol=1e-12)

    def test_localized_pbr_channels_and_warmer_lower_vermilion(self):
        p=np.array([[0,-.16,1.399],[0,-.16,1.3815],[.06,-.14,1.43]])
        albedo,pbr=paint.paint_samples(p,np.array([1,0,0]),np.array([0,1,0]),self.spec['palette_srgb'])
        np.testing.assert_allclose(pbr[0,:3],[.4,.05,.22],atol=1e-7)
        np.testing.assert_allclose(pbr[1,:3],[.29,.17,.22],atol=1e-7)
        np.testing.assert_allclose(pbr[2,:3],[.47,0,.22],atol=1e-7)
        np.testing.assert_allclose(albedo[1,:3],paint.linear('#E17A60'),atol=1e-7)
        for value in (albedo,pbr):
            self.assertTrue(np.isfinite(value).all());self.assertGreaterEqual(value.min(),0);self.assertLessEqual(value.max(),1)
            np.testing.assert_array_equal(value[:,3],1)

    def test_original_tile1003_uniform_domain_rasterization_preserves_channels(self):
        p=np.array([[-.01,-.16,1.38],[.01,-.16,1.38],[.01,-.16,1.405],[-.01,-.16,1.405]])
        uv=np.array([[0,0],[1,0],[1,1],[0,1]],dtype=float);tri=np.array([[0,1,2],[0,2,3]])
        original=uv+[2,0];snapshot=original.copy();args=(tri,tri,np.ones(4),np.zeros(4),self.spec['palette_srgb'],32)
        a,r,_=paint.rasterize(p,uv,*args)
        b,s,_=paint.rasterize(p,original,*args,domain={'origin':[2,0],'extent':1})
        np.testing.assert_allclose(a,b);np.testing.assert_allclose(r,s);np.testing.assert_array_equal(original,snapshot)
        self.assertGreater(r[0,16,1],r[-1,16,1])
        np.testing.assert_allclose(r[:,:,2],.22)
        with self.assertRaises(ValueError):paint.rasterize(p,original,*args)

    def test_frozen_r9_recipe_not_rewritten_to_hide_history(self):
        r=json.loads((ROOT/'studio/reviews/mom-head-form-r9/report.json').read_text())
        for name,digest in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(hashlib.sha256((ROOT/'studio/authoring/mom-head-form-r9.json').read_bytes()).hexdigest(),r['spec_sha256'])

if __name__=='__main__':unittest.main()
