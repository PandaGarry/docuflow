"""Actual R17 -> fitted CC0 hair assets and bounded original-head finish."""
import gzip,json,sys,hashlib,os
from pathlib import Path
import numpy as np
import mom_character_r17 as prior
import mom_character_r15 as core
import mom_face_finish_r18 as face
import mom_face_paint_r17 as source_paint
import mom_face_paint_r18 as paint
import mom_hair_asset_r18 as hair
import mom_head_cage as model
from mom_face_finish_r7 import linear
ROOT=core.ROOT;build=core.build;BASE=ROOT/'studio/reviews/mom-character-r18';OUT=BASE;SPEC=ROOT/'studio/authoring/mom-character-r18.json';NATIVE=ROOT/'.cache/r18/mom-character-r18.blend'
SCRIPTS=('mom_character_r18.py','mom_face_finish_r18.py','mom_hair_asset_r18.py','mom_face_paint_r17.py','mom_face_paint_r18.py','mom_wardrobe_finish_r18.py','mom_character_r15.py')

def load(bpy,s):
 bundle=ROOT/'.cache/r18-r17-source';paths=list(bundle.rglob('mom-character-r17.blend'));r=json.loads((ROOT/'studio/reviews/mom-character-r17/report.json').read_text())
 if len(paths)!=1 or build.study.sha(paths[0])!=s['source_binary_sha256'] or s['source_binary_sha256']!=r['native_artifact']['sha256']:raise ValueError('Expected actual hash-verified R17')
 if (bundle/'studio/reviews/mom-character-r17/report.json').read_bytes()!=(ROOT/'studio/reviews/mom-character-r17/report.json').read_bytes():raise ValueError('Source archived receipt differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(paths[0].resolve()),use_scripts=False);bpy.context.view_layer.update();actual=build.diagnostic.head_data(bpy);expected=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-character-r17/head-edit-data.json.gz').read_bytes()))
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if actual[k]!=expected[k]:raise ValueError('Source head mismatch '+k)
 if build.finish.saved_material_state(bpy)!=r['saved_material_state']:raise ValueError('Source materials differ')
 return r,actual

def probe_albedo(bpy):
 mesh=bpy.data.objects['GEO-rain-head'].data;shader=mesh.materials[0].node_tree.nodes['Principled BSDF'];node=shader.inputs['Base Color'].links[0].from_node;im=node.image;scale=node.inputs['Vector'].links[0].from_node;subtract=scale.inputs[0].links[0].from_node;uv=source_paint.render_uv(mesh);pixels=np.empty(len(im.pixels),np.float32);im.pixels.foreach_get(pixels);pixels=pixels.reshape(im.size[1],im.size[0],4);out={}
 for i in (6341,6375,3150):
  values=[]
  for loop in mesh.loops:
   if loop.vertex_index!=i:continue
   co=(np.array(uv.data[loop.index].uv)-np.array(subtract.inputs[1].default_value[:2]))*np.array(scale.inputs[1].default_value[:2]);xy=np.clip(np.round(co*np.array(im.size)-.5).astype(int),0,np.array(im.size)-1);values.append(pixels[xy[1],xy[0],:3].tolist())
  out[str(i)]={'original_uv_texel_linear_rgb':np.mean(values,axis=0).tolist(),'uv_loop_samples':len(values)}
 return {'active_image':im.name,'samples':out,'method':'Actual active packed EXR texels sampled using original render UV and actual shader domain transform; not a beauty-frame color score.'}

def frame(bpy,name,view='front',size=(1024,1280),samples=64,bare=False):
 pos={'front':(0,-4,1.5),'three-quarter':(2.2,-4,1.5),'profile':(4,0,1.5),'rear':(0,4,1.5)}[view]
 return core.render(bpy,OUT/name,pos,(0,0,1.47) if bare else (0,0,1.455),.48,size,samples)

