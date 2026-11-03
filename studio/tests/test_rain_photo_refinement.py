"""A6 geometry/privacy contracts. No photo recognition or likeness scores."""
from collections import Counter
from pathlib import Path
import subprocess
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio/tools'))
import rain_mom_pass_a6 as a6


class PhotoGuidedRefinementTests(unittest.TestCase):
    def test_cap_outward_normals_and_one_open_hairline(self):
        points,polygons,_=a6.cap_geometry()
        p=np.asarray(points)
        self.assertTrue(np.isfinite(p).all())
        edges=Counter()
        for polygon in polygons:
            v=p[list(polygon)]
            n=np.cross(v[1]-v[0],v[2]-v[0])
            self.assertGreater(np.dot(n,v.mean(axis=0)-[0,.008,1.49]),0)
            for a,b in zip(polygon,polygon[1:]+polygon[:1]):edges[tuple(sorted((a,b)))]+=1
        self.assertEqual(sum(count==1 for count in edges.values()),96)
        self.assertTrue(all(count in (1,2) for count in edges.values()))

    def test_cap_dimensions_and_finite_uv(self):
        points,_,uv=a6.cap_geometry()
        p=np.asarray(points)
        self.assertLess(np.abs(p[:,0]).max(),.131)
        self.assertLess(p[:,2].max(),1.66)
        self.assertGreater(p[:,2].min(),1.39)
        self.assertTrue(np.isfinite(uv).all())
        self.assertEqual(len(points),len(uv))

    def test_face_changes_remain_small_and_symmetric(self):
        p=np.stack(np.meshgrid(np.linspace(-.15,.15,25),np.linspace(-.16,.05,9),np.linspace(1.33,1.55,25)),axis=-1).reshape(-1,3)
        q=a6.face_refinement(p)
        self.assertTrue(np.isfinite(q).all())
        self.assertLess(np.linalg.norm(q-p,axis=1).max(),.004)
        other=p.copy();other[:,0]*=-1
        q[:,0]*=-1
        np.testing.assert_allclose(q,a6.face_refinement(other),atol=1e-12)

    def test_face_map_does_not_fold(self):
        p=np.stack(np.meshgrid(np.linspace(-.13,.13,31),np.linspace(-.15,-.04,7),np.linspace(1.35,1.53,31)),axis=-1).reshape(-1,3)
        columns=[]
        for axis in range(3):
            d=np.zeros((1,3));d[0,axis]=1e-6
            columns.append((a6.face_refinement(p+d)-a6.face_refinement(p-d))/2e-6)
        self.assertGreater(np.linalg.det(np.stack(columns,axis=2)).min(),.7)

    def test_lash_only_pass_does_not_apply_cheek_or_lip_change(self):
        p=np.array([[.02,-.14,1.39]])
        np.testing.assert_allclose(a6.face_refinement(p,head=False),p,atol=1e-9)

    def test_personal_reference_files_not_tracked(self):
        tracked=subprocess.check_output(['git','ls-files','--','studio/reference'],cwd=ROOT,text=True).splitlines()
        self.assertEqual(tracked,['studio/reference/README.md'])
        result=subprocess.run(['git','check-ignore','-q','studio/reference/privacy-probe.jpeg'],cwd=ROOT)
        self.assertEqual(result.returncode,0)

    def test_new_build_does_not_open_private_photos(self):
        import ast
        tree=ast.parse((ROOT/'studio/tools/rain_mom_pass_a6.py').read_text())
        literals=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        # No attachment filename, private file path or raw-upload reference in code literals.
        for value in literals:
            if '\n' in value:continue # module docstring describes policy, not an input path
            self.assertNotIn('arena-coding-uploads',value)
            self.assertNotIn('studio/reference/',value)
            self.assertNotRegex(value,r'IMG_\d+')


if __name__=='__main__':
    unittest.main()
