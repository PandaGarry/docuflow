#!/usr/bin/env python3
"""Reject/review existing A7 form, not create A8 or claim a new likeness result.

Actual official Rain and exact reconstructed A7: matched neutral/clay views,
no hair hiding the skull/face and no complexion/skin shaders hiding the planes.
Export indexed head topology/weights/evaluated neutral coordinates for deliberate
region/landmark editing, instead of guessing global Gaussian centers from pixels.
Private photographs/screenshots are never read or packed.
"""
from __future__ import annotations
import hashlib
import gzip
import json
from pathlib import Path
import numpy as np
import rain_mom_pass_a7 as a7

base=a7.base
study=a7.study
ROOT=study.ROOT
OUT=ROOT/'studio/reviews/mom-form-audit'
VISIBLE={'GEO-rain-head','GEO-rain-eyes','GEO-rain-eye_cornea','GEO-rain-eye_dots',
         'GEO-rain-eyebrows','GEO-rain-eyelashes','GEO-rain-gums_lower',
         'GEO-rain-gums_upper','GEO-rain-tongue'}


def flat_material(bpy,name,color):
    m=bpy.data.materials.new(name);m.use_nodes=True
    node=m.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value=(*color,1)
    node.inputs['Roughness'].default_value=.68
    node.inputs['Specular IOR Level'].default_value=.25
    return m


def diagnostic_stage(bpy):
    scene,camera=study.stage(bpy)
    for obj in bpy.data.objects:
        if obj.type=='LIGHT':obj.data.color=(1,1,1)
        if obj.type=='MESH' and obj.name not in VISIBLE:obj.hide_render=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.12,.12,.12,1)
    skin=flat_material(bpy,'Audit neutral skin',(.45,.45,.45))
    brow=flat_material(bpy,'Audit brow',(.085,.085,.085))
    lash=flat_material(bpy,'Audit lashes',(.035,.035,.035))
    for name,material in [('GEO-rain-head',skin),('GEO-rain-eyebrows',brow),('GEO-rain-eyelashes',lash)]:
        mesh=bpy.data.objects[name].data
        for i in range(len(mesh.materials)):mesh.materials[i]=material
    # Identical grayscale filter on original eye material, preserving iris/sclera.
    tree=bpy.data.materials['MAT-rain.eyes'].node_tree
    socket=tree.nodes['Principled BSDF'].inputs['Base Color']
    source=socket.links[0].from_socket
    hsv=tree.nodes.new('ShaderNodeHueSaturation');hsv.inputs['Saturation'].default_value=0
    tree.links.new(source,hsv.inputs['Color']);tree.links.new(hsv.outputs['Color'],socket)
    return scene,camera


def head_data(bpy):
    obj=bpy.data.objects['GEO-rain-head'];mesh=obj.data
    positions=base.transform_points(base.point_array(mesh.vertices),obj.matrix_world)
    subs=[(m,m.show_viewport) for m in obj.modifiers if m.type=='SUBSURF']
    for m,_ in subs:m.show_viewport=False
    bpy.context.view_layer.update()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());temporary=evaluated.to_mesh()
    try:
        neutral=base.transform_points(base.point_array(temporary.vertices),evaluated.matrix_world)
        if len(neutral)!=len(positions):raise ValueError('Cannot silently call noncorresponding topology indexed')
    finally:
        evaluated.to_mesh_clear()
        for m,visible in subs:m.show_viewport=visible
        bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain']
    relevant=set(g.name for g in obj.vertex_groups)
    return {'space':'World meters, Blender Z-up facing -Y. Original vertex indices, un-subdivided head topology.',
            'basis_vertices':positions.round(7).tolist(),'neutral_evaluated_vertices_without_subdivision':neutral.round(7).tolist(),
            'polygons':[list(p.vertices) for p in mesh.polygons],
            'vertex_group_names':[g.name for g in obj.vertex_groups],
            'vertex_weights':[[[g.group,round(g.weight,7)] for g in v.groups] for v in mesh.vertices],
            'shape_keys':[k.name for k in mesh.shape_keys.key_blocks],
            'related_rest_bones':[{'name':b.name,'head':list(b.head_local),'tail':list(b.tail_local),'parent':b.parent.name if b.parent else None} for b in rig.data.bones if b.name in relevant],
            'basis_coordinate_sha256':hashlib.sha256(positions.tobytes()).hexdigest(),
            'note':'These are the existing source/current forms, NOT a fitted target. Shape-key migration and rig-rest redesign must be evaluated for a future primary-form revision.'}


