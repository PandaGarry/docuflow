"""Acquire pinned CC0 MakeHuman hair data (not the old AGPL asset checkout).

Data conversion upstream explicitly uses the MakeHuman CC0 system asset pack.
HumanGen Web code is MIT; meshes/textures/fit data are CC0. We reimplement the
published three-vertex barycentric fit; no MakeHuman application code required.
"""
import base64, hashlib, json, subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/assets/external/makehuman-hair-r18'
REPO='NastyFFM/HumanGenWeb'
COMMIT='a8ee33f96791ed15534246ac88cc8b20f9da8f6a'

def get(path):
 data=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/contents/{path}?ref={COMMIT}']))
 return base64.b64decode(data['content'])

def fitted(base,data):
 fit=np.asarray(data['fit']);scale=np.ones(3)
 for axis,(a,b,ref) in data['scale'].items():
  k='xyz'.index(axis);scale[k]=abs(base[a,k]-base[b,k])/ref
 return np.einsum('ij,ijk->ik',fit[:,3:6],base[fit[:,:3].astype(int)])+fit[:,6:9]*scale

def main():
 OUT.mkdir(parents=True,exist_ok=True);readme=get('README.md');(OUT/'UPSTREAM-README.md').write_bytes(readme)
 if b'MakeHuman CC0 asset pack' not in readme:raise ValueError('Missing asset-specific CC0 provenance')
 info=json.loads(get('data/mesh.json'));binary=get('data/mesh.bin');base=np.frombuffer(binary,dtype='<f4',count=info['vertexCount']*3).reshape(-1,3)
 eye=fitted(base,json.loads(get('data/eye.json')));centers=[eye[eye[:,0]*side>0].mean(0).tolist() for side in (-1,1)]
 records=[]
 for name in ('long01','bob02'):
  raw=get(f'data/proxies/hair/{name}.json');data=json.loads(raw);verts=fitted(base,data);mapping=np.array(data['map']);faces=np.asarray(data['quads']).reshape(-1,4)
  path=OUT/f'{name}.npz';np.savez_compressed(path,vertices=verts[mapping],polygons=faces,uv=np.array(data['uv']).reshape(-1,2),source_eye_centers=np.array(centers))
  texture=get(f'data/proxies/hair/{name}.webp');(OUT/f'{name}.webp').write_bytes(texture)
  records.append({'name':name,'vertices':len(mapping),'quads':len(faces),'bounds_source_dm':[verts.min(0).tolist(),verts.max(0).tolist()],'mesh_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'texture_sha256':hashlib.sha256(texture).hexdigest(),'upstream_fit_json_sha256':hashlib.sha256(raw).hexdigest(),'upstream_asset_path':f'data/proxies/hair/{name}.json','source_normal_map':data.get('normal',False)})
 license_text=subprocess.check_output(['gh','api','repos/makehumancommunity/mpfb2/contents/LICENSE.ASSETS.md','--jq','.content']);license_bytes=base64.b64decode(license_text);(OUT/'LICENSE.ASSETS.md').write_bytes(license_bytes)
 manifest={'source_repository':f'https://github.com/{REPO}','source_commit':COMMIT,'source_asset_license':'CC0-1.0','upstream_conversion_code_license':'MIT (not incorporated)','original_asset_pack':'https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip','source_mesh_binary_sha256':hashlib.sha256(binary).hexdigest(),'readme_sha256':hashlib.sha256(readme).hexdigest(),'license_sha256':hashlib.sha256(license_bytes).hexdigest(),'method':'Reconstructed original hair only from CC0 fit data and original CC0 base coordinates. No head/body asset imported into Rain. Source .npz retains original render topology and UV.','assets':records}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
