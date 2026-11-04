"""Real fine HAIR curves following acquired CC0 mesh/UV islands, not tube locks.

The fitted mesh is a 3D growth guide and dark undercoat. UV is used to walk its
surfaces; no canonical pixels are sampled. Distinct overlapping UV islands are
processed separately so reused source strand cards cannot erase each other.
"""
import hashlib,json
import numpy as np
from PIL import Image
import mom_hair_asset_r18 as source
from mom_groom_r15 import native_curves

def islands(polys,count):
 parent=np.arange(count)
 def root(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 for f in polys:
  for b in f[1:]:parent[root(int(b))]=root(int(f[0]))
 groups={}
 for i,f in enumerate(polys):groups.setdefault(root(int(f[0])),[]).append(i)
 return [np.asarray(g) for g in groups.values()]

def guide_paths(settings,resolution=768):
 p,polys,uv,record=source.fit('bob02',settings);tri=np.array([[f[0],f[i],f[i+1]] for f in polys for i in (1,2)]);cross=np.cross(p[tri[:,1]]-p[tri[:,0]],p[tri[:,2]]-p[tri[:,0]]);normals=np.zeros_like(p)
 for k in range(3):np.add.at(normals,tri[:,k],cross)
 normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
 # Texture alpha only defines real source strands. Coordinates are 3D guide data.
 alpha=np.asarray(Image.open(source.ASSETS/'bob02.webp').convert('RGBA'))[:,:,3]/255
 paths=[];path_normals=[];lengths=[];components=islands(polys,len(p))
 for group in components:
  faces=polys[group];used=np.unique(faces);low=np.maximum(np.floor(uv[used].min(0)*resolution).astype(int)-1,0);high=np.minimum(np.ceil(uv[used].max(0)*resolution).astype(int)+1,resolution);width,height=high-low
  if width<2 or height<2:continue
  positions=np.full((height,width,3),np.nan);ns=np.zeros_like(positions)
  for f in faces:
   for j in (1,2):
    ids=np.array([f[0],f[j],f[j+1]]);t=uv[ids]*resolution-low-.5;a,b,c=t;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(den)<1e-8:continue
    lo=np.maximum(np.floor(t.min(0)).astype(int),0);hi=np.minimum(np.ceil(t.max(0)).astype(int),[width-1,height-1]);xx,yy=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1));w0=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den;w1=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;w2=1-w0-w1;valid=(w0>=-1e-6)&(w1>=-1e-6)&(w2>=-1e-6);weights=np.stack([w0,w1,w2],axis=-1);block=positions[lo[1]:hi[1]+1,lo[0]:hi[0]+1];normal_block=ns[lo[1]:hi[1]+1,lo[0]:hi[0]+1];block[valid]=(weights@p[ids])[valid];normal_block[valid]=(weights@normals[ids])[valid]
  for x in range(width):
   ys=np.arange(height);u=(x+low[0]+.5)/resolution;v=(ys+low[1]+.5)/resolution;ay=np.clip(((1-v)*(alpha.shape[0]-1)).astype(int),0,alpha.shape[0]-1);ax=min(alpha.shape[1]-1,int(u*(alpha.shape[1]-1)));valid=np.isfinite(positions[:,x,0])&(alpha[ay,ax]>.20);indices=np.where(valid)[0]
   if len(indices)<5:continue
   cuts=np.where((np.diff(indices)>1)|(np.linalg.norm(np.diff(positions[indices,x],axis=0),axis=1)>.012))[0]+1
   for rows in np.split(indices,cuts):
    if len(rows)<5:continue
    q=positions[rows,x];n=ns[rows,x];d=np.linalg.norm(np.diff(q,axis=0),axis=1);length=float(d.sum())
    if length<.025:continue
    if q[0,2]<q[-1,2]:q=q[::-1];n=n[::-1];d=d[::-1]
    arc=np.r_[0,np.cumsum(d)];target=np.linspace(0,arc[-1],40);path=np.column_stack([np.interp(target,arc,q[:,k]) for k in range(3)]);normal=np.column_stack([np.interp(target,arc,n[:,k]) for k in range(3)]);normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-12);paths.append(path);path_normals.append(normal);lengths.append(length)
 if not paths:raise ValueError('No actual UV-island growth paths')
 return np.array(paths),np.array(path_normals),np.array(lengths),len(components)

def fibers(settings,count=16000,seed=1904):
 guides,normals,lengths,components=guide_paths(settings);rng=np.random.default_rng(seed);ids=rng.choice(len(guides),count,p=lengths/lengths.sum());p=guides[ids].copy();n=normals[ids];t=np.linspace(0,1,p.shape[1]);tangent=np.gradient(p,axis=1);lateral=np.cross(tangent,n);lateral/=np.maximum(np.linalg.norm(lateral,axis=2,keepdims=True),1e-12)
 p+=n*rng.uniform(.00015,.0018,(count,1,1))*(.25+.75*np.sin(np.pi*t))[None,:,None]
 p+=lateral*rng.normal(0,.00045,(count,1,1))*(.2+.8*np.sin(np.pi*t))[None,:,None]
 radius=rng.uniform(.000038,.000062,(count,1))*(1-.90*t**5)[None,:]
 return p,radius,{'source_uv_islands':components,'actual_surface_guides':len(guides),'fine_native_hair_curves':count,'points_per_curve':p.shape[1],'radius_range_m':[float(radius.min()),float(radius.max())],'coordinate_sha256':hashlib.sha256(p.astype(np.float32).tobytes()).hexdigest(),'seed':seed,'source_commit':json.loads((source.ASSETS/'manifest.json').read_text())['source_commit'],'source_license':'CC0-1.0','method':'Native fine HAIR curves walking separate original CC0 UV islands on actual fitted3D surfaces. Existing fitted mesh retained as dark coverage, not final ribbon highlights. No canonical image used as texture or geometry.'}

def build(bpy,rig,settings,count):
 p,r,receipt=fibers(settings,count);mat=bpy.data.materials.new('Mom R19 physical fine warm brown hair');mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear();out=nodes.new('ShaderNodeOutputMaterial');shader=nodes.new('ShaderNodeBsdfHairPrincipled');shader.parametrization='MELANIN';shader.inputs['Melanin'].default_value=.48;shader.inputs['Melanin Redness'].default_value=.30;shader.inputs['Roughness'].default_value=.42
 if 'Radial Roughness' in shader.inputs:shader.inputs['Radial Roughness'].default_value=.40
 mat.node_tree.links.new(shader.outputs[0],out.inputs['Surface']);obj=native_curves(bpy,'GROOM-mom-R19-CC0-surface-grown-hair',p,r,mat,rig)
 receipt['object']=obj.name;receipt['attachment']='Original DEF-Head, rigid growth guides; dynamics not certified';return obj,receipt
