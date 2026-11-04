"""R12 coordinated design/bindings/geometry safety. NOT a beauty/likeness gate."""
import gzip,hashlib,json,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_head_cage as model
import mom_head_surface_r2 as surface
import mom_face_paint_r11 as oldpaint
import mom_face_paint_r12 as paint

class HeadR12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old,cls.v,cls.a=model.load_cage(ROOT/'studio/authoring/mom-head-form-r11.json')
        cls.spec,_,cls.b=model.load_cage(ROOT/'studio/authoring/mom-head-form-r12.json')
        cls.data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
        cls.before=oldpaint.finish_ears(cls.a(cls.v),cls.data,cls.old['ear_finish'])
        cls.after=paint.finish_ears(cls.b(cls.v),cls.data,cls.spec['ear_finish'])

    def test_coordinated_not_another_six_target_lip_only_pass(self):
        d=self.spec['revision_deltas_from_r11_m'];self.assertEqual(len(d),24);self.assertEqual(len(self.spec['controls']),87)
        for a,b in zip(self.old['controls'],self.spec['controls']):
            self.assertEqual(a['source_vertex'],b['source_vertex'])
            np.testing.assert_allclose(np.array(b['target_world_m'])-a['target_world_m'],d.get(a['name'],[0,0,0]),atol=1e-12)
        self.assertTrue(all(k in d for k in ('tip','bridge-low','mouth-seam','upper-lip-border','chin-tip')))
        self.assertEqual(self.spec['brow_curve'],self.old['brow_curve']);self.assertEqual(self.spec['portrait_smile_amount'],.4)
        self.assertFalse(self.spec['art_approved']);self.assertFalse(self.spec['production_swap_allowed'])

    def test_mouth_down_and_nose_cap_less_pointed_from_measured_design(self):
        old={c['name']:np.array(c['target_world_m']) for c in self.old['controls']};new={c['name']:np.array(c['target_world_m']) for c in self.spec['controls']}
        self.assertAlmostEqual(new['mouth-seam'][2]-old['mouth-seam'][2],-.005)
        self.assertAlmostEqual(new['tip'][1]-old['tip'][1],.005)
        self.assertLess(new['tip-shoulder.L'][1]-new['tip'][1],.0011)
        self.assertGreater(old['tip-shoulder.L'][1]-old['tip'][1],.004)
        r=json.loads((ROOT/'studio/authoring/mom-r12-design-review.json').read_text())
        self.assertGreater(r['reference_normalized_vertical_from_eyes']['upper_vermilion_center'],r['r11_projection']['normalized_vertical_from_eyes']['upper_surface6333'])
        self.assertAlmostEqual(new['columella'][2],old['columella'][2])

    def test_true_contact_corners_are_not_upper_border69(self):
        n=surface.vertex_normals(self.v,self.data['polygons']);added=self.spec['controls'][85:]
        self.assertEqual([a['source_vertex'] for a in added],[1406,4601])
        for a in added:self.assertLess(n[a['source_vertex'],1],-.5)
        np.testing.assert_allclose(added[0]['target_world_m'][1:],added[1]['target_world_m'][1:],atol=3e-7)
        self.assertEqual(added[0]['target_world_m'][0],-added[1]['target_world_m'][0])
        seam=next(c for c in self.spec['controls'] if c['name']=='mouth-seam')['target_world_m'][2]
        self.assertAlmostEqual(added[0]['target_world_m'][2]-seam,.0036)

    def test_ears_adduct_and_reduce_projection_without_moving_central_face(self):
        self.assertEqual(self.spec['ear_finish']['adduction_degrees'],30)
        self.assertLess(float(abs(self.after[:,0]).max()),float(abs(self.before[:,0]).max())-.011)
        cage=self.b(self.v);central=np.abs(self.v[:,0])<.087
        np.testing.assert_array_equal(self.after[central],cage[central])
        mask=paint.ear_mask(self.data);self.assertTrue(np.isfinite(mask).all());self.assertGreater((mask>.9).sum(),10)
        self.assertLess(float(np.linalg.norm(self.after-self.before,axis=1).max()),.022)
        self.assertGreater(float(np.linalg.norm(self.after-self.before,axis=1).max()),.020)

    def test_no_sampled_cage_fold_or_reversed_surface_triangles(self):
        self.assertGreater(float(np.linalg.det(self.b.jacobians(self.v)).min()),.05)
        np.testing.assert_allclose(self.b(self.b.centers)-self.b.centers,self.b.displacements,atol=1e-12)
        tri=np.array([[f[0],f[j],f[j+1]] for f in self.data['polygons'] for j in range(1,len(f)-1)])
        a=self.before[tri];b=self.after[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12
        self.assertTrue((np.einsum('ij,ij->i',na[valid],nb[valid])>0).all())

    def test_palette_and_material_evaluation_held_not_rebaked(self):
        self.assertEqual(self.spec['palette_srgb'],self.old['palette_srgb'])
        self.assertIs(paint.paint_samples,oldpaint.paint_samples);self.assertIs(paint.saved_material_state,oldpaint.saved_material_state)
        self.assertFalse(hasattr(paint,'rasterize'))
        r=json.loads((ROOT/'studio/authoring/mom-r12-design-review.json').read_text())
        self.assertEqual(r['reference']['sha256'],hashlib.sha256((ROOT/r['reference']['path']).read_bytes()).hexdigest())

    def test_frozen_previous_recipes_remain_unchanged(self):
        for rev in (10,11):
            r=json.loads((ROOT/f'studio/reviews/mom-head-form-r{rev}/report.json').read_text())
            for name,digest in r['scripts'].items():self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main()
