"""Reopen DOWNLOADED R9/R10 binaries; controlled portrait light, no geometry repaint.

Original source is neither acquired nor rebuilt. Diagnostic neutral and higher-
sample portrait checks are deliberately separate. No altered blend distributed.
"""
import gzip,hashlib,importlib,json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-lookdev-r10'
LIGHTS=[{'name':'PortraitKey','energy':45,'size':.75,'position':[-.8,-1.1,2.15],'color':[1,.83,.70]},
        {'name':'PortraitFill','energy':8,'size':1.3,'position':[.95,-.85,1.75],'color':[.75,.85,1]},
        {'name':'PortraitRim','energy':18,'size':.8,'position':[.5,.6,2],'color':[1,.88,.75]}]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())

def portrait_stage(bpy):
    from mathutils import Vector
    scene=bpy.context.scene
    for obj in list(bpy.data.objects):
        if obj.type=='LIGHT':bpy.data.objects.remove(obj,do_unlink=True)
    for light in LIGHTS:
        data=bpy.data.lights.new(light['name'],'AREA');data.energy=light['energy'];data.shape='DISK';data.size=light['size'];data.color=light['color']
        obj=bpy.data.objects.new(light['name'],data);scene.collection.objects.link(obj);obj.location=light['position']
        obj.rotation_euler=(Vector((0,-.08,1.47))-obj.location).to_track_quat('-Z','Y').to_euler()
    world=bpy.data.worlds.new('Portrait studio');world.use_nodes=True;scene.world=world
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.09,.07,.06,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.16
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=0
    scene.cycles.samples=96;scene.cycles.use_denoising=True
    scene.render.resolution_x=1024;scene.render.resolution_y=1024;scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2
    return scene

def render(bpy,scene,path,position):
    from mathutils import Vector
    camera=scene.camera;target=(0,0,1.47);camera.data.type='ORTHO';camera.data.ortho_scale=.48
    camera.location=position;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(path.resolve());bpy.ops.render.render(write_still=True)
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'camera':{'position':list(position),'target':list(target),'ortho_scale':.48},
            'dimensions':[1024,1024],'samples':96,'view_transform':scene.view_settings.view_transform,'look':scene.view_settings.look,
            'scope':'Controlled portrait illumination only; not a form-only or calibrated likeness comparison.'}

