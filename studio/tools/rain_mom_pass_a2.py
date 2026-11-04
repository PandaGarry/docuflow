#!/usr/bin/env python3
"""A2: same conservative A1 geometry, darker brows, calibrated native controls.

A1 and its failed smile receipt remain intact. Original Rain drivers are never
muted or replaced. Neutral before/after and source/candidate expressions are
native renders with identical cameras and lights, not generated illustrations.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

import rain_mom_pass as base

study = base.study
ROOT = study.ROOT
OUT = ROOT/'studio/reviews/rain-mom-a2'


def solve_control(evaluate, target):
    """Find a small input for a monotone native response, including clamps.

    Return closest attainable response honestly. Search resolution is NOT a
    deformation/acceptance threshold; this only positions an existing control.
    """
    trials = []
    for value in (-.05, 0.0, .05):
        trials.append((value, float(evaluate(value))))
    for (left, left_response), (right, right_response) in zip(trials[:2], trials[1:3]):
        if left_response == right_response or not min(left_response,right_response) <= target <= max(left_response,right_response):
            continue
        increasing = right_response > left_response
        for _ in range(22):
            middle = (left+right)/2
            response = float(evaluate(middle))
            trials.append((middle,response))
            if (response < target) == increasing:
                left = middle
            else:
                right = middle
    best = min(trials,key=lambda t:(abs(t[1]-target),abs(t[0])))
    return {'input': best[0], 'response': best[1], 'trials': trials}


def set_key_via_actuator(bpy,rig,key_name,target,prefix):
    keys = bpy.data.objects['GEO-rain-head'].data.shape_keys
    curve = next(f for f in keys.animation_data.drivers if f.data_path == f'key_blocks["{key_name}"].value')
    options=[]
    for var in curve.driver.variables:
        for t in var.targets:
            if t.id == rig and t.bone_target.startswith(prefix) and t.transform_type.startswith('LOC_'):
                option=(t.bone_target,'XYZ'.index(t.transform_type[-1]))
                if option not in options:
                    options.append(option)
    if not options:
        raise ValueError(f'{key_name}: no supported native ACT control')
    solutions=[]
    for name,axis in options:
        bone=rig.pose.bones[name]
        original=bone.location.copy()
        def evaluate(value):
            bone.location=original
            bone.location[axis]=value
            rig.update_tag(); bpy.context.view_layer.update()
            return keys.key_blocks[key_name].value
        result=solve_control(evaluate,target)
        result.update({'bone':name,'axis':axis})
        solutions.append(result)
        bone.location=original
        rig.update_tag(); bpy.context.view_layer.update()
    best=min(solutions,key=lambda s:(abs(s['response']-target),abs(s['input'])))
    rig.pose.bones[best['bone']].location[best['axis']]=best['input']
    rig.update_tag(); bpy.context.view_layer.update()
    actual=float(keys.key_blocks[key_name].value)
    return {'key':key_name,'target':target,'actual':actual,
            'status':'actuated' if abs(actual-target)<1e-4 else 'blocked-partial-actuation',
            'bone':best['bone'],'axis':best['axis'],'input':best['input'],
            'expression':curve.driver.expression,'solutions':solutions}


def restore(bpy,rig,matrices):
    for name,matrix in matrices.items():
        rig.pose.bones[name].matrix_basis=matrix
    rig.update_tag(); bpy.context.view_layer.update()


def expression_images(bpy,rig,matrices,scene,camera,prefix):
    neutral=base.head_geometry(bpy)
    images=[];expressions=[]
    for label,key_names,target,bone_prefix in [('blink',('EyelidsClose.L','EyelidsClose.R'),.99999,'ACT-Eyelid'),
                                                ('smile',('Smile.L','Smile.R'),.5,'ACT-Lips')]:
        restore(bpy,rig,matrices)
        controls=[set_key_via_actuator(bpy,rig,k,target,bone_prefix) for k in key_names]
        posed=base.head_geometry(bpy)
        expressions.append({'expression':label,'controls':controls,'finite_vertices':bool(np.isfinite(posed).all()),
                            'maximum_head_displacement_m':float(np.linalg.norm(posed-neutral,axis=1).max())})
        images.append(study.render(bpy,scene,camera,OUT/f'{prefix}-{label}.png',(0,-4,1.5),(0,0,1.45),.60))
    restore(bpy,rig,matrices)
    return images,expressions


def board():
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(1536,1640),'#1c2530');draw=ImageDraw.Draw(canvas)
    for col,label in enumerate(('ORIGINAL RAIN v3','MOM STUDY A2 - NOT APPROVED')):
        draw.text((col*768+24,12),label,fill='white',font_size=24)
    for row,view in enumerate(('full','face')):
        for col,directory in enumerate((ROOT/'studio/reviews/rain-study',OUT)):
            filename=f'source-{view}.png' if col==0 else f'candidate-{view}.png'
            with Image.open(directory/filename) as image:
                canvas.paste(image,(col*768,48+row*768))
    draw.text((24,1596),'Same native camera/light. Stock clothes + hair retained. Rain Rig (CC) Blender Foundation | studio.blender.org',fill='white',font_size=18)
    canvas.save(OUT/'comparison.png')


def main():
    import bpy
    OUT.mkdir(parents=True,exist_ok=True)
    source=study.acquire(ROOT/'.cache/rain-v3')
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False)
    bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain']
    signature=base.rig_signature(rig)
    matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones}
    topology={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'}
    source_invalid=base.invalid_drivers(bpy)
    scene,camera=study.stage(bpy)
    source_images,source_expressions=expression_images(bpy,rig,matrices,scene,camera,'source')
    meshes=base.change_meshes(bpy)
    materials=base.change_materials(bpy)
    bpy.data.materials['MAT-rain.eyebrows'].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=base.linear_color('#6B4F38')
    materials[-1]['base_color_srgb']='#6B4F38'
    neutral=base.head_geometry(bpy)
    images=[study.render(bpy,scene,camera,OUT/'candidate-full.png',(0,-4,1.05),(0,0,.85),1.95),
            study.render(bpy,scene,camera,OUT/'candidate-face.png',(0,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-three-quarter.png',(2.2,-4,1.5),(0,0,1.45),.60)]
    candidate_images,expressions=expression_images(bpy,rig,matrices,scene,camera,'candidate')
    candidate_invalid=base.invalid_drivers(bpy)
    receipt={'revision':'rain-mom-a2','source_blend_sha256':study.sha(source),
             'source_url':study.URL,'archive_sha256':study.ARCHIVE_SHA,
             'source_original_images':'studio/reviews/rain-study',
             'source_scripts_executed':False,'blender_version':bpy.app.version_string,
             'scripts':{p.name:study.sha(p) for p in (ROOT/'studio/tools/rain_mom_pass_a2.py',ROOT/'studio/tools/rain_mom_pass.py',ROOT/'studio/tools/rain_study.py')},
             'reference_sha256':study.sha(ROOT/'studio/characters/mom/master/turnaround.png'),
             'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org',
             'license':'CC-BY-4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
             'change_notice':'A1 skin, soft waist/cheek/chin/nose proportions and thinner brows; A2 darker brown brows and properly calibrated native expression tests. Stock wardrobe and haircut retained.',
             'meshes':meshes,'materials':materials,'images':images+source_images+candidate_images,
             'source_expressions':source_expressions,'candidate_expressions':expressions,
             'source_invalid_drivers':source_invalid,'candidate_invalid_drivers':candidate_invalid,
             'new_invalid_drivers':sorted(set(candidate_invalid)-set(source_invalid)),
             'rig_rest_signature_before':signature,'rig_rest_signature_after':base.rig_signature(rig),
             'topology_unchanged':topology=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'},
             'pose_restored_max_head_error_m':float(np.linalg.norm(base.head_geometry(bpy)-neutral,axis=1).max()),
             'art_approved':False,'production_swap_allowed':False,
             'scope':'Paired native neutral/expression diagnostics only. Not a full rig/body-animation, anatomical, speech or likeness acceptance.'}
    if not receipt['topology_unchanged'] or receipt['rig_rest_signature_after']!=signature:
        raise ValueError('Unexpected topology/rest rig modification')
    if not all(e['finite_vertices'] for e in expressions+source_expressions):
        raise ValueError('Nonfinite native head geometry')
    text=bpy.data.texts.new('DOCUFLOW_A2_CHANGES.txt')
    text.write(receipt['credit']+'\nCC BY 4.0 '+receipt['license_url']+'\n'+receipt['change_notice']+'\nExperimental. Asset scripts were NOT executed.\n')
    bpy.ops.file.pack_all()
    native=ROOT/'.cache/rain-v3/rain-mom-a2.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()),compress=True)
    receipt['native_artifact']={'filename':native.name,'sha256':study.sha(native),'textures_packed':True,'storage':'GitHub Actions artifact (14 days), reconstructable from scripts.'}
    study.write(OUT/'report.json',receipt)
    board()


if __name__=='__main__':
    main()
