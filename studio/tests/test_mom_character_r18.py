"""Acquired-asset and original-surface safety, never artistic certification."""
import unittest,sys,json,gzip,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'studio/tools'))
import mom_hair_asset_r18 as hair
import mom_face_finish_r18 as face
class R18(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.s=json.loads((ROOT/'studio/authoring/mom-character-r18.json').read_text())
 def test_actual_acquired_assets_and_license_bound(self):
  m=json.loads((hair.ASSETS/'manifest.json').read_text());self.assertEqual(m['source_asset_license'],'CC0-1.0');self.assertIn('MakeHuman CC0 asset pack',(hair.ASSETS/'UPSTREAM-README.md').read_text());self.assertEqual(len(m['assets']),2)
  for a in m['assets']:
   for suffix,key in (('.npz','mesh_sha256'),('.webp','texture_sha256')):self.assertEqual(hashlib.sha256((hair.ASSETS/(a['name']+suffix)).read_bytes()).hexdigest(),a[key])
 def test_fitted_source_topology_and_uv_are_retained(self):
  for n in ('long01','bob02'):
   q,polys,uv,record=hair.fit(n,self.s['hair_fit']);d=np.load(hair.ASSETS/(n+'.npz'));self.assertTrue(np.isfinite(q).all());np.testing.assert_array_equal(polys,d['polygons']);np.testing.assert_array_equal(uv,d['uv']);self.assertAlmostEqual(q[:,2].max(),self.s['hair_fit']['crown_z']);self.assertLess(q[:,0].max(),.21);self.assertGreater(q[:,2].min(),1.25)
 def test_nasal_fairing_preserves_original_surface_orientation(self):
  d=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r17/head-edit-data.json.gz').read_bytes()));p=np.array(d['basis_vertices']);q=face.fair(p,d['polygons'],self.s['fairing']);self.assertLessEqual(np.linalg.norm(q-p,axis=1).max(),.0035);np.testing.assert_array_equal(p[:,0],q[:,0]);np.testing.assert_array_equal(p[:,2],q[:,2]);tri=np.array([[f[0],f[j],f[j+1]] for f in d['polygons'] for j in range(1,len(f)-1)]);a=p[tri];b=q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);v=np.linalg.norm(na,axis=1)>1e-12;self.assertTrue((np.einsum('ij,ij->i',na[v],nb[v])>0).all())
 def test_source_ids_weld_uv_seams_not_distinct_cards(self):
  for n in ('bob02','long01'):
   d=np.load(hair.ASSETS/(n+'.npz'));ids,first,inverse=np.unique(d['render_to_source'],return_index=True,return_inverse=True);self.assertLess(len(ids),len(d['vertices']));np.testing.assert_array_equal(d['vertices'][first][inverse],d['vertices']);self.assertEqual(len(d['uv']),len(d['vertices']))
 def test_actual_pigment_energy_not_beauty_retouch(self):
  import mom_face_paint_r17 as old
  import mom_face_paint_r18 as new
  p=np.array([[-.02,-.15,1.42],[.02,-.15,1.42],[0,-.15,1.45]]);uv=np.array([[.1,.1],[.9,.1],[.5,.9]]);tri=np.array([[0,1,2]]);weights=np.zeros(3)
  args=(p,uv,tri,tri,weights,weights,self.s['palette_srgb'])
  a,rough,_=old.rasterize(*args,resolution=32);b,response,record=new.rasterize(*args,resolution=32,energy_scale=self.s['linear_albedo_energy_scale']);np.testing.assert_allclose(b[:,:,:3],a[:,:,:3]*.72);np.testing.assert_array_equal(b[:,:,3],a[:,:,3]);np.testing.assert_array_equal(rough,response);self.assertEqual(record['linear_albedo_energy_scale'],.72)
 def test_no_automatic_acceptance(self):
  for k in ('art_approved','user_approved','production_swap_allowed'):self.assertFalse(self.s[k])
if __name__=='__main__':unittest.main()
