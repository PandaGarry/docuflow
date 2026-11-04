"""R11 anatomical bindings and geometry-only revision; not a likeness score."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_head_surface_r2 as surface
import mom_face_paint_r10 as old_paint
import mom_face_paint_r11 as paint

class HeadR11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old,cls.v,cls.a=model.load_cage(ROOT/'studio/authoring/mom-head-form-r10.json')
        cls.spec,_,cls.b=model.load_cage(ROOT/'studio/authoring/mom-head-form-r11.json')
        cls.data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']

    def test_six_existing_oral_targets_only_no_corner_or_nose_reset(self):
        d=self.spec['revision_deltas_from_r10_m'];self.assertEqual(len(d),6)
        self.assertEqual(len(self.spec['controls']),85)
        for a,b in zip(self.old['controls'],self.spec['controls'][:83]):
            self.assertEqual(a['source_vertex'],b['source_vertex']);self.assertEqual(a['name'],b['name'])
            np.testing.assert_allclose(np.array(b['target_world_m'])-a['target_world_m'],d.get(a['name'],[0,0,0]),atol=1e-12)
        for key in ('ear_finish','brow_curve','palette_srgb','portrait_smile_amount'):self.assertEqual(self.old[key],self.spec[key])
        self.assertNotIn('mouth-corner.L',d)
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])

    def test_new_transition_anchors_are_exterior_not_inner_mouth(self):
        n=surface.vertex_normals(self.v,self.data['polygons'])
        self.assertEqual(len(self.spec['added_controls_from_r10']),2)
        for authored,control in zip(self.spec['added_controls_from_r10'],self.spec['controls'][83:]):
            index=control['source_vertex'];self.assertIn(index,(6368,3117));self.assertLess(n[index,1],-.5)
            self.assertNotIn(index,(3112,3113))
            baseline=self.a(self.v[[index]])[0]
            np.testing.assert_allclose(baseline,authored['r10_baseline_world_m'],atol=1e-12)
            np.testing.assert_allclose(control['target_world_m'],baseline+authored['delta_m'],atol=5.1e-10,rtol=0)
            self.assertLess(authored['delta_m'][1],0)

    def test_upper_lower_projection_balance_not_another_lower_lip_shrink(self):
        a={c['name']:np.array(c['target_world_m']) for c in self.old['controls']}
        b={c['name']:np.array(c['target_world_m']) for c in self.spec['controls']}
        old=a['lower-lip-volume'][1]-a['upper-lip-center'][1]
        new=b['lower-lip-volume'][1]-b['upper-lip-center'][1]
        self.assertGreater(new,0);self.assertLess(new,old*.5)
        self.assertEqual(a['lower-lip-volume'][2],b['lower-lip-volume'][2])
        d=self.spec['revision_deltas_from_r10_m'];np.testing.assert_allclose(d['cupid-peak.L'],d['cupid-peak.R'])
        self.assertEqual(self.spec['portrait_smile_amount'],.4)

    def test_sampled_nonfolding_bounded_and_exact_interpolation(self):
        self.assertGreater(float(np.linalg.det(self.b.jacobians(self.v)).min()),.15)
        change=float(np.linalg.norm(self.b(self.v)-self.a(self.v),axis=1).max())
        self.assertGreater(change,.0025);self.assertLess(change,.003)
        np.testing.assert_allclose(self.b(self.b.centers)-self.b.centers,self.b.displacements,atol=1e-12)
        tri=np.array([[face[0],face[i],face[i+1]] for face in self.data['polygons'] for i in range(1,len(face)-1)])
        a=self.a(self.v)[tri];b=self.b(self.v)[tri]
        na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0])
        valid=np.linalg.norm(na,axis=1)>1e-12
        self.assertTrue((np.einsum('ij,ij->i',na[valid],nb[valid])>0).all())

    def test_material_samples_bitwise_identical_to_r10(self):
        top=paint.group_sum(self.data,('DEF-Lip_Top_',));bottom=paint.group_sum(self.data,('DEF-Lip_Bot_',))
        a,r=old_paint.paint_samples(self.v,top,bottom,self.old['palette_srgb'])
        b,s=paint.paint_samples(self.v,top,bottom,self.spec['palette_srgb'])
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(r,s)
        self.assertEqual(paint.atlas_domain(np.array([[2.01,.01],[2.99,.99]])),old_paint.atlas_domain(np.array([[2.01,.01],[2.99,.99]])))

    def test_frozen_r10_native_and_held_light_recipes(self):
        for path in ('studio/reviews/mom-head-form-r10/report.json','studio/reviews/mom-head-lookdev-r10/report.json'):
            r=json.loads((ROOT/path).read_text())
            if 'scripts' in r:
                for name,digest in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
            else:self.assertEqual(hashlib.sha256((ROOT/'studio/tools/mom_head_lookdev_r10.py').read_bytes()).hexdigest(),r['script_sha256'])

if __name__=='__main__':unittest.main()
