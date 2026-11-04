"""Real R13 Rain asset → coordinated R14 proportions, native strand hair and vest.

No original head replacement, embedded-script execution, generated image or
render retouch. Final Cycles frames are evidence, not automatic art approval.
"""
import gzip,json,sys
from pathlib import Path
import numpy as np
import mom_character_probe_r14 as source
import mom_face_anatomy_r14 as anatomy
import mom_groom_r14 as groom
import mom_wardrobe_r14 as wardrobe
import mom_head_surface_r2 as surface
import mom_head_lookdev_r10 as portrait
build=source.prior;ROOT=source.ROOT;OUT=source.OUT;SPEC=ROOT/'studio/authoring/mom-character-r14.json'
SCRIPTS=('mom_character_r14.py','mom_character_probe_r14.py','mom_face_anatomy_r14.py','mom_groom_r14.py','mom_wardrobe_r14.py','mom_head_lookdev_r10.py','mom_head_cage.py','mom_face_anatomy_r12.py','mom_smile_pose_r3.py')

def edit_blocks(bpy,obj,field):
 mesh=obj.data;keys=mesh.shape_keys;blocks=[k.data for k in keys.key_blocks] if keys else [mesh.vertices];world=obj.matrix_world.copy();inverse=world.inverted();maximum=0
 for block in blocks:
  p=build.base.transform_points(build.base.point_array(block),world);q=field(p);maximum=max(maximum,float(np.linalg.norm(q-p,axis=1).max()))
  if not np.isfinite(q).all():raise ValueError('Nonfinite edited key')
  block.foreach_set('co',build.base.transform_points(q,inverse).ravel())
 if keys:mesh.vertices.foreach_set('co',build.base.point_array(keys.key_blocks[0].data).ravel());keys.update_tag()
 mesh.update();bpy.context.view_layer.update();return {'object':obj.name,'original_blocks':len(blocks),'max_change_m':maximum}

def iris(bpy,settings):
 tree=bpy.data.materials['MAT-rain.eyes'].node_tree;image=tree.nodes['Image Texture.001'];old=image.inputs['Vector'].links[0].from_socket;center=(.45102685,.4571689,0)
 subtract=tree.nodes.new('ShaderNodeVectorMath');subtract.operation='SUBTRACT';subtract.inputs[1].default_value=center
 scale=tree.nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(settings['iris_uv_scale'],settings['iris_uv_scale'],1)
 add=tree.nodes.new('ShaderNodeVectorMath');add.operation='ADD';add.inputs[1].default_value=center
 tree.links.new(old,subtract.inputs[0]);tree.links.new(subtract.outputs['Vector'],scale.inputs[0]);tree.links.new(scale.outputs['Vector'],add.inputs[0]);tree.links.new(add.outputs['Vector'],image.inputs['Vector'])
 return {'existing_image':image.image.name,'image_packed_sha256':build.hashlib.sha256(bytes(image.image.packed_file.data)).hexdigest(),'original_uv_layer_unchanged':True,'iris_uv_center':center,'uv_scale':settings['iris_uv_scale'],'requested_iris_scale':1/settings['iris_uv_scale']}

def brows(bpy,rig,spec):
 head=bpy.data.objects['GEO-rain-head'];hp=build.base.transform_points(build.base.point_array(head.data.vertices),head.matrix_world);polys=[list(f.vertices) for f in head.data.polygons]
 def field(p):
  x=np.abs(p[:,0]);q=p.copy();center=np.polyval(np.polyfit(x,p[:,2],3),x);phase=np.clip((x-.019)/.061,0,1)
  q[:,2]=center+(p[:,2]-center)*(.66/.48)+.0007*np.sin(np.pi*phase)
  q[:,1]=surface.front_surface_y(q,hp,polys)-.002;return q
 receipt=edit_blocks(bpy,bpy.data.objects['GEO-rain-eyebrows'],field)
 rng=np.random.default_rng(1402);paths=[];radii=[]
 for side in (-1,1):
  for _ in range(220):
   x=rng.uniform(.021,.078);z=float(surface.cubic_curve(np.array([x]),spec['brow_curve']['abscissae_m'],spec['brow_curve']['heights_m'])[0])+rng.uniform(-.0017,.0017)
   p=np.array([[side*x,0,z],[side*(x+.0013),0,z+.001],[side*(x+.0028),0,z+.0015]])
   p[:,1]=surface.front_surface_y(p,hp,polys)-.0034;paths.append(p);radii.append([.00006,.000045,.000008])
 obj=groom.native_curves(bpy,'GROOM-mom-R14-brow-fibers',np.array(paths),np.array(radii),groom.hair_material(bpy,'#79583E'),rig)
 receipt.update({'fiber_object':obj.name,'fibers':440,'strip_transverse_scale_relative_to_r13':.66/.48});return receipt

