"""Fit acquired CC0 MakeHuman hair; keep original strand UV and alpha texture."""
import hashlib,json
from pathlib import Path
import numpy as np
from mom_face_finish_r7 import linear,smoothstep
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'studio/assets/external/makehuman-hair-r18'

def fit(name,settings):
 manifest=json.loads((ASSETS/'manifest.json').read_text());record=next(a for a in manifest['assets'] if a['name']==name);mesh=ASSETS/f'{name}.npz';tex=ASSETS/f'{name}.webp'
 if hashlib.sha256(mesh.read_bytes()).hexdigest()!=record['mesh_sha256'] or hashlib.sha256(tex.read_bytes()).hexdigest()!=record['texture_sha256']:raise ValueError('Acquired asset changed')
 data=np.load(mesh);p=data['vertices'];eye=data['source_eye_centers'].mean(0);q=np.empty_like(p);top=p[:,1].max();bottom=p[:,1].min();dy=p[:,1]-eye[1]
 upper=(settings['crown_z']-settings['eye_z'])/(top-eye[1]);lower=(settings['eye_z']-settings['tip_z'])/(eye[1]-bottom)
 # Continuous piecewise-height fitting. The original UVs and card topology stay.
 q[:,2]=settings['eye_z']+np.where(dy>=0,dy*upper,dy*lower)
 q[:,0]=p[:,0]*settings['half_width']/max(abs(p[:,0].min()),abs(p[:,0].max()))
 q[:,1]=-(p[:,2]-.25)*.1*settings['depth_scale']
 t=np.clip((1.52-q[:,2])/(1.52-settings['tip_z']),0,1);wave=.020*np.sin(1.5*np.pi*t)+.040*t**6
 q[:,0]+=np.sign(q[:,0])*wave
 q[:,1]+=.008*np.sin(2*np.pi*t)*smoothstep(.07,.12,abs(q[:,0]))
 return q,data['polygons'],data['uv'],record

def material(bpy,name):
 mat=bpy.data.materials.new('Mom R18 CC0 textured hair '+name);mat.use_nodes=True;n=mat.node_tree.nodes;links=mat.node_tree.links;shader=n['Principled BSDF'];shader.inputs['Roughness'].default_value=.48;shader.inputs['Specular IOR Level'].default_value=.26
 image=bpy.data.images.load(str((ASSETS/f'{name}.webp').resolve()),check_existing=False);image.pack();tex=n.new('ShaderNodeTexImage');tex.image=image;tex.extension='EXTEND';tex.interpolation='Linear';tex.name='CC0 original strand texture, not canonical art'
 # Original brown texture provides fine strands; a modest tint warms it.
 mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;mix.inputs[2].default_value=(.90,.58,.37,1) if name=='bob02' else (10,16,13,1);links.new(tex.outputs['Color'],mix.inputs[1]);links.new(mix.outputs[0],shader.inputs['Base Color']);links.new(tex.outputs['Alpha'],shader.inputs['Alpha'])
 return mat

def build(bpy,rig,name,settings):
 p,polys,uv,record=fit(name,settings);mesh=bpy.data.meshes.new('CC0 fitted '+name);mesh.from_pydata(p.tolist(),[],polys.tolist());mesh.update();layer=mesh.uv_layers.new(name='Original CC0 strand UV');loops=np.concatenate(polys);layer.data.foreach_set('uv',uv[loops].ravel())
 for poly in mesh.polygons:poly.use_smooth=True
 obj=bpy.data.objects.new('HAIR-mom-R18-asset-'+name,mesh);bpy.context.scene.collection.objects.link(obj);mesh.materials.append(material(bpy,name))
 # Subdivision follows existing coherent source surfaces, not a generated cage.
 sub=obj.modifiers.new('Smooth original asset surfaces','SUBSURF');sub.levels=1;sub.render_levels=1
 world=obj.matrix_world.copy();obj.parent=rig;obj.parent_type='BONE';obj.parent_bone='DEF-Head';bpy.context.view_layer.update();obj.matrix_world=world
 return obj,{'object':obj.name,'asset':name,'source_license':'CC0-1.0','source_commit':json.loads((ASSETS/'manifest.json').read_text())['source_commit'],'source_mesh_sha256':record['mesh_sha256'],'source_texture_sha256':record['texture_sha256'],'vertices':len(p),'polygons':len(polys),'original_uv_sha256':hashlib.sha256(np.asarray(uv,dtype=np.float32).tobytes()).hexdigest(),'fit':settings,'binding':'Original DEF-Head; no hair/shoulder dynamics certification','method':'Acquired coherent mesh and original alpha strand texture, smooth3D height/width/depth + wave fit. No canonical texture sampling, no Rain head replacement.'}
