"""Appearance-only edits on ACTUAL verified R15; original face/eyes/rig untouched."""
import gzip,json,shutil,sys
from pathlib import Path
import numpy as np
import mom_character_r15 as core
import mom_groom_r16 as groom
import mom_wardrobe_r16 as wardrobe
build=core.build;ROOT=core.ROOT;OUT=ROOT/'studio/reviews/mom-character-r16';SPEC=ROOT/'studio/authoring/mom-character-r16.json'
SCRIPTS=('mom_character_r16.py','mom_character_r15.py','mom_groom_r16.py','mom_wardrobe_r16.py','mom_head_lookdev_r10.py','mom_smile_pose_r3.py')

def load(bpy):
 r=json.loads((ROOT/'studio/reviews/mom-character-r15/report.json').read_text());bundle=ROOT/'.cache/r16-r15-source';files=list(bundle.rglob('mom-character-r15.blend'))
 if len(files)!=1:raise ValueError('Expected actual verified R15 binary')
 path=files[0]
 if build.study.sha(path)!=r['native_artifact']['sha256']:raise ValueError('R15 binary hash mismatch')
 if (bundle/'studio/reviews/mom-character-r15/report.json').read_bytes()!=(ROOT/'studio/reviews/mom-character-r15/report.json').read_bytes():raise ValueError('R15 archived receipt differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(path.resolve()),use_scripts=False);bpy.context.view_layer.update();return r,path

def remove_added_object(bpy,name):
 obj=bpy.data.objects[name];data=obj.data;kind=obj.type;bpy.data.objects.remove(obj,do_unlink=True)
 if data.users==0:
  if kind=='CURVES':bpy.data.hair_curves.remove(data)
  elif kind=='MESH':bpy.data.meshes.remove(data)
  elif kind=='CURVE':bpy.data.curves.remove(data)

def main():
 import bpy
 OUT.mkdir(parents=True,exist_ok=True);spec=json.loads(SPEC.read_text());old,native=load(bpy);rig=bpy.data.objects['RIG-rain'];rest=build.base.rig_signature(rig);invalid=build.base.invalid_drivers(bpy)
 expected=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r15/head-edit-data.json.gz').read_bytes()));before=build.diagnostic.head_data(bpy)
 for key in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if before[key]!=expected[key]:raise ValueError('Downloaded head mismatch '+key)
 eye_before=build.eye_fingerprints(bpy)
 remove_added_object(bpy,old['groom']['object'])
 for name in old['wardrobe']['objects']:remove_added_object(bpy,name)
 hair=groom.build(bpy,rig,spec['groom']);clothes=wardrobe.build(bpy,rig,spec['wardrobe']);core.OUT=OUT;core.check_smile_roundtrip(bpy,rig,'appearance')
 after=build.diagnostic.head_data(bpy)
 for key in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if after[key]!=before[key]:raise ValueError('Appearance pass changed original head '+key)
 if eye_before!=build.eye_fingerprints(bpy):raise ValueError('Appearance pass changed original eyes')
 if build.finish.saved_material_state(bpy)!=old['saved_material_state']:raise ValueError('Appearance pass changed head material')
 shutil.copyfile(ROOT/'studio/reviews/mom-character-r15/head-edit-data.json.gz',OUT/'head-edit-data.json.gz')
 images=[]
 # Reuse raw verified R15 anatomy frames: exact same retained head, not re-rendered anatomy.
 for name in ('clay-front.png','clay-three-quarter.png','clay-profile.png','bare-front.png'):
  f=next(f for f in old['images'] if f['path'].endswith('/'+name));src=ROOT/f['path']
  if build.study.sha(src)!=f['sha256']:raise ValueError('R15 anatomy frame changed')
  shutil.copyfile(src,OUT/name);frame=dict(f);frame['path']=(OUT/name).relative_to(ROOT).as_posix();frame['reused_from']=f['path'];frame['scope']='Unchanged R15 head/eyes; raw frame reuse, not a new R16 anatomy render';images.append(frame)
 from mathutils import Vector
 scene=bpy.context.scene;camera=scene.camera;camera.location=(0,-4,1.5);camera.data.ortho_scale=.60;camera.rotation_euler=(Vector((0,0,1.39))-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.resolution_x=1024;scene.render.resolution_y=1280
 bpy.ops.file.pack_all();path=ROOT/'.cache/r16/mom-character-r16.blend';path.parent.mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=str(path.resolve()),compress=True)
 images.append(core.render(bpy,OUT/'saved-neutral-front.png',(0,-4,1.5),(0,0,1.39),.60,(512,640),32))
 act={n:rig.pose.bones[n].location.copy() for n in ('ACT-Lips_Corner.L','ACT-Lips_Corner.R')};baseline=build.base.head_geometry(bpy);smile=build.warm_pose.set_warm_smile(bpy,rig,.4)
 for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:images.append(core.render(bpy,OUT/f'portrait-{view}.png',position,(0,0,1.39),.60,(1024,1280) if view=='front' else (768,960),64 if view=='front' else 48))
 for n,location in act.items():rig.pose.bones[n].location=location
 rig.update_tag();bpy.context.view_layer.update();restore=float(np.linalg.norm(build.base.head_geometry(bpy)-baseline,axis=1).max());newinvalid=sorted(set(build.base.invalid_drivers(bpy))-set(invalid))
 if restore>1e-7 or rest!=build.base.rig_signature(rig) or newinvalid:raise ValueError('Appearance pass rig/restore failure')
 record={'revision':spec['revision'],'source_run':41827110660,'downloaded_r15_binary_sha256':build.study.sha(native),'source_r15_report_sha256':build.study.sha(ROOT/'studio/reviews/mom-character-r15/report.json'),'spec_sha256':build.study.sha(SPEC),'scripts':{n:build.study.sha(ROOT/'studio/tools'/n) for n in SCRIPTS},'canonical_face_sha256':build.study.sha(ROOT/'studio/characters/mom/master/face.png'),'head_edit_data_sha256':build.study.sha(OUT/'head-edit-data.json.gz'),'native_artifact':{'filename':path.name,'sha256':build.study.sha(path),'storage':'GitHub Actions artifact 14 days'},'head_edits_this_revision':[],'head_unchanged_since_r15':True,'eye_coordinates_unchanged_since_r15':True,'eye_coordinate_hashes':eye_before,'face_design_source':'mom-character-r15','groom':hair,'wardrobe':clothes,'brows':old['brows'],'images':images,'smile':smile,'pose_restore_error_m':restore,'source_rest_signature':rest,'candidate_rest_signature':build.base.rig_signature(rig),'saved_material_state':build.finish.saved_material_state(bpy),'new_invalid_drivers':newinvalid,'known_blink_visual_failure':True,'blink_visual_approved':False,'embedded_python_executed':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False,'scope':'Original verified R15 face/eyes/keys/rig retained without reconstruction. Groom roots/waves/tips and fitted vest/collar refinement only. Bare anatomy frames explicitly reused, not newly rendered. Not final likeness or full acting/dynamics acceptance.','credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0'}
 build.study.write(OUT/'report.json',record)

def verify():
 import bpy
 from PIL import Image
 r=json.loads((OUT/'report.json').read_text());path=ROOT/'.cache/r16/mom-character-r16.blend'
 if build.study.sha(path)!=r['native_artifact']['sha256']:raise ValueError('Native hash differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(path.resolve()),use_scripts=False);bpy.context.view_layer.update()
 d=build.diagnostic.head_data(bpy);expected=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()))
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if d[k]!=expected[k]:raise ValueError('Reopen original head mismatch '+k)
 if build.eye_fingerprints(bpy)!=r['eye_coordinate_hashes']:raise ValueError('Reopen eyes differ')
 if build.finish.saved_material_state(bpy)!=r['saved_material_state']:raise ValueError('Reopen head materials differ')
 if build.base.rig_signature(bpy.data.objects['RIG-rain'])!=r['candidate_rest_signature']:raise ValueError('Reopen rest differs')
 hair=bpy.data.objects[r['groom']['object']]
 if hair.type!='CURVES' or len(hair.data.curves)!=r['groom']['curves']:raise ValueError('Reopen native groom differs')
 for n in r['wardrobe']['objects']:
  if n not in bpy.data.objects:raise ValueError('Reopen clothing missing')
 f=core.render(bpy,OUT/'reopened-neutral-front.png',(0,-4,1.5),(0,0,1.39),.60,(512,640),32)
 a=np.asarray(Image.open(OUT/'saved-neutral-front.png'),float);b=np.asarray(Image.open(OUT/'reopened-neutral-front.png'),float);error=float(abs(a-b).mean())
 if error>.5:raise ValueError('Reopen image differs')
 packed=[{'name':i.name,'packed':bool(i.packed_file) or bool(i.packed_files)} for i in bpy.data.images if i.source in ('FILE','TILED') and i.type=='IMAGE']
 if not all(i['packed'] for i in packed):raise ValueError('Unpacked texture')
 build.study.write(OUT/'verification.json',{'status':'actual_saved_binary_reopened_in_separate_process','native_sha256':build.study.sha(path),'report_sha256':build.study.sha(OUT/'report.json'),'head_and_eyes_match':True,'groom_curves':len(hair.data.curves),'packed_images':packed,'rgb_mae_255':error,'render':f,'independent_redownload':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False})
if __name__=='__main__':verify() if '--verify' in sys.argv else main()