def main():
 import bpy
 global OUT
 s=json.loads(SPEC.read_text());scope=os.environ.get('R18_RENDER_SCOPE',s['render_scope']);assert scope in ('preview','final');preview=scope=='preview'
 if preview:OUT=BASE/'preview'
 OUT.mkdir(parents=True,exist_ok=True);old,before=load(bpy,s);source_probe=probe_albedo(bpy);rig=bpy.data.objects['RIG-rain'];rest=build.base.rig_signature(rig);invalid=build.base.invalid_drivers(bpy);eyes=build.eye_fingerprints(bpy)
 head=bpy.data.objects['GEO-rain-head'];edits=[core.edit_blocks(bpy,head,lambda p:face.fair(p,before['polygons'],s['fairing']))]
 original=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source'];paint_receipt=paint.apply(bpy,original,s['palette_srgb'],s['linear_albedo_energy_scale']);candidate_probe=probe_albedo(bpy)
 import mom_wardrobe_finish_r18 as wardrobe
 wardrobe_receipt=wardrobe.apply(bpy)
 brow=bpy.data.objects['GEO-rain-eyebrows'].data.materials[0];brow.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*linear(s['palette_srgb']['brows']),1)
 for name in old['groom']['objects']+[old['groom']['surface_fiber_object']]:prior.prior.remove_added_object(bpy,name)
 candidates={};objects={}
 for name in ('bob02','long01'):
  obj,record=hair.build(bpy,rig,name,s['hair_fit']);obj.hide_render=True;objects[name]=obj;candidates[name]=record
 # Same explicit held R17 stage for meaningful face comparison.
 prior.stage(bpy,json.loads((ROOT/'studio/authoring/mom-character-r17.json').read_text()));scene=bpy.context.scene;scene.cycles.transparent_max_bounces=32
 images=[];act={n:rig.pose.bones[n].location.copy() for n in ('ACT-Lips_Corner.L','ACT-Lips_Corner.R')};neutral=build.base.head_geometry(bpy);smile=build.warm_pose.set_warm_smile(bpy,rig,s['smile_amount'])
 if preview:
  for name,obj in objects.items():
   obj.hide_render=False;images.append(frame(bpy,f'candidate-{name}-front.png',size=(640,800),samples=32));obj.hide_render=True
 selected=objects[s['selected_hair_asset']];selected.hide_render=False
 for view in (('three-quarter','profile') if preview else ('front','three-quarter','profile','rear')):images.append(frame(bpy,f'portrait-{view}.png',view,(640,800) if preview else ((1024,1280) if view=='front' else (768,960)),32 if preview else 64))
 for n,v in act.items():rig.pose.bones[n].location=v
 rig.update_tag();bpy.context.view_layer.update();restore=float(np.linalg.norm(build.base.head_geometry(bpy)-neutral,axis=1).max())
 hidden={n:bpy.data.objects[n].hide_render for n in old['wardrobe']['objects']+['GEO-rain-body','GROOM-mom-R17-brow-fibers']}
 selected.hide_render=True
 for n in hidden:bpy.data.objects[n].hide_render=True
 images.append(frame(bpy,'bare-front.png',size=(640,640) if preview else (1024,1024),samples=32 if preview else 64,bare=True))
 if not preview:
  mats=list(head.data.materials);clay=build.diagnostic.flat_material(bpy,'R18 neutral clay',(.45,.45,.45))
  for i in range(len(mats)):head.data.materials[i]=clay
  for view in ('front','three-quarter','profile'):images.append(frame(bpy,f'clay-{view}.png',view,(768,768),32,True))
  for i,m in enumerate(mats):head.data.materials[i]=m
 selected.hide_render=False
 for n,v in hidden.items():bpy.data.objects[n].hide_render=v
 after=build.diagnostic.head_data(bpy)
 for k in ('polygons','vertex_weights','shape_keys','related_rest_bones'):
  if before[k]!=after[k]:raise ValueError('Original structure changed '+k)
 state=build.finish.saved_material_state(bpy)
 if state['original_uv_sha256']!=old['saved_material_state']['original_uv_sha256'] or build.eye_fingerprints(bpy)!=eyes:raise ValueError('Original eye or UV changed')
 if restore>1e-7 or rest!=build.base.rig_signature(rig) or set(build.base.invalid_drivers(bpy))-set(invalid):raise ValueError('Rig/pose restoration failed')
 (OUT/'head-edit-data.json.gz').write_bytes(gzip.compress(json.dumps(after,separators=(',',':')).encode(),mtime=0))
 from mathutils import Vector
 camera=scene.camera;camera.location=(0,-4,1.5);camera.rotation_euler=(Vector((0,0,1.455))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.48;scene.render.resolution_x=512;scene.render.resolution_y=640;scene.cycles.samples=32
 NATIVE.parent.mkdir(parents=True,exist_ok=True);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(NATIVE.resolve()),compress=True)
 if not preview:images.append(frame(bpy,'saved-neutral-front.png',size=(512,640),samples=32))
 record={'revision':s['revision'],'preview_only':preview,'source_run':s['source_run'],'source_binary_sha256':s['source_binary_sha256'],'spec_sha256':build.study.sha(SPEC),'scripts':{n:build.study.sha(ROOT/'studio/tools'/n) for n in SCRIPTS},'asset_manifest_sha256':build.study.sha(hair.ASSETS/'manifest.json'),'canonical_face_sha256':build.study.sha(ROOT/'studio/characters/mom/master/face.png'),'native_artifact':{'filename':NATIVE.name,'sha256':build.study.sha(NATIVE),'storage':'GitHub Actions artifact 14 days'},'head_edit_data_sha256':build.study.sha(OUT/'head-edit-data.json.gz'),'edits':edits,'source_albedo_probe':source_probe,'candidate_albedo_probe':candidate_probe,'uv_paint':paint_receipt,'candidates':candidates,'selected_hair_asset':s['selected_hair_asset'],'source_eyes_retained':True,'eye_coordinate_hashes':eyes,'saved_material_state':state,'saved_skin_shader':prior.skin_shader_state(bpy),'candidate_rest_signature':rest,'new_invalid_drivers':[],'pose_restore_error_m':restore,'images':images,'smile':smile,'wardrobe':old['wardrobe'],'wardrobe_unchanged':False,'collar_finish':wardrobe_receipt,'known_blink_visual_failure':True,'blink_visual_approved':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False,'embedded_python_executed':False,'visible_geometry_inventory':[{'object':o.name,'type':o.type,'materials':[m.name for m in o.data.materials if m]} for o in bpy.context.scene.objects if o.type in ('MESH','CURVE','CURVES') and not o.hide_render],'native_runtime':{'blender':bpy.app.version_string,'render_engine':scene.render.engine,'cycles_device':scene.cycles.device},'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY4.0. Hair MakeHuman CC0 system assets; pinned conversion by HumanGen Web.','scope':'Actual original Rain with acquired fitted hair assets. Full acting/blink/cloth/hair dynamics not approved; visual review required.'}
 build.study.write(OUT/'report.json',record)

