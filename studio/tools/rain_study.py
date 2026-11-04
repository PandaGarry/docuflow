#!/usr/bin/env python3
"""Bounded Rain v3 acquisition / native inspection. No procedural substitute.

The official asset is CC-BY 4.0 Blender Foundation. Embedded Python is disabled.
Native outputs are diagnostics, not likeness, art or working-rig approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[2]
URL='https://studio.blender.org/download-source/files/ee/a7/eea73e55dba1cea31c09848df6a794b2-4.zip'
ARCHIVE_SHA='80217f163f6392dc829233d63c2cfb5e1376775bc34101ad14f39631fea70d24'
BLEND_SHA='831ab6d837c679040285862b15dc9ee5180b018442a88aeaf92aaa7509b80258'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def acquire(directory):
    directory.mkdir(parents=True,exist_ok=True);archive=directory/'rain-v3.zip'
    if not archive.exists():
        request=urllib.request.Request(URL,headers={'User-Agent':'Docuflow-Rain-study/1.0'})
        with urllib.request.urlopen(request,timeout=60) as response,archive.open('wb') as out:
            total=0
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>100*1024*1024:raise ValueError('archive exceeds bounded acquisition size')
                out.write(chunk)
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('official archive changed; manual provenance review required')
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist())>500*1024*1024:raise ValueError('unpacked source too large')
        for item in z.infolist():
            target=(directory/'source'/item.filename).resolve()
            if not target.is_relative_to((directory/'source').resolve()):raise ValueError('unsafe archive path')
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('archive symlink rejected')
        z.extractall(directory/'source')
    found=[p for p in (directory/'source').rglob('*.blend') if sha(p)==BLEND_SHA]
    if len(found)!=1:raise ValueError('expected exact source Rain blend not found')
    return found[0]


def inspect(bpy):
    meshes=[]
    for o in bpy.data.objects:
        if o.type!='MESH':continue
        meshes.append({'name':o.name,'vertices':len(o.data.vertices),'materials':[m.name if m else None for m in o.data.materials],
                       'shape_keys':[k.name for k in o.data.shape_keys.key_blocks] if o.data.shape_keys else [],
                       'modifiers':[{'name':m.name,'type':m.type,'render':m.show_render} for m in o.modifiers],
                       'hidden_render':o.hide_render})
    rigs=[{'name':o.name,'bones':len(o.data.bones),'pose_controls':[{'name':b.name,'location':list(b.location),'properties':{k:str(v)[:150] for k,v in b.items() if k!='_RNA_UI'}} for b in o.pose.bones]} for o in bpy.data.objects if o.type=='ARMATURE']
    materials=[]
    for m in bpy.data.materials:
        materials.append({'name':m.name,'nodes':[{'name':n.name,'type':n.type,'image':n.image.name if n.type=='TEX_IMAGE' and n.image else None,
            'inputs':{s.name:list(s.default_value) if hasattr(s.default_value,'__len__') else s.default_value for s in n.inputs if hasattr(s,'default_value') and s.type in ('VALUE','RGBA')}} for n in m.node_tree.nodes] if m.use_nodes else []})
    return {'meshes':meshes,'rigs':rigs,'materials':materials,
            'embedded_scripts':[{'name':t.name,'sha256':hashlib.sha256(t.as_string().encode()).hexdigest(),'characters':len(t.as_string())} for t in bpy.data.texts],
            'invalid_drivers':[{'object':o.name,'path':f.data_path,'expression':f.driver.expression} for o in bpy.data.objects if o.animation_data for f in o.animation_data.drivers if not f.driver.is_valid]}


def stage(bpy):
    from mathutils import Vector
    scene=bpy.context.scene
    for o in list(bpy.data.objects):
        if o.type in ('CAMERA','LIGHT'):bpy.data.objects.remove(o,do_unlink=True)
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.threads_mode='FIXED';scene.render.threads=2
    scene.render.resolution_x=768;scene.render.resolution_y=768;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.render.film_transparent=False;scene.render.use_border=False;scene.render.use_compositing=False;scene.render.use_sequencer=False
    scene.render.use_simplify=True;scene.render.simplify_subdivision=2;scene.render.simplify_subdivision_render=2
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0
    world=bpy.data.worlds.new('StudyWorld');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.10,.13,.17,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.3;scene.world=world
    data=bpy.data.cameras.new('StudyCamera');camera=bpy.data.objects.new('StudyCamera',data);scene.collection.objects.link(camera);scene.camera=camera
    for name,power,size,position,color in [('Key',450,3,(-3,-4,4),(1,.88,.78)),('Fill',180,3,(3,-2,2),(.75,.85,1)),('Rim',500,2,(0,3,3),(1,1,1))]:
        data=bpy.data.lights.new('Study'+name,'AREA');data.energy=power;data.shape='DISK';data.size=size;data.color=color
        o=bpy.data.objects.new('Study'+name,data);scene.collection.objects.link(o);o.location=position
        o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
    return scene,camera


def render(bpy,scene,camera,path,position,target,scale):
    from mathutils import Vector
    camera.data.type='ORTHO';camera.data.ortho_scale=scale
    camera.location=position;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(path.resolve());bpy.ops.render.render(write_still=True)
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'camera':{'position':position,'target':target,'ortho_scale':scale},'dimensions':[768,768],'samples':24}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='studio/reviews/rain-study');parser.add_argument('--source-dir',default='.cache/rain-v3');parser.add_argument('--stage',choices=['inspect'],default='inspect');args=parser.parse_args()
    import bpy
    output=ROOT/args.output;output.mkdir(parents=True,exist_ok=True)
    source=acquire(ROOT/args.source_dir)
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False)
    bpy.context.view_layer.update()
    receipt={'source':{'url':URL,'archive_sha256':ARCHIVE_SHA,'blend_sha256':sha(source),'license':'CC-BY-4.0','credit':'Rain Rig (CC) Blender Foundation | studio.blender.org',
                       'hash_witness':'https://github.com/TheDudeCommits/CodexOfWar/blob/main/ArtSource/P10/Round003/README.md'},
             'embedded_python_executed':False,'blender_version':bpy.app.version_string,'inspection':inspect(bpy),
             'scope':'Native original Rain inspection, no adaptation or rig/likeness approval yet','script_sha256':sha(__file__)}
    write(output/'inspection.json',receipt)
    scene,camera=stage(bpy)
    # Rain is Blender Z-up, facing -Y. Framing is explicit, never a substitute asset.
    images=[render(bpy,scene,camera,output/'source-full.png',(0,-4,1.05),(0,0,.85),1.95),
            render(bpy,scene,camera,output/'source-face.png',(0,-4,1.5),(0,0,1.45),.60)]
    write(output/'render-report.json',{'stage':args.stage,'source_blend_sha256':sha(source),'script_sha256':sha(__file__),'images':images,'source_scripts_disabled':True,'art_approved':False})


if __name__=='__main__':main()
