"""Actual R16 binary -> coordinated original Rain R17 head, paint and hair.

Preview and final both build the same native asset. Preview is a real render,
not an acceptance gate. Final also renders unobscured clay and reopens binary.
"""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
import mom_character_r16 as prior
import mom_character_r15 as core
import mom_face_anatomy_r17 as anatomy
import mom_face_paint_r17 as paint
import mom_groom_r17 as groom
import mom_head_cage as model
import mom_head_lookdev_r10 as portrait
from mom_face_finish_r7 import linear,smoothstep
ROOT=core.ROOT;build=core.build;BASE=ROOT/'studio/reviews/mom-character-r17';OUT=BASE;SPEC=ROOT/'studio/authoring/mom-character-r17.json';NATIVE=ROOT/'.cache/r17/mom-character-r17.blend'
SCRIPTS=('mom_character_r17.py','mom_face_anatomy_r17.py','mom_face_paint_r17.py','mom_groom_r17.py','mom_character_r15.py','mom_smile_pose_r3.py')

def load(bpy,spec):
 bundle=ROOT/'.cache/r17-r16-source';files=list(bundle.rglob('mom-character-r16.blend'))
 if len(files)!=1:raise ValueError('Expected one actual verified R16 binary')
 native=files[0];report=ROOT/'studio/reviews/mom-character-r16/report.json';r=json.loads(report.read_text())
 if build.study.sha(native)!=spec['source_binary_sha256'] or build.study.sha(native)!=r['native_artifact']['sha256']:raise ValueError('Source binary hash mismatch')
 if (bundle/'studio/reviews/mom-character-r16/report.json').read_bytes()!=report.read_bytes():raise ValueError('Archived source receipt mismatch')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(native.resolve()),use_scripts=False);bpy.context.view_layer.update()
 expected=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r16/head-edit-data.json.gz').read_bytes()));actual=build.diagnostic.head_data(bpy)
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if actual[k]!=expected[k]:raise ValueError('Downloaded head differs '+k)
 if build.finish.saved_material_state(bpy)!=r['saved_material_state']:raise ValueError('Source paint differs')
 return r,actual

def brow_field(p,spec):
 q=p.copy();x=abs(p[:,0]);q[:,2]+=spec['inner_lift_m']+(spec['outer_lift_m']-spec['inner_lift_m'])*smoothstep(.025,.065,x);return q

def eyes(bpy,spec):
 before=build.eye_fingerprints(bpy);edits=[core.edit_blocks(bpy,bpy.data.objects['GEO-rain-eyes'],lambda p:anatomy.iris_field(p,spec['iris']))]
 def dots(p):
  q=p.copy()
  for side in (-1,1):
   mask=p[:,0]*side>0
   if not mask.any():continue
   c=p[mask].mean(0)
   for axis in (0,2):q[mask,axis]=c[axis]+(p[mask,axis]-c[axis])*spec['iris']['catchlight_scale']
  q[:,2]+=spec['iris']['catchlight_lift_m'];return q
 edits.append(core.edit_blocks(bpy,bpy.data.objects['GEO-rain-eye_dots'],dots))
 ramp=bpy.data.materials['MAT-rain.eyes'].node_tree.nodes['Mom R6 gray blue iris'].color_ramp
 for e,color in zip(ramp.elements,('#111C22','#667983','#8CA5AB','#B0BEC1','#EEEAE3','#FFFFFF')):e.color=(*linear(color),1)
 after=build.eye_fingerprints(bpy)
 if before['GEO-rain-eye_cornea']!=after['GEO-rain-eye_cornea']:raise ValueError('Cornea changed')
 return edits,{'before':before,'after':after,'native_uv_texture_retained':True,'cornea_coordinates_retained':True,'iris_and_dots_y_coordinates_retained':True}

def stage(bpy,spec):
 scene=portrait.portrait_stage(bpy)
 for name,key in (('PortraitKey','key_energy_w'),('PortraitFill','fill_energy_w'),('PortraitRim','rim_energy_w')):bpy.data.objects[name].data.energy=spec['stage'][key]
 scene.view_settings.exposure=spec['stage']['exposure'];return scene

def frame(bpy,name,view='front',size=(1024,1280),samples=64,bare=False):
 pos={'front':(0,-4,1.5),'three-quarter':(2.2,-4,1.5),'profile':(4,0,1.5)}[view]
 return core.render(bpy,OUT/name,pos,(0,0,1.47) if bare else (0,0,1.455),.48,size,samples)

