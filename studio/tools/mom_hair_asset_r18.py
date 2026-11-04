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
 # Smooth monotone forelock lift opens BOTH eyes without cutting source cards.
 front=smoothstep(-.070,-.130,q[:,1]);center=np.exp(-(q[:,0]/.085)**6)
 q[:,2]+=settings['fringe_lift_m']*front*center*smoothstep(1.63,1.44,q[:,2])
 q[:,0]-=settings['part_shift_m']*smoothstep(1.48,1.63,q[:,2])*np.exp(-(q[:,0]/.09)**4)
 if name=='bob02':q[:,0]*=1+1.2*smoothstep(1.34,settings['tip_z'],q[:,2])
 t=np.clip((1.52-q[:,2])/(1.52-settings['tip_z']),0,1);wave=.035*np.sin(1.5*np.pi*t)+.055*t**6
 q[:,0]+=np.sign(q[:,0])*wave
 q[:,1]+=.008*np.sin(2*np.pi*t)*smoothstep(.07,.12,abs(q[:,0]))
 return q,data['polygons'],data['uv'],record

def material(bpy,name):
 mat=bpy.data.materials.new('Mom R18 CC0 textured hair '+name);mat.use_nodes=True;n=mat.node_tree.nodes;links=mat.node_tree.links;shader=n['Principled BSDF'];shader.inputs['Roughness'].default_value=.60;shader.inputs['Specular IOR Level'].default_value=.08;shader.inputs['Anisotropic'].default_value=.50;shader.inputs['Anisotropic Rotation'].default_value=.25
 image=bpy.data.images.load(str((ASSETS/f'{name}.webp').resolve()),check_existing=False);image.pack();tex=n.new('ShaderNodeTexImage');tex.image=image;tex.extension='EXTEND';tex.interpolation='Linear';tex.name='CC0 original strand texture, not canonical art'
 # Source luminance still supplies fine strands. A bounded brown ramp prevents
 # pale diffuse highlights in the gray stock bob from bleaching the whole wig.
 bw=n.new('ShaderNodeRGBToBW');ramp=n.new('ShaderNodeValToRGB');ramp.name='R18 bounded warm brown, source strand luminance'
 cr=ramp.color_ramp;cr.elements.remove(cr.elements[1]);cr.elements[0].position=0;cr.elements[0].color=(*(linear('#503822')*.55),1)
 for pos,color in ((.10,'#70513A'),(.45,'#9A7856'),(1.,'#B38C65')):e=cr.elements.new(pos);e.color=(*(linear(color)*.55),1)
 bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.00018;links.new(bw.outputs[0],bump.inputs['Height']);links.new(bump.outputs['Normal'],shader.inputs['Normal'])
 links.new(tex.outputs['Color'],bw.inputs['Color']);links.new(bw.outputs[0],ramp.inputs[0]);links.new(ramp.outputs[0],shader.inputs['Base Color']);links.new(tex.outputs['Alpha'],shader.inputs['Alpha'])

 return mat

def build(bpy,rig,name,settings):
 p,polys,uv,record=fit(name,settings);render_count=len(p);ids=np.load(ASSETS/f'{name}.npz')['render_to_source'];_,first,inverse=np.unique(ids,return_index=True,return_inverse=True);source_p=p[first];source_polys=inverse[polys];mesh=bpy.data.meshes.new('CC0 fitted '+name);mesh.from_pydata(source_p.tolist(),[],source_polys.tolist());mesh.update();layer=mesh.uv_layers.new(name='Original CC0 strand UV');loops=np.concatenate(polys);layer.data.foreach_set('uv',uv[loops].ravel())
 for poly in mesh.polygons:poly.use_smooth=True
 obj=bpy.data.objects.new('HAIR-mom-R18-asset-'+name,mesh);bpy.context.scene.collection.objects.link(obj);mesh.materials.append(material(bpy,name))
 # Subdivision follows existing coherent source surfaces, not a generated cage.
 sub=obj.modifiers.new('Smooth original asset surfaces','SUBSURF');sub.levels=1;sub.render_levels=1
 if rig is not None:
  world=obj.matrix_world.copy();obj.parent=rig;obj.parent_type='BONE';obj.parent_bone='DEF-Head';bpy.context.view_layer.update();obj.matrix_world=world
 return obj,{'object':obj.name,'asset':name,'source_license':'CC0-1.0','source_commit':json.loads((ASSETS/'manifest.json').read_text())['source_commit'],'source_mesh_sha256':record['mesh_sha256'],'source_texture_sha256':record['texture_sha256'],'vertices':len(source_p),'render_vertices':render_count,'polygons':len(polys),'original_uv_sha256':hashlib.sha256(np.asarray(uv,dtype=np.float32).tobytes()).hexdigest(),'fit':settings,'saved_appearance_state':fingerprint(obj),'binding':'Original DEF-Head; no hair/shoulder dynamics certification' if rig is not None else 'UNRIGGED DIAGNOSTIC ONLY, not original character binary','method':'Acquired coherent mesh and original alpha strand texture, smooth3D height/width/depth + wave fit. No canonical texture sampling, no Rain head replacement.'}


def fingerprint(obj):
 mesh=obj.data;p=np.empty(len(mesh.vertices)*3,np.float32);mesh.vertices.foreach_get('co',p);uv=np.empty(len(mesh.uv_layers.active.data)*2,np.float32);mesh.uv_layers.active.data.foreach_get('uv',uv);tree=mesh.materials[0].node_tree;shader=tree.nodes['Principled BSDF'];ramp=tree.nodes['R18 bounded warm brown, source strand luminance'].color_ramp;tex=next(n for n in tree.nodes if n.type=='TEX_IMAGE');bump=next(n for n in tree.nodes if n.type=='BUMP')
 return {'coordinate_sha256':hashlib.sha256(p.tobytes()).hexdigest(),'polygon_sha256':hashlib.sha256(json.dumps([list(f.vertices) for f in mesh.polygons],separators=(',',':')).encode()).hexdigest(),'loop_uv_sha256':hashlib.sha256(uv.tobytes()).hexdigest(),'packed_texture_sha256':hashlib.sha256(bytes(tex.image.packed_file.data)).hexdigest(),'texture_colorspace':tex.image.colorspace_settings.name,'brown_ramp':[{'position':float(e.position),'linear_rgba':list(e.color)} for e in ramp.elements],'shader':{k:float(shader.inputs[k].default_value) for k in ('Roughness','Specular IOR Level','Anisotropic','Anisotropic Rotation')},'source_strand_micro_normal':{'strength':float(bump.inputs['Strength'].default_value),'distance_m':float(bump.inputs['Distance'].default_value)}}