def relax_arms(bpy,rig):
 from mathutils import Matrix,Vector
 prop=rig.pose.bones['Properties_IKFK'];record=[]
 for side,sign,label in [('L',1,'left'),('R',-1,'right')]:
  prop['ik_arm_'+label]=0.0;rig.update_tag();bpy.context.view_layer.update()
  bone=rig.pose.bones['FK-Upperarm.'+side];world=rig.matrix_world@bone.matrix;pivot=world.translation.copy()
  world=Matrix.Translation(pivot)@Matrix.Rotation(sign*np.deg2rad(72),4,'Y')@Matrix.Translation(-pivot)@world
  bone.matrix=rig.matrix_world.inverted()@world;rig.update_tag();bpy.context.view_layer.update();record.append({'control':bone.name,'world_y_degrees':sign*72,'ik_property':'ik_arm_'+label})
 return record

def render(bpy,path,position,target,scale,resolution=(1024,1280),samples=64):
 from mathutils import Vector
 scene=bpy.context.scene;camera=scene.camera;camera.data.type='ORTHO';camera.data.ortho_scale=scale;camera.location=position;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
 scene.render.resolution_x=resolution[0];scene.render.resolution_y=resolution[1];scene.cycles.samples=samples;scene.render.filepath=str(path.resolve());bpy.ops.render.render(write_still=True)
 return {'path':path.relative_to(ROOT).as_posix(),'sha256':build.study.sha(path),'camera':{'position':list(position),'target':list(target),'ortho_scale':scale},'dimensions':list(resolution),'samples':samples,'engine':scene.render.engine}

def main():
 import bpy
 spec=json.loads(SPEC.read_text());old,native=source.load(bpy);OUT.mkdir(parents=True,exist_ok=True);rig=bpy.data.objects['RIG-rain'];rest=build.base.rig_signature(rig);invalid=build.base.invalid_drivers(bpy)
 head=bpy.data.objects['GEO-rain-head'];before=build.diagnostic.head_data(bpy);delta=anatomy.neutral_residual(spec)
 tri=np.array([[f[0],f[j],f[j+1]] for f in before['polygons'] for j in range(1,len(f)-1)])
 def head_field(p):
  q=p+delta;a=p[tri];b=q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12
  if (np.einsum('ij,ij->i',na[valid],nb[valid])<=0).any():raise ValueError('R14 residual reverses original head corrective triangle')
  return q
 edits=[edit_blocks(bpy,head,head_field),edit_blocks(bpy,bpy.data.objects['GEO-rain-eyelashes'],anatomy.aperture)]
 for name in ('GEO-rain-eyes','GEO-rain-eye_cornea','GEO-rain-eye_dots'):
  edits.append(edit_blocks(bpy,bpy.data.objects[name],lambda p:anatomy.globe(p,spec['eye_finish']['globe_scale'])))
 eye=iris(bpy,spec['eye_finish']);brow=brows(bpy,rig,spec);brow_fiber=bpy.data.objects[brow['fiber_object']];brow_fiber.hide_render=True
 indexed=build.diagnostic.head_data(bpy)
 for key in ('polygons','vertex_weights','shape_keys','related_rest_bones'):
  if indexed[key]!=before[key]:raise ValueError('Original head topology/weights/keys/rest changed')
 (OUT/'head-edit-data.json.gz').write_bytes(gzip.compress(json.dumps(indexed,separators=(',',':')).encode(),mtime=0))
 material_state=build.finish.saved_material_state(bpy)
 if material_state['original_uv_sha256']!=old['saved_material_state']['original_uv_sha256']:raise ValueError('Head UV changed')
 if material_state['active_original_uv_maps']!=old['saved_material_state']['active_original_uv_maps']:raise ValueError('Head paint maps changed')
 # Unhidden anatomy evidence BEFORE adding hair/body. Existing neutral diagnostic light.
 colors={name:list(bpy.data.objects[name].data.materials) for name in ('GEO-rain-head','GEO-rain-eyebrows','GEO-rain-eyelashes')}
 gray=build.diagnostic.flat_material(bpy,'R14 neutral clay',(.45,.45,.45))
 for i in range(len(head.data.materials)):head.data.materials[i]=gray
 images=[]
 for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:images.append(render(bpy,OUT/f'clay-{view}.png',position,(0,0,1.47),.48,(768,768),24))
 for name,mats in colors.items():
  for i,m in enumerate(mats):bpy.data.objects[name].data.materials[i]=m
 scene=portrait.portrait_stage(bpy);images.append(render(bpy,OUT/'bare-front.png',(0,-4,1.5),(0,0,1.47),.48,(1024,1024),96));brow_fiber.hide_render=False
 hair=groom.build(bpy,rig,spec['groom']);clothes=wardrobe.build(bpy,rig,spec['wardrobe'])
 body=bpy.data.objects['GEO-rain-body'];body.hide_render=False;body.hide_set(False)
 arm_pose=relax_arms(bpy,rig)
 # Save a neutral face, clothed and groomed, with original pose/shape drivers live.
 from mathutils import Vector
 camera=scene.camera;camera.data.ortho_scale=.60;camera.location=(0,-4,1.5);camera.rotation_euler=(Vector((0,0,1.39))-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.resolution_x=1024;scene.render.resolution_y=1280
 bpy.ops.file.pack_all();path=ROOT/'.cache/r14/mom-character-r14.blend';path.parent.mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=str(path.resolve()),compress=True)
 images.append(render(bpy,OUT/'saved-neutral-front.png',(0,-4,1.5),(0,0,1.39),.60,(512,640),32))
 matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones};baseline=build.base.head_geometry(bpy);smile=build.warm_pose.set_warm_smile(bpy,rig,.4)
 for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:images.append(render(bpy,OUT/f'portrait-{view}.png',position,(0,0,1.39),.60))
 import rain_mom_pass_a2 as controls
 controls.restore(bpy,rig,matrices);restore=float(np.linalg.norm(build.base.head_geometry(bpy)-baseline,axis=1).max())
 if restore>1e-7 or rest!=build.base.rig_signature(rig) or set(build.base.invalid_drivers(bpy))-set(invalid):raise ValueError('Rig/restore integrity failure')
 record={'revision':spec['revision'],'source_run':41807469868,'downloaded_r13_binary_sha256':build.study.sha(native),'spec_sha256':build.study.sha(SPEC),'scripts':{name:build.study.sha(ROOT/'studio/tools'/name) for name in SCRIPTS},'canonical_face_sha256':build.study.sha(ROOT/'studio/characters/mom/master/face.png'),'head_edit_data_sha256':build.study.sha(OUT/'head-edit-data.json.gz'),'native_artifact':{'filename':path.name,'sha256':build.study.sha(path),'storage':'GitHub Actions artifact 14 days'},'edits':edits,'eye_finish':eye,'brows':brow,'groom':hair,'wardrobe':clothes,'arm_pose':arm_pose,'images':images,'smile':smile,'pose_restore_error_m':restore,'source_rest_signature':rest,'candidate_rest_signature':build.base.rig_signature(rig),'original_head_topology_weights_keys_retained':True,'saved_material_state':material_state,'new_invalid_drivers':sorted(set(build.base.invalid_drivers(bpy))-set(invalid)),'known_blink_visual_failure':True,'blink_visual_approved':False,'embedded_python_executed':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False,'scope':'Actual coordinated face + first strand groom/wardrobe study, not final likeness/full acting/cloth or hair dynamics acceptance. Bare anatomy remains visible in separate frames.','credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0'}
 build.study.write(OUT/'report.json',record)

