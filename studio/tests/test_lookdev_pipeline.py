"""R4 geometry/contract regressions. Passing is not artistic acceptance."""
from __future__ import annotations
import math
import unittest
from studio.authoring import lookdev as f
from studio.authoring.mesh import topology
from studio.authoring.refined_body import hand as previous_hand
from studio.pipeline.contracts import ROOT, file_hash, load_json
from studio.pipeline.packages import validate_bundle
from studio.tools.render_lookdev import project, VIEWS


def unscale(p):
    return (p[0]/f.HEAD_SCALE[0],p[1]/f.HEAD_SCALE[1],
            f.HEAD_PIVOT_Z+(p[2]-f.HEAD_PIVOT_Z)/f.HEAD_SCALE[2])


class LookdevForms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.head,cls.colors,cls.masks=f.head()
        cls.hands={s:f.hand(s) for s in (-1,1)}

    def test_head_closed_single_component(self):
        t=topology(self.head.vertices,self.head.faces)
        self.assertEqual(t['components'],1)
        self.assertEqual(t['nonmanifold_edges'],0)

    def test_color_mask_correspondence(self):
        self.assertEqual(len(self.colors),len(self.head.vertices))
        self.assertEqual(len(self.masks),len(self.colors))
        self.assertTrue(all(0<=m<=1 for m in self.masks))
        self.assertTrue(all(0<=c<=1 for rgb in self.colors for c in rgb))

    def test_profile_c1_at_interior_knots(self):
        e=1e-6
        for z,*_ in f.PROFILE[1:-1]:
            a,b,c=f.profile(z-e),f.profile(z),f.profile(z+e)
            for k in range(3):
                self.assertAlmostEqual((b[k]-a[k])/e,(c[k]-b[k])/e,delta=.003)

    def test_nose_is_part_of_front_surface(self):
        self.assertGreater(f.front(0,2.28)-f.front(.10,2.28),.04)

    def test_hands_closed_all_quad_and_weighted(self):
        for mesh,_ in self.hands.values():
            t=topology(mesh.vertices,mesh.faces)
            self.assertEqual(t['components'],1)
            self.assertEqual(t['nonmanifold_edges'],0)
            self.assertEqual(t['quad_fraction'],1)
            self.assertEqual(len(mesh.vertices),19586)
            for weights in mesh.weights:self.assertAlmostEqual(sum(weights.values()),1)

    def test_original_tip_ids_survive_two_subdivision_levels(self):
        for s,(mesh,tips) in self.hands.items():
            old,old_tips=previous_hand(s,False)
            self.assertEqual(tips,old_tips)
            self.assertEqual(len(tips),5)
            self.assertTrue(all(i<len(old.vertices) for ring in tips.values() for i in ring))

    def test_wrist_extension_inside_cuff(self):
        for mesh,_ in self.hands.values():
            self.assertGreater(max(v[2] for v in mesh.vertices),1.13)
            self.assertTrue(any(any(k.startswith('forearm.') for k in w) for w in mesh.weights))

    def test_hands_are_mirrored_not_reversed_digit_order(self):
        a,b=self.hands[-1][0],self.hands[1][0]
        # Ring winding differs; rounded sort keys also split exact half-bin ties.
        from collections import defaultdict
        from itertools import product
        grid=defaultdict(list);cell=1e-6
        def key(p):return tuple(math.floor(c/cell) for c in p)
        for p in b.vertices:grid[key(p)].append(p)
        self.assertEqual(len(a.vertices),len(b.vertices))
        for p in a.vertices:
            p=(-p[0],p[1],p[2]);k=key(p)
            candidates=(q for delta in product((-1,0,1),repeat=3)
                        for q in grid[tuple(k[i]+delta[i] for i in range(3))])
            self.assertTrue(any(sum((x-y)**2 for x,y in zip(p,q))<1e-16 for q in candidates))

    def test_finger_shafts_actually_widen_not_only_palm_vertices(self):
        # Regression: an early continue previously discarded shaft edits.
        old,_=previous_hand(1)
        new=self.hands[1][0];cx=f.digits(1)['middle'][0][0]
        def width(mesh):
            xs=[abs(x-cx) for (x,y,z),w in zip(mesh.vertices,mesh.weights)
                if .94<z<.96 and sum(v for k,v in w.items() if k.startswith('middle.'))>.98]
            return max(xs)
        self.assertGreater(width(new),width(old)*1.05)

    def test_sclera_uses_same_surface_as_iris(self):
        for cx in (-.135,.135):
            for p in f.eye_white(cx).vertices:
                x,y,z=unscale(p);self.assertAlmostEqual(y,f.eye_y(cx,x,z))
            mesh,_=f.iris(cx)
            for p in mesh.vertices:
                x,y,z=unscale(p);self.assertAlmostEqual(y-f.eye_y(cx,x,z),.0007)

    def test_white_boundary_matches_inner_lid(self):
        for cx in (-.135,.135):
            white=f.eye_white(cx);lid,_=f.lids(cx)
            for p,q in zip(white.vertices[-96:],lid.vertices[:96]):
                for x,y in zip(p,q):self.assertAlmostEqual(x,y)

    def test_iris_is_inside_aperture(self):
        for cx in (-.135,.135):
            mesh,_=f.iris(cx)
            for p in mesh.vertices:
                x,y,z=unscale(p);dx=x-cx;dz=z-2.405-.035*dx
                self.assertLessEqual((dx/.080)**2+(dz/(.046 if dz>0 else .055))**2,1)

    def test_hair_base_closed_groom_intentionally_open(self):
        hair=f.hair();t=topology(hair.vertices,hair.faces)
        self.assertEqual(t['nonmanifold_edges'],0)
        groom,colors=f.hair_fibers();t=topology(groom.vertices,groom.faces)
        self.assertEqual(t['components'],480)
        self.assertGreater(t['boundary_edges'],0)
        self.assertEqual(len(colors),len(groom.vertices))

    def test_beard_fibers_finite_and_colored(self):
        mesh,colors=f.beard_fibers()
        self.assertGreater(len(mesh.faces),0)
        self.assertEqual(len(mesh.vertices),len(colors))
        self.assertTrue(all(math.isfinite(c) for p in mesh.vertices for c in p))


