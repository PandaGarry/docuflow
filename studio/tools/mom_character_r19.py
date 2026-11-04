"""Actual verified R18 rig -> fine physical native hair, original face unchanged."""
import gzip,json,sys,shutil,hashlib
from pathlib import Path
import numpy as np
import mom_character_r18 as prior
import mom_groom_r19 as groom
ROOT=prior.ROOT;build=prior.build;core=prior.core;BASE=ROOT/'studio/reviews/mom-character-r19';NATIVE=ROOT/'.cache/r19/mom-character-r19.blend';SPEC=ROOT/'studio/authoring/mom-character-r19.json'
SCRIPTS=('mom_character_r19.py','mom_groom_r19.py','mom_hair_asset_r18.py','mom_groom_r15.py','mom_character_r15.py')

def curve_state(obj):
 p=np.empty(len(obj.data.attributes['position'].data)*3,np.float32);obj.data.attributes['position'].data.foreach_get('vector',p);r=np.empty(len(obj.data.attributes['radius'].data),np.float32);obj.data.attributes['radius'].data.foreach_get('value',r);shader=next(n for n in obj.data.materials[0].node_tree.nodes if n.bl_idname=='ShaderNodeBsdfHairPrincipled')
 return {'curves':len(obj.data.curves),'points':len(r),'coordinate_sha256':hashlib.sha256(p.tobytes()).hexdigest(),'radius_sha256':hashlib.sha256(r.tobytes()).hexdigest(),'parent_bone':obj.parent_bone,'shader':{k:float(shader.inputs[k].default_value) for k in ('Melanin','Melanin Redness','Roughness','Radial Roughness')}}

def frame(bpy,name,view='front',size=(1024,1280),samples=64):
 pos={'front':(0,-4,1.5),'three-quarter':(2.2,-4,1.5),'profile':(4,0,1.5),'rear':(0,4,1.5)}[view]
 return core.render(bpy,BASE/name,pos,(0,0,1.455),.48,size,samples)

