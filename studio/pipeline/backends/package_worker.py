"""One bounded chunk from an external trusted-local package; no procedural fallback."""
from __future__ import annotations
import argparse
import importlib.metadata
from pathlib import Path
import resource
import time

from ..contracts import ROOT, ContractError, file_hash, load_json
from ..packages import validate_bundle, append_package, bind, apply
from ..resources import effective_threads
from ..timeline import evaluate
from ..run_probe import write_json


def stage(bpy, project):
    from mathutils import Vector
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = project['render']['samples']
    scene.cycles.seed = project['render']['seed']
    scene.cycles.use_denoising = project['render']['denoise']
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = effective_threads(project['render']['threads'])
    scene.render.resolution_x, scene.render.resolution_y = project['resolution']
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = project['fps']['num'], project['fps']['den']
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = -.5
    scene.unit_settings.system = 'METRIC'
    scene.world = bpy.data.worlds.new('STUDIO_World')
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (.72,.75,.69,1)
    bg.inputs[1].default_value = .35
    bpy.ops.mesh.primitive_plane_add(size=200)
    floor = bpy.context.object
    floor.name = 'STUDIO_Floor'
    mat = bpy.data.materials.new('STUDIO_Matte')
    mat.diffuse_color = (.70,.74,.68,1)
    mat.use_nodes = True
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = mat.diffuse_color
    mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .8
    floor.data.materials.append(mat)
    for name, loc, energy, size in [('Key',(-3,4,5),600,4),('Fill',(4,2,3),350,4),('Rim',(1,-3,4),650,3)]:
        bpy.ops.object.light_add(type='AREA',location=loc)
        lamp=bpy.context.object;lamp.name='STUDIO_'+name;lamp.data.energy=energy;lamp.data.size=size
        lamp.rotation_euler=(Vector((0,0,1.4))-lamp.location).to_track_quat('-Z','Y').to_euler()
    settings=project.get('camera',{'position':[2.5,7,2.9],'target':[.05,0,1.38],'ortho_scale':5.8})
    bpy.ops.object.camera_add(location=settings['position'])
    camera=bpy.context.object;camera.name='STUDIO_Camera'
    camera.rotation_euler=(Vector(settings['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=settings['ortho_scale'];scene.camera=camera
    return scene


def overlay(path, rig_test=False, revision="r2", deformation_test=False):
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(path) as source:
        image = source.convert('RGB')
    scale = image.width/960
    def font(size):
        return ImageFont.truetype(str(ROOT/'studio/fonts/Nunito-700.ttf'),max(8,round(size*scale)))
    draw=ImageDraw.Draw(image)
    draw.text((round(32*scale),round(22*scale)),(f'ПАПА / РИГ {revision}' if rig_test else 'ПАПА / 3D-БЛОКИНГ'),font=font(25),fill='#253c32')
    draw.text((round(32*scale),round(59*scale)),(('Плечи · локти · кисти' if deformation_test else 'IK ног · пальцы · тест опоры') if rig_test else 'Внешний .blend · IK · контроль памяти'),font=font(15),fill='#4c6457')
    draw.text((round(32*scale),image.height-round(45*scale)),(('Тест деформаций. Не утверждённая модель. Без речи.' if deformation_test else 'Технический переступ, не готовая походка. Без речи.') if rig_test else 'Не утверждённая модель. Без речи и походки.'),font=font(15),fill='#4c6457')
    image.save(path)
    image.close()


def run(job, output, first, end):
    import bpy
    started=time.perf_counter()
    p, a, s = [load_json(Path(job)/f'{name}.json') for name in ('project','package','shot')]
    validate_bundle(p,a,s)
    if not s['frame_range'][0] <= first < end <= s['frame_range'][1]:
        raise ValueError('chunk outside shot')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects=append_package(bpy,a)
    bindings=bind(objects,a)
    scene=stage(bpy,p)
    scene.frame_start,scene.frame_end=s['frame_range'][0],s['frame_range'][1]-1
    # Preserve all curves in the optional exported scene, not only this chunk.
    for track in s['tracks']:
        typ,target=bindings[track['control']]
        path={'SHAPE_KEY':'value','OBJECT_LOCATION':'location','OBJECT_ROTATION':'rotation_euler','POSE_ROTATION':'rotation_euler'}[typ]
        for key in track['keys']:
            apply(bindings,{track['control']:key['value']})
            target.keyframe_insert(data_path=path,frame=key['frame'])
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    output=Path(output);frames=output/'frames';frames.mkdir(parents=True,exist_ok=True)
    scene.frame_set(first);apply(bindings,evaluate(s,first));bpy.context.view_layer.update()
    if first==s['frame_range'][0]:
        bpy.ops.wm.save_as_mainfile(filepath=str((output/'preview-scene.blend').resolve()),check_existing=False)
    measurements=[]
    for frame in range(first,end):
        scene.frame_set(frame);apply(bindings,evaluate(s,frame));bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        residuals=[]
        for check in a['ik_checks']:
            rig=objects[check['armature']].evaluated_get(deps)
            endpoint=rig.matrix_world@rig.pose.bones[check['bone']].tail
            residuals.append((endpoint-objects[check['target']].matrix_world.translation).length)
        if max(residuals) > .005:
            raise ContractError('IK target unreachable or solver residual >0.005 m')
        skins={}
        for obj in objects.values():
            if obj.type=='MESH' and any(m.type=='ARMATURE' for m in obj.modifiers):
                evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
                skins[obj.name]=list(evaluated.matrix_world@mesh.vertices[-1].co)
                evaluated.to_mesh_clear()
        from .geometry_probes import measure
        geometry=measure(objects,a,deps)
        path=frames/f'{frame-s["frame_range"][0]:06d}.png'
        scene.render.filepath=str(path.resolve());bpy.ops.render.render(write_still=True)
        raw=file_hash(path);overlay(path,bool(a.get('contact_probes')),a['revision'],'extreme' in s['shot_id'])
        measurements.append({'frame':frame,'max_ik_error_m':max(residuals),'skin_vertices_m':skins,
                             'raw_png_sha256':raw,'controls':evaluate(s,frame),**geometry})
        print(f'PACKAGE_FRAME {frame}',flush=True)
    ocio=Path(importlib.metadata.distribution('bpy').locate_file('bpy'))/'4.5/datafiles/colormanagement/config.ocio'
    write_json(output/'worker-report.json',{'status':'complete','frame_range':[first,end],
        'asset_id':a['asset_id'],'asset_revision':a['revision'],'package_blend_sha256':a['blend']['sha256'],
        'art_status':a['art_status'],'imported_objects':sorted(objects),'blender':bpy.app.version_string,
        'blender_build_hash':bpy.app.build_hash.decode(),'color_management':{'view_transform':'AgX','look':scene.view_settings.look,'exposure':scene.view_settings.exposure,'ocio_sha256':file_hash(ocio)},
        'effective_threads':scene.render.threads,'peak_worker_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'wall_seconds':round(time.perf_counter()-started,4),'measurements':measurements})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--first',type=int,required=True);parser.add_argument('--end',type=int,required=True)
    args=parser.parse_args();run(args.job,args.output,args.first,args.end)
