#!/usr/bin/env python3
"""Bounded native still review; clean frames, no image-generation substitution."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.pipeline.contracts import file_hash,load_json,safe_path
from studio.pipeline.packages import validate_bundle,append_package,bind,apply
from studio.pipeline.resources import run_guarded
from studio.pipeline.render_package import worker_env
from studio.pipeline.run_probe import write_json,runtime_identity

VIEWS=('hero','front','hand_open','hand_curl','full')


def project(size,samples):
    p=load_json(ROOT/'studio/production/dad-refined/project.json')
    p['project_id']='dad-r4-still-review';p['resolution']=[size,size]
    p['render'].update(samples=samples,seed=107,threads=2)
    p['resources'].update(rss_limit_mb=2048,timeout_seconds=300)
    return p


def worker(package_path,output,view,size,samples):
    import bpy
    from mathutils import Vector
    from studio.pipeline.backends.package_worker import stage
    p=project(size,samples);a=load_json(package_path)
    s={'schema_version':2,'kind':'shot','shot_id':'lookdev-static-review','project_id':p['project_id'],
       'asset_id':a['asset_id'],'asset_revision':a['revision'],'frame_range':[0,2],
       'tracks':[{'control':'head.rotation','keys':[{'frame':0,'value':[0,0,0]},{'frame':1,'value':[0,0,0]}]}]}
    validate_bundle(p,a,s)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects=append_package(bpy,a);bindings=bind(objects,a)
    scene=stage(bpy,p);camera=scene.camera;camera.data.type='PERSP';camera.data.lens=90
    if view=='hero':position=(1.10,3.20,2.65);target=(0,.02,2.14)
    elif view=='front':position=(0,3.25,2.46);target=(0,.02,2.16);camera.data.lens=95
    elif view in ('hand_open','hand_curl'):
        position=(1.04,.84,1.20);target=(.75,.02,1.035);camera.data.lens=80
        values={'wrist.R.rotation':[.10,.15,0]}
        for n,factor in [('index',.7),('middle',1),('ring',1.2),('pinky',1.5),('thumb',.6)]:
            angles=(.6,.8,.5) if view=='hand_curl' else tuple(v*factor for v in (.10,.10,.06))
            for j,v in enumerate(angles,1):values[f'finger.R.{n}.{j:02d}']=[v,0,0]
        apply(bindings,values)
    else:
        position=(2.6,7,2.7);target=(0,0,1.33);camera.data.type='ORTHO';camera.data.ortho_scale=3.55
    camera.location=position;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.view_settings.exposure=-.25
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.10,.135,.19,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.28
    floor=bpy.data.materials['STUDIO_Matte'].node_tree.nodes['Principled BSDF']
    floor.inputs['Base Color'].default_value=(.065,.085,.115,1);floor.inputs['Roughness'].default_value=.76
    # A real curved cyclorama avoids the floor/world horizon behind the head.
    bpy.data.objects.remove(bpy.data.objects['STUDIO_Floor'],do_unlink=True)
    import math
    section=[(12,0),(-1.5,0)]+[(-1.5-2*math.sin(i*math.pi/64),2-2*math.cos(i*math.pi/64)) for i in range(1,33)]+[(-3.5,8)]
    vertices=[(x,y,z) for x in (-12,12) for y,z in section];n=len(section)
    data=bpy.data.meshes.new('ReviewCyclorama');data.from_pydata(vertices,[],[(i,i+1,n+i+1,n+i) for i in range(n-1)])
    backdrop=bpy.data.objects.new('ReviewCyclorama',data);scene.collection.objects.link(backdrop)
    data.materials.append(bpy.data.materials['STUDIO_Matte'])
    for poly in data.polygons:poly.use_smooth=True
    if view!='full':backdrop.hide_render=True
    lighting=[('Key',(-3,4.5,5),720,3.5,(1,.86,.73)),('Fill',(4,3,3.2),230,3,(.67,.79,1)),('Rim',(-1,-3,4),850,2.5,(.77,.86,1))]
    for name,position,energy,light_size,color in lighting:
        obj=bpy.data.objects['STUDIO_'+name];obj.location=position;obj.data.energy=energy;obj.data.size=light_size;obj.data.color=color
        obj.rotation_euler=(Vector((0,0,1.9))-obj.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.view_layer.update()
    output.mkdir(exist_ok=True,parents=True);image=output/f'{view}.png'
    scene.render.filepath=str(image.resolve());bpy.ops.render.render(write_still=True)
    write_json(output/f'{view}.json',{'view':view,'revision':a['revision'],'blend_sha256':a['blend']['sha256'],
        'render_script_sha256':file_hash(__file__),'png_sha256':file_hash(image),'dimensions':[size,size],
        'samples':samples,'threads':scene.render.threads,'camera':{'position':list(camera.location),'target':list(target),'type':camera.data.type,'lens_mm':camera.data.lens},
        'lighting':lighting,'blender_version':bpy.app.version_string,'color_management':{'view':'AgX','look':scene.view_settings.look,'exposure':scene.view_settings.exposure},
        'scope':'native static lookdev; no artistic/anatomical approval or full face rig claim'})


def run(args):
    out=safe_path(ROOT,args.output);out.mkdir(parents=True,exist_ok=True)
    native=safe_path(ROOT,args.native_dir);package_path=safe_path(ROOT,args.package)
    reports=[]
    for view in args.views:
        command=[sys.executable,__file__,'--worker','--package',package_path.relative_to(ROOT).as_posix(),'--output',out.relative_to(ROOT).as_posix(),'--views',view,'--size',str(args.size),'--samples',str(args.samples)]
        result=run_guarded(command,out/f'{view}.log',cwd=ROOT,env=worker_env(native,2),rss_limit_mb=2048,timeout_seconds=300)
        image=out/f'{view}.png'
        from PIL import Image
        with Image.open(image) as png:
            png.load()
            if png.size!=(args.size,args.size):raise ValueError('native still dimensions mismatch')
        report=load_json(out/f'{view}.json');report['process']=result.to_dict();reports.append(report)
        print('LOOKDEV_STILL_COMPLETE',view,image,flush=True)
    report={'scope':'native stills, not approval','asset':load_json(package_path)['blend'],'runtime':runtime_identity(native),'renders':reports}
    write_json(out/'render-report.json',report)
    if args.record:write_json(safe_path(ROOT,args.record),report)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--worker',action='store_true')
    parser.add_argument('--package',default='studio/out/dad-lookdev-r4/package.json');parser.add_argument('--native-dir',default='.cache/blender-native')
    parser.add_argument('--output',default='studio/out/dad-r4-review');parser.add_argument('--views',nargs='+',choices=VIEWS,default=list(VIEWS))
    parser.add_argument('--size',type=int,default=1024);parser.add_argument('--samples',type=int,default=64);parser.add_argument('--record')
    args=parser.parse_args()
    if args.size<128 or args.size>1536 or args.size%2 or not 1<=args.samples<=128:parser.error('size must be even 128..1536 and samples 1..128')
    if args.worker:worker(safe_path(ROOT,args.package),safe_path(ROOT,args.output),args.views[0],args.size,args.samples)
    else:run(args)