def verify():
 import bpy
 from PIL import Image
 r=json.loads((OUT/'report.json').read_text());path=ROOT/'.cache/r14/mom-character-r14.blend'
 if build.study.sha(path)!=r['native_artifact']['sha256']:raise ValueError('Native file hash differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(path.resolve()),use_scripts=False);bpy.context.view_layer.update()
 d=build.diagnostic.head_data(bpy);expected=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()))
 for key in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if d[key]!=expected[key]:raise ValueError('Reopen head mismatch '+key)
 if build.base.rig_signature(bpy.data.objects['RIG-rain'])!=r['candidate_rest_signature']:raise ValueError('Reopen rest mismatch')
 if build.finish.saved_material_state(bpy)!=r['saved_material_state']:raise ValueError('Reopen material mismatch')
 hair=bpy.data.objects[r['groom']['object']]
 if hair.type!='CURVES' or len(hair.data.curves)!=r['groom']['curves']:raise ValueError('Reopen native groom missing')
 for name in r['wardrobe']['objects']:
  if name not in bpy.data.objects:raise ValueError('Reopen wardrobe missing')
 f=render(bpy,OUT/'reopened-neutral-front.png',(0,-4,1.5),(0,0,1.39),.60,(512,640),32)
 a=np.asarray(Image.open(OUT/'saved-neutral-front.png'),float);b=np.asarray(Image.open(OUT/'reopened-neutral-front.png'),float);error=float(abs(a-b).mean())
 if error>.5:raise ValueError('Reopen render differs')
 packed=[{'name':i.name,'packed':bool(i.packed_file) or bool(i.packed_files)} for i in bpy.data.images if i.source in ('FILE','TILED') and i.type=='IMAGE']
 if not all(i['packed'] for i in packed):raise ValueError('External unpacked texture')
 build.study.write(OUT/'verification.json',{'status':'saved_native_reopened_in_separate_process','native_sha256':build.study.sha(path),'report_sha256':build.study.sha(OUT/'report.json'),'geometry_matches':True,'groom_curves':len(hair.data.curves),'packed_images':packed,'rgb_mae_255':error,'render':f,'independent_redownload':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False})
if __name__=='__main__':
 verify() if '--verify' in sys.argv else main()