def load(bpy,s):
 old=ROOT/'studio/reviews/mom-character-r18';r=json.loads((old/'report.json').read_text());bundle=ROOT/'.cache/r19-r18-source';files=list(bundle.rglob('mom-character-r18.blend'))
 if len(files)!=1 or build.study.sha(files[0])!=s['source_binary_sha256'] or r['native_artifact']['sha256']!=s['source_binary_sha256']:raise ValueError('Expected actual verified R18 binary')
 if (bundle/'studio/reviews/mom-character-r18/report.json').read_bytes()!=(old/'report.json').read_bytes():raise ValueError('Source receipt differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(files[0].resolve()),use_scripts=False);bpy.context.view_layer.update();expected=json.loads(gzip.decompress((old/'head-edit-data.json.gz').read_bytes()));actual=build.diagnostic.head_data(bpy)
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if actual[k]!=expected[k]:raise ValueError('Actual R18 head differs '+k)
 if build.finish.saved_material_state(bpy)!=r['saved_material_state'] or build.eye_fingerprints(bpy)!=r['eye_coordinate_hashes']:raise ValueError('Actual source look differs')
 for a in r['candidates'].values():
  if groom.source.fingerprint(bpy.data.objects[a['object']])!=a['saved_appearance_state']:raise ValueError('Source acquired hair differs')
 return r,actual

def main():
 import bpy
 BASE.mkdir(parents=True,exist_ok=True);s=json.loads(SPEC.read_text());old,before=load(bpy,s);rig=bpy.data.objects['RIG-rain'];rest=build.base.rig_signature(rig);invalid=build.base.invalid_drivers(bpy)
 fit_spec=ROOT/'studio/authoring/mom-character-r18.json'
 if build.study.sha(fit_spec)!=s['fitting_spec_sha256']:raise ValueError('Fitted guide source changed')
 fit=json.loads(fit_spec.read_text())['hair_fit'];obj,receipt=groom.build(bpy,rig,fit,s['fine_hair_curves']);cap=bpy.data.objects[old['candidates']['bob02']['object']];shader=cap.data.materials[0].node_tree.nodes['Principled BSDF'];shader.inputs['Roughness'].default_value=.80;shader.inputs['Specular IOR Level'].default_value=.02
 ramp=cap.data.materials[0].node_tree.nodes['R18 bounded warm brown, source strand luminance'].color_ramp
 for e in ramp.elements:e.color=(*(np.array(e.color[:3])*.45),1)
 cap_state=groom.source.fingerprint(cap);hair_state=curve_state(obj);scene=bpy.context.scene;scene.cycles.transparent_max_bounces=12
 # Gray/color anatomy is exact unchanged R18. Reuse raw frames with full provenance.
 images=[]
 for name in ('bare-front.png','clay-front.png','clay-three-quarter.png','clay-profile.png'):
  source=next(f for f in old['images'] if f['path'].endswith('/'+name));p=ROOT/source['path']
  if build.study.sha(p)!=source['sha256']:raise ValueError('Reused source anatomy changed')
  shutil.copyfile(p,BASE/name);f=dict(source);f['reused_from']=source['path'];f['path']=(BASE/name).relative_to(ROOT).as_posix();f['scope']='Raw R18 anatomy reuse, exact unchanged original face/eyes/material. Not a new R19 anatomy render.';images.append(f)
 act={n:rig.pose.bones[n].location.copy() for n in ('ACT-Lips_Corner.L','ACT-Lips_Corner.R')};neutral=build.base.head_geometry(bpy);smile=build.warm_pose.set_warm_smile(bpy,rig,.12)
 for view in ('front','three-quarter','profile','rear'):images.append(frame(bpy,f'portrait-{view}.png',view,(1024,1280) if view=='front' else (768,960),64 if view=='front' else 48))
 for n,v in act.items():rig.pose.bones[n].location=v
 rig.update_tag();bpy.context.view_layer.update();restore=float(np.linalg.norm(build.base.head_geometry(bpy)-neutral,axis=1).max());after=build.diagnostic.head_data(bpy)
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if before[k]!=after[k]:raise ValueError('Groom modified original face '+k)
 if build.finish.saved_material_state(bpy)!=old['saved_material_state'] or build.eye_fingerprints(bpy)!=old['eye_coordinate_hashes'] or rest!=build.base.rig_signature(rig) or restore>1e-7 or set(build.base.invalid_drivers(bpy))-set(invalid):raise ValueError('Original rig/face/look changed')
 shutil.copyfile(ROOT/'studio/reviews/mom-character-r18/head-edit-data.json.gz',BASE/'head-edit-data.json.gz')
 from mathutils import Vector
 camera=scene.camera;camera.location=(0,-4,1.5);camera.rotation_euler=(Vector((0,0,1.455))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.48;scene.render.resolution_x=512;scene.render.resolution_y=640;scene.cycles.samples=32;NATIVE.parent.mkdir(parents=True,exist_ok=True);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(NATIVE.resolve()),compress=True);images.append(frame(bpy,'saved-neutral-front.png',size=(512,640),samples=32))
 record={'revision':'mom-character-r19','source_run':s['source_run'],'source_binary_sha256':s['source_binary_sha256'],'spec_sha256':build.study.sha(SPEC),'scripts':{n:build.study.sha(ROOT/'studio/tools'/n) for n in SCRIPTS},'canonical_face_sha256':build.study.sha(ROOT/'studio/characters/mom/master/face.png'),'native_runtime':bpy.app.version_string,'native_artifact':{'filename':NATIVE.name,'sha256':build.study.sha(NATIVE),'storage':'GitHub Actions artifact 14 days'},'groom':receipt,'saved_curve_state':hair_state,'undercoat_object':cap.name,'saved_undercoat_state':cap_state,'head_unchanged_from_r18':True,'head_edit_data_sha256':build.study.sha(BASE/'head-edit-data.json.gz'),'saved_material_state':old['saved_material_state'],'eye_coordinate_hashes':old['eye_coordinate_hashes'],'candidate_rest_signature':rest,'new_invalid_drivers':[],'pose_restore_error_m':restore,'images':images,'smile':smile,'known_blink_visual_failure':True,'blink_visual_approved':False,'embedded_python_executed':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False,'scope':'Fine native strand hair on real R18 Rain, original head/eyes/keys/look/rest unchanged. Existing mesh is dark coverage only. Full acting/blink/cloth/hair dynamics not approved. Must visually inspect actual multiview.','credit':'Rain Rig (CC) Blender Foundation | studio.blender.org, modified CC BY4.0. Growth-guide hair geometry/UV/alpha MakeHuman CC0 via pinned HumanGen conversion.'};build.study.write(BASE/'report.json',record)

def verify():
 import bpy
 from PIL import Image
 r=json.loads((BASE/'report.json').read_text())
 if build.study.sha(NATIVE)!=r['native_artifact']['sha256']:raise ValueError('Saved binary differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(NATIVE.resolve()),use_scripts=False);bpy.context.view_layer.update();actual=build.diagnostic.head_data(bpy);expected=json.loads(gzip.decompress((BASE/'head-edit-data.json.gz').read_bytes()))
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if actual[k]!=expected[k]:raise ValueError('Reopened original head differs '+k)
 if curve_state(bpy.data.objects[r['groom']['object']])!=r['saved_curve_state'] or groom.source.fingerprint(bpy.data.objects[r['undercoat_object']])!=r['saved_undercoat_state']:raise ValueError('Reopened physical groom differs')
 if build.finish.saved_material_state(bpy)!=r['saved_material_state'] or build.eye_fingerprints(bpy)!=r['eye_coordinate_hashes'] or build.base.rig_signature(bpy.data.objects['RIG-rain'])!=r['candidate_rest_signature']:raise ValueError('Reopened face/rig/look differs')
 f=frame(bpy,'reopened-neutral-front.png',size=(512,640),samples=32);a=np.asarray(Image.open(BASE/'saved-neutral-front.png'),float);b=np.asarray(Image.open(BASE/'reopened-neutral-front.png'),float);error=float(abs(a-b).mean())
 if error>.5:raise ValueError('Reopened actual image differs')
 packed=[{'name':i.name,'packed':bool(i.packed_file) or bool(i.packed_files)} for i in bpy.data.images if i.source in ('FILE','TILED') and i.type=='IMAGE']
 if not all(i['packed'] for i in packed):raise ValueError('External texture')
 build.study.write(BASE/'verification.json',{'status':'actual_saved_binary_reopened_in_separate_process','native_sha256':build.study.sha(NATIVE),'report_sha256':build.study.sha(BASE/'report.json'),'rgb_mae_255':error,'packed_images':packed,'render':f,'independent_redownload':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False})
if __name__=='__main__':verify() if '--verify' in sys.argv else main()