def verify():
 import bpy
 from PIL import Image
 r=json.loads((BASE/'report.json').read_text())
 if build.study.sha(NATIVE)!=r['native_artifact']['sha256']:raise ValueError('Binary hash differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False;bpy.ops.wm.open_mainfile(filepath=str(NATIVE.resolve()),use_scripts=False);bpy.context.view_layer.update();actual=build.diagnostic.head_data(bpy);expected=json.loads(gzip.decompress((BASE/'head-edit-data.json.gz').read_bytes()))
 for k in ('basis_vertices','polygons','vertex_weights','shape_keys','related_rest_bones'):
  if actual[k]!=expected[k]:raise ValueError('Reopened original head differs '+k)
 if build.finish.saved_material_state(bpy)!=r['saved_material_state'] or build.eye_fingerprints(bpy)!=r['eye_coordinate_hashes'] or prior.skin_shader_state(bpy)!=r['saved_skin_shader']:raise ValueError('Reopened look differs')
 if build.base.rig_signature(bpy.data.objects['RIG-rain'])!=r['candidate_rest_signature']:raise ValueError('Reopened rig differs')
 for a in r['candidates'].values():
  obj=bpy.data.objects[a['object']]
  if len(obj.data.vertices)!=a['vertices'] or obj.parent_bone!='DEF-Head' or hair.fingerprint(obj)!=a['saved_appearance_state']:raise ValueError('Reopened hair differs')
 body=bpy.data.objects['GEO-rain-body'].data.materials[0].node_tree.nodes['Principled BSDF']
 if list(body.inputs['Base Color'].default_value)!=r['uv_paint']['matching_body_skin_after']:raise ValueError('Reopened neck/body pigment differs')
 f=frame(bpy,'reopened-neutral-front.png',size=(512,640),samples=32);a=np.asarray(Image.open(BASE/'saved-neutral-front.png'),float);b=np.asarray(Image.open(BASE/'reopened-neutral-front.png'),float);err=float(abs(a-b).mean())
 if err>.5:raise ValueError('Reopened image differs')
 packed=[{'name':i.name,'packed':bool(i.packed_file) or bool(i.packed_files)} for i in bpy.data.images if i.source in ('FILE','TILED') and i.type=='IMAGE']
 if not all(i['packed'] for i in packed):raise ValueError('Unpacked texture')
 build.study.write(BASE/'verification.json',{'status':'actual_saved_binary_reopened_in_separate_process','native_sha256':build.study.sha(NATIVE),'report_sha256':build.study.sha(BASE/'report.json'),'rgb_mae_255':err,'packed_images':packed,'render':f,'independent_redownload':False,'art_approved':False,'user_approved':False,'production_swap_allowed':False})
if __name__=='__main__':verify() if '--verify' in sys.argv else main()