class LookdevContracts(unittest.TestCase):
    def setUp(self):
        self.base=ROOT/'studio/production/dad-lookdev'
        self.a=load_json(self.base/'package-r4.json')

    def test_inherited_body_stress_fixture_validates_for_r4(self):
        # Contract-only suite runs on clean checkouts without generated .blend.
        # Native entry points keep verify_files=True; provenance is tested below.
        validate_bundle(load_json(self.base/'project.json'),self.a,load_json(self.base/'shot.json'),verify_files=False)

    def test_package_remains_unreviewed_with_unsupported_face_removed(self):
        self.assertEqual(self.a['revision'],'r4')
        self.assertEqual(self.a['art_status'],'unreviewed')
        for name in ('jaw.open','eye.R.blink','eye.L.blink'):
            self.assertNotIn(name,self.a['bindings'])

    def test_provenance_matches_current_authoring_sources(self):
        provenance=self.a['provenance']
        self.assertEqual(file_hash(ROOT/provenance['authoring_script']),provenance['script_sha256'])
        for item in provenance['dependencies']:
            self.assertEqual(file_hash(ROOT/item['path']),item['sha256'])

    def test_review_budget_and_distinct_views(self):
        p=project(1024,48)
        self.assertEqual(p['resolution'],[1024,1024])
        self.assertEqual(p['render']['threads'],2)
        self.assertEqual(p['resources']['rss_limit_mb'],2048)
        self.assertEqual(p['resources']['timeout_seconds'],300)
        self.assertEqual(len(set(VIEWS)),5)

    def test_audit_scope_and_zero_unweighted(self):
        a=load_json(ROOT/'studio/production/dad-r4-model-audit.json')
        self.assertEqual(a['unweighted_vertices'],0)
        self.assertEqual(a['bone_count'],51)
        self.assertTrue(a['limitations'])


if __name__=='__main__':unittest.main()