def main():
 import bpy
 global OUT
 preview='--preview' in sys.argv
 if preview:OUT=BASE/'preview-2'
 OUT.mkdir(parents=True,exist_ok=True);s=json.loads(SPEC.read_text());old,before=load(bpy,s);rig=bpy.data.objects['RIG-rain'];rest=build.base.rig_signature(rig);invalid=build.base.invalid_drivers(bpy)
 if build.study.sha(ROOT/s['reference']['path'])!=s['reference']['sha256']:raise ValueError('Canonical changed')
 head=bpy.data.objects['GEO-rain-head'];p=np.array(before['basis_vertices']);delta=anatomy.head_residual(p,s);tri=np.array([[f[0],f[j],f[j+1]] for f in before['polygons'] for j in range(1,len(f)-1)]);key_deltas=[]
 limiter={'method':'Continuous spatial deformation reevaluated on each original corrective; no shared vertex-wise attenuation. Strict orientation check on every block remains enabled.'}
 def head_field(p):
  d=anatomy.head_residual(p,s);q=p+d;a=p[tri];b=q[tri];na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0]);valid=np.linalg.norm(na,axis=1)>1e-12
  if (np.einsum('ij,ij->i',na[valid],nb[valid])<=0).any():raise ValueError('Residual reverses original corrective triangle')
  key_deltas.append(hashlib.sha256(d.tobytes()).hexdigest());return q
 edits=[core.edit_blocks(bpy,head,head_field)]
 for name in ('GEO-rain-gums_lower','GEO-rain-gums_upper','GEO-rain-tongue'):edits.append(core.edit_blocks(bpy,bpy.data.objects[name],lambda p:anatomy.oral_field(p,s['mouth'])))
 eye_edits,eye=eyes(bpy,s);edits+=eye_edits
 edits.append(core.edit_blocks(bpy,bpy.data.objects['GEO-rain-eyebrows'],lambda p:brow_field(p,s['brows'])))
 fiber=bpy.data.objects[old['brows']['fiber_object']];a=fiber.data.attributes['position'];v=np.empty(len(a.data)*3,dtype=np.float32);a.data.foreach_get('vector',v);a.data.foreach_set('vector',brow_field(v.reshape(-1,3),s['brows']).ravel());fiber.name='GROOM-mom-R17-brow-fibers'
 browmat=bpy.data.objects['GEO-rain-eyebrows'].data.materials[0];browmat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*linear(s['palette_srgb']['brows']),1)
 original=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source'];paint_receipt=paint.apply(bpy,original,s['palette_srgb'])
 prior.remove_added_object(bpy,old['groom']['object']);hair=groom.build(bpy,rig,s['hair'],s['palette_srgb']['hair']);stage(bpy,s)
 after=build.diagnostic.head_data(bpy)
 for k in ('polygons','vertex_weights','shape_keys','related_rest_bones'):
  if after[k]!=before[k]:raise ValueError('Original head structure changed '+k)
 if build.finish.saved_material_state(bpy)['original_uv_sha256']!=old['saved_material_state']['original_uv_sha256']:raise ValueError('Original UV changed')
 (OUT/'head-edit-data.json.gz').write_bytes(gzip.compress(json.dumps(after,separators=(',',':')).encode(),mtime=0))
 NATIVE.parent.mkdir(parents=True,exist_ok=True);frame_config=(512,640);camera=bpy.context.scene.camera
 # Same neutral render configuration before save and during reopen.
 from mathutils import Vector
 camera.location=(0,-4,1.5);camera.rotation_euler=(Vector((0,0,1.455))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.48
 bpy.context.scene.render.resolution_x=512;bpy.context.scene.render.resolution_y=640;bpy.context.scene.cycles.samples=32
 bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(NATIVE.resolve()),compress=True)
 images=[]
 if not preview:images.append(frame(bpy,'saved-neutral-front.png',size=frame_config,samples=32))
 act={n:rig.pose.bones[n].location.copy() for n in ('ACT-Lips_Corner.L','ACT-Lips_Corner.R')};neutral=build.base.head_geometry(bpy);smile=build.warm_pose.set_warm_smile(bpy,rig,s['portrait_smile_amount'])
 for view in (('front','three-quarter') if preview else ('front','three-quarter','profile')):
  images.append(frame(bpy,f'portrait-{view}.png',view,(640,800) if preview else ((1024,1280) if view=='front' else (768,960)),32 if preview else 64))
 for n,v in act.items():rig.pose.bones[n].location=v
 rig.update_tag();bpy.context.view_layer.update();restore=float(np.linalg.norm(build.base.head_geometry(bpy)-neutral,axis=1).max())
 # Explicitly unobscured anatomy, not a hidden-face success claim.
 hide_names=hair['objects']+[hair['surface_fiber_object']]+old['wardrobe']['objects']+['GEO-rain-body',fiber.name]
 hidden={n:bpy.data.objects[n].hide_render for n in hide_names}
 for n in hidden:bpy.data.objects[n].hide_render=True
 images.append(frame(bpy,'bare-front.png',size=(640,640) if preview else (1024,1024),samples=32 if preview else 64,bare=True))
 if not preview:
  mats=list(head.data.materials);gray=build.diagnostic.flat_material(bpy,'R17 neutral clay',(.45,.45,.45))
  for i in range(len(mats)):head.data.materials[i]=gray
  for view in ('front','three-quarter','profile'):images.append(frame(bpy,f'clay-{view}.png',view,(768,768),32,True))
  for i,m in enumerate(mats):head.data.materials[i]=m
 for n,state in hidden.items():bpy.data.objects[n].hide_render=state
 newinvalid=sorted(set(build.base.invalid_drivers(bpy))-set(invalid))
 if restore>1e-7 or rest!=build.base.rig_signature(rig) or newinvalid:raise ValueError('Rig/restoration failure')
 record={'revision':s['revision'],'preview_only':preview,'source_run':s['source_run'],'source_binary_sha256':s['source_binary_sha256'],'spec_sha256':build.study.sha(SPEC),'scripts':{n:build.study.sha(ROOT/'studio/tools'/n) for n in SCRIPTS},'canonical_face_sha256':s['reference']['sha256'],'head_edit_data_sha256':build.study.sha(OUT/'head-edit-data.json.gz'),'edits':edits,'corrective_orientation_limiter':limiter,'actual_landmark_deltas_m':{str(i):delta[i].tolist() for i in (3150,6375,6341,486)},'corrective_transport':'Smooth spatial deformation reevaluated for every original block; original key names/weights/drivers retained, corrective deltas deliberately transported.','original_head_key_count':len(key_deltas),'original_topology_weights_and_key_names_retained':True,'native_artifact':{'filename':NATIVE.name,'sha256':build.study.sha(NATIVE),'storage':'GitHub Actions artifact, 14 days'},'groom':hair,'wardrobe':old['wardrobe'],'wardrobe_unchanged_from_r16':True,'eye_finish':eye,'eye_coordinate_hashes':build.eye_fingerprints(bpy),'uv_paint':paint_receipt,'saved_material_state':build.finish.saved_material_state(bpy),'stage':s['stage'],'images':images,'smile':smile,'pose_restore_error_m':restore,'candidate_rest_signature':rest,'new_invalid_drivers':newinvalid,'known_blink_visual_failure':True,'blink_visual_approved':False,'embedded_python_executed':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False,'scope':'Head identity and new sculpted hair. Clothes unchanged; full acting/blink/lip-sync and hair dynamics are not approved. Actual render must be visually reviewed, no automatic likeness certification.','credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0'}
 build.study.write(OUT/'report.json',record)