def main():
    import bpy
    import rain_mom_pass_a2 as controls
    import mom_smile_pose_r3 as smile
    OUT.mkdir(parents=True,exist_ok=True);sources={};images=[]
    for rev in (9,10):
        build=importlib.import_module(f'mom_head_form_r{rev}');finish=importlib.import_module(f'mom_face_paint_r{rev}')
        report_path=ROOT/f'studio/reviews/mom-head-form-r{rev}/report.json';r=read(report_path)
        for name,digest in r['scripts'].items():
            if sha(ROOT/'studio/tools'/name)!=digest:raise ValueError('Frozen source recipe changed')
        bundle=ROOT/f'.cache/lookdev-r10/r{rev}'
        paths=list(bundle.rglob(f'mom-head-form-r{rev}.blend'))
        if len(paths)!=1:raise ValueError('Expected exactly one downloaded native binary per version')
        native=paths[0]
        if sha(native)!=r['native_artifact']['sha256']:raise ValueError('Downloaded artifact binary hash mismatch')
        archived_report=bundle/f'studio/reviews/mom-head-form-r{rev}/report.json'
        if sha(archived_report)!=sha(report_path):raise ValueError('Downloaded report does not match committed evidence')
        if list((ROOT/'.cache').rglob('rain_v3.2.blend')):raise ValueError('Independent worker must not acquire original source')
        bpy.context.preferences.filepaths.use_scripts_auto_execute=False
        bpy.ops.wm.open_mainfile(filepath=str(native.resolve()),use_scripts=False);bpy.context.view_layer.update()
        state=finish.saved_material_state(bpy)
        if state!=r['saved_material_state']:raise ValueError('Downloaded material/UV/packed bytes changed')
        rig=bpy.data.objects['RIG-rain'];rest=build.base.rig_signature(rig)
        if rest!=r['candidate_rest_signature']:raise ValueError('Downloaded rig rest changed')
        expected=json.loads(gzip.decompress((ROOT/f'studio/reviews/mom-head-form-r{rev}/head-edit-data.json.gz').read_bytes()))
        actual=build.diagnostic.head_data(bpy)
        for key in ('polygons','vertex_weights','shape_keys'):
            if actual[key]!=expected[key]:raise ValueError(f'Downloaded {key} changed')
        error=max(float(np.abs(np.array(actual[key])-expected[key]).max()) for key in ('basis_vertices','neutral_evaluated_vertices_without_subdivision'))
        if error>3e-7:raise ValueError('Downloaded geometry differs')
        packed=[{'name':im.name,'packed':bool(im.packed_file) or bool(im.packed_files)} for im in bpy.data.images if im.source in ('FILE','TILED') and im.type=='IMAGE']
        if not packed or not all(im['packed'] for im in packed):raise ValueError('External unpacked dependency')
        receipt={'downloaded_binary_sha256':sha(native),'committed_report_sha256':sha(report_path),'saved_material_state':state,
                 'geometry_max_coordinate_error_m':error,'rest_signature':rest,'packed_images':packed,'source_acquired':False,'embedded_python_executed':False}
        if rev==10:
            frame=build.study.render(bpy,bpy.context.scene,bpy.context.scene.camera,OUT/'independent-neutral-front.png',(0,-4,1.5),(0,0,1.47),.48)
            with Image.open(ROOT/'studio/reviews/mom-head-form-r10/candidate-front.png') as im:a=np.asarray(im.convert('RGB'),dtype=float)
            with Image.open(OUT/'independent-neutral-front.png') as im:b=np.asarray(im.convert('RGB'),dtype=float)
            diff=np.abs(a-b);mae=float(diff.mean());p99=float(np.percentile(diff,99))
            if mae>.5 or p99>4:raise ValueError('Independent neutral differs from original native render')
            receipt.update({'independent_neutral_render':frame,'independent_neutral_rgb_mae_255':mae,'independent_neutral_rgb_p99_255':p99})
        scene=portrait_stage(bpy)
        if rev==10:images.append(render(bpy,scene,OUT/'r10-neutral-front.png',(0,-4,1.5)))
        matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones};baseline=build.base.head_geometry(bpy)
        receipt['warm_smile']=smile.set_warm_smile(bpy,rig,.4)
        views=[('front',(0,-4,1.5))] if rev==9 else [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]
        for view,position in views:images.append(render(bpy,scene,OUT/f'r{rev}-warm-{view}.png',position))
        controls.restore(bpy,rig,matrices)
        receipt['pose_restore_error_m']=float(np.linalg.norm(build.base.head_geometry(bpy)-baseline,axis=1).max())
        if receipt['pose_restore_error_m']>1e-7 or finish.saved_material_state(bpy)!=state or build.base.rig_signature(rig)!=rest or sha(native)!=r['native_artifact']['sha256']:
            raise ValueError('Portrait stage changed asset or failed to restore')
        sources[str(rev)]=receipt
    record={'revision':'mom-head-lookdev-r10','script_sha256':sha(__file__),'sources':sources,'images':images,'lights':LIGHTS,
            'world_color':[.09,.07,.06],'world_strength':.16,'portrait_smile_amount':.4,'asset_materials_changed_by_lookdev':False,
            'original_source_acquired':False,'independently_downloaded_artifacts':True,
            'art_approved':False,'user_approved':False,'production_swap_allowed':False,
            'scope':'Fresh worker, downloaded actual R9/R10 binaries, no source rebuild. Independent neutral persistence before matched higher-sample portrait light. Lighting is not evidence of geometry improvement; inspect primary clay separately. No hair/full acting/cinema-quality approval.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0'}
    (OUT/'report.json').write_text(json.dumps(record,indent=2)+'\n')

if __name__=='__main__':main()