def reconstruct_a7(bpy):
    rig=bpy.data.objects['RIG-rain']
    base.change_meshes(bpy);base.change_materials(bpy)
    a7.face.change_face(bpy);a7.face.complexion(bpy);a7.prior.refine_nasal_base(bpy)
    a7.refine_face(bpy);a7.refine_groom(bpy,rig)
    bpy.context.view_layer.update()


def main():
    import bpy
    OUT.mkdir(parents=True,exist_ok=True)
    historical=json.loads((ROOT/'studio/reviews/rain-mom-a7/report.json').read_text())
    for name,digest in historical['scripts'].items():
        if study.sha(ROOT/'studio/tools'/name)!=digest:
            raise ValueError(f'A7 recipe changed: {name}; audit must not mislabel a reconstruction')
    source=study.acquire(ROOT/'.cache/rain-v3')
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    geometry={};images=[];checks={}
    for label in ('official-source','existing-a7'):
        bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False);bpy.context.view_layer.update()
        source_rest=base.rig_signature(bpy.data.objects['RIG-rain'])
        if label=='existing-a7':reconstruct_a7(bpy)
        geometry[label]=head_data(bpy)
        checks[label]={'rest_bone_signature':base.rig_signature(bpy.data.objects['RIG-rain']),
                       'source_rest_bone_signature':source_rest,'invalid_drivers':base.invalid_drivers(bpy)}
        scene,camera=diagnostic_stage(bpy)
        for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:
            images.append(study.render(bpy,scene,camera,OUT/f'{label}-clay-{view}.png',position,(0,0,1.47),.48))
    geometry.update({'license':'CC-BY-4.0','credit':'Rain Rig (CC) Blender Foundation | studio.blender.org',
                     'source_blend_sha256':study.sha(source),'scope':'Existing topology/neutral data for manual primary-form planning, no private photo-derived scan.'})
    (OUT/'head-edit-data.json.gz').write_bytes(gzip.compress(json.dumps(geometry,separators=(',',':')).encode(),mtime=0))
    report={'status':'rejected_requires_major_rework','new_design_created':False,
            'source_url':study.URL,'source_blend_sha256':study.sha(source),'archive_sha256':study.ARCHIVE_SHA,
            'script_sha256':study.sha(__file__),'historical_a7_recipe_scripts':historical['scripts'],
            'blender_version':bpy.app.version_string,'embedded_python_executed':False,
            'stage':'Same camera/geometry pose per view, neutral white lights, neutral skin/brows/lashes, eye color desaturated. All hair/body/wardrobe hidden, not deleted.',
            'checks':checks,'images':images,'geometry_file_sha256':study.sha(OUT/'head-edit-data.json.gz'),
            'art_approved':False,'production_swap_allowed':False,
            'scope':'Actual diagnostic renders of UNCHANGED source and A7. Not a new character result, not acceptance, not proof that the rig is fully functional.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0 https://creativecommons.org/licenses/by/4.0/'}
    study.write(OUT/'native-audit.json',report)
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(1536,3*768+85),'#1c2530');draw=ImageDraw.Draw(canvas)
    draw.text((20,15),'SOURCE CLAY',fill='white',font_size=26)
    draw.text((788,15),'EXISTING A7 CLAY - REJECTED',fill='white',font_size=26)
    for row,view in enumerate(('front','three-quarter','profile')):
        for col,label in enumerate(('official-source','existing-a7')):
            with Image.open(OUT/f'{label}-clay-{view}.png') as im:canvas.paste(im,(col*768,55+row*768))
    draw.text((20,3*768+60),'Diagnostic ONLY: no new design. Rain Rig (CC) Blender Foundation | studio.blender.org',fill='white',font_size=20)
    canvas.save(OUT/'native-clay-audit.png')


if __name__=='__main__':
    main()