def verify():
 import bpy
 from PIL import Image
 r=json.loads((BASE/'report.json').read_text())
 if build.study.sha(NATIVE)!=r['native_artifact']['sha256']:raise ValueError('Native hash differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(NATIVE.resolve()),use_scripts=False);bpy.context.view_layer.update();actual=build.diagnostic.head_data(bpy);expected=json.loads(gzip.decompress((BASE/'head-edit-data.json.gz').read_bytes()))
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if actual[k]!=expected[k]:raise ValueError('Reopened head differs '+k)
 if build.finish.saved_material_state(bpy)!=r['saved_material_state'] or build.eye_fingerprints(bpy)!=r['eye_coordinate_hashes']:raise ValueError('Reopened materials/eyes differ')
 if build.base.rig_signature(bpy.data.objects['RIG-rain'])!=r['candidate_rest_signature']:raise ValueError('Reopened rest differs')
 for name in r['groom']['objects']:
  obj=bpy.data.objects[name]
  if obj.type!='MESH' or len(obj.data.vertices)!=3200:raise ValueError('Reopened sculpted lock differs')
 f=frame(bpy,'reopened-neutral-front.png',size=(512,640),samples=32);a=np.asarray(Image.open(BASE/'saved-neutral-front.png'),float);b=np.asarray(Image.open(BASE/'reopened-neutral-front.png'),float);error=float(abs(a-b).mean())
 if error>.5:raise ValueError('Reopen image differs')
 packed=[{'name':i.name,'packed':bool(i.packed_file) or bool(i.packed_files)} for i in bpy.data.images if i.source in ('FILE','TILED') and i.type=='IMAGE']
 if not all(i['packed'] for i in packed):raise ValueError('Unpacked texture')
 build.study.write(BASE/'verification.json',{'status':'actual_saved_binary_reopened_in_separate_process','native_sha256':build.study.sha(NATIVE),'report_sha256':build.study.sha(BASE/'report.json'),'head_and_eyes_match':True,'packed_images':packed,'rgb_mae_255':error,'render':f,'independent_redownload':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False})
if __name__=='__main__':verify() if '--verify' in sys.argv else main()
