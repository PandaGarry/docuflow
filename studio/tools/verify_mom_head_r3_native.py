#!/usr/bin/env python3
"""Reopen the actual downloaded R3 .blend artifact; not an art acceptance test."""
from pathlib import Path
import gzip
import json
import numpy as np
from PIL import Image
import mom_head_form_r3 as build

ROOT=build.ROOT
OUT=ROOT/'studio/reviews/mom-head-form-r3/reopen'


def main():
    import bpy
    report=json.loads((ROOT/'studio/reviews/mom-head-form-r3/report.json').read_text())
    files=list((ROOT/'.cache/head-r3-artifact').rglob('mom-head-form-r3.blend'))
    if len(files)!=1:raise ValueError('Expected one actual downloaded R3 blend')
    native=files[0]
    if build.study.sha(native)!=report['native_artifact']['sha256']:raise ValueError('Downloaded blend hash differs from saved artifact')
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.open_mainfile(filepath=str(native.resolve()),use_scripts=False);bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain']
    if build.base.rig_signature(rig)!=report['candidate_rest_signature']:raise ValueError('Saved rig rest changed')
    data=build.diagnostic.head_data(bpy)
    expected=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r3/head-edit-data.json.gz').read_bytes()))
    for key in ('polygons','vertex_weights','shape_keys'):
        if data[key]!=expected[key]:raise ValueError(f'Saved mesh mismatch: {key}')
    basis_error=float(np.abs(np.array(data['basis_vertices'])-expected['basis_vertices']).max())
    neutral_error=float(np.abs(np.array(data['neutral_evaluated_vertices_without_subdivision'])-expected['neutral_evaluated_vertices_without_subdivision']).max())
    if max(basis_error,neutral_error)>2e-6:raise ValueError('Saved neutral geometry does not match built geometry')
    images=[]
    for image in bpy.data.images:
        if image.source in ('FILE','TILED') and image.type=='IMAGE':
            packed=bool(image.packed_file) or bool(image.packed_files)
            images.append({'name':image.name,'packed':packed})
    if not images or not all(i['packed'] for i in images):raise ValueError('Texture dependencies not fully packed')
    OUT.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    render=build.study.render(bpy,scene,scene.camera,OUT/'reopened-front.png',(0,-4,1.5),(0,0,1.47),.48)
    with Image.open(ROOT/'studio/reviews/mom-head-form-r3/candidate-front.png') as im:a=np.asarray(im.convert('RGB'),dtype=float)
    with Image.open(OUT/'reopened-front.png') as im:b=np.asarray(im.convert('RGB'),dtype=float)
    difference=np.abs(a-b);mae=float(difference.mean());p99=float(np.percentile(difference,99))
    if mae>.5 or p99>4:raise ValueError(f'Reopened render differs unexpectedly: MAE {mae}, p99 {p99}')
    import mom_smile_pose_r3 as smile_pose
    import rain_mom_pass_a2 as controls
    matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones}
    baseline=build.base.head_geometry(bpy)
    warm=smile_pose.set_warm_smile(bpy,rig)
    warm_render=build.study.render(bpy,scene,scene.camera,OUT/'warm-smile.png',(0,-4,1.5),(0,0,1.47),.48)
    controls.restore(bpy,rig,matrices)
    restore_error=float(np.linalg.norm(build.base.head_geometry(bpy)-baseline,axis=1).max())
    if restore_error>1e-7:raise ValueError('Warm pose did not restore neutral geometry')
    # Capture actual graph rather than guessing whether ACT-only lid controls
    # also move the lash skeleton. No new eyelid pose or bone edit is applied.
    eyelids=[]
    for side in ('L','R'):
        for prefix in ('ACT-Eyelid_Upper','ACT-Eyelid_Lower','MSTR-Eyering_Upper','MSTR-Eyering_Lower'):
            bone=rig.pose.bones[f'{prefix}.{side}']
            constraints=[]
            for c in bone.constraints:
                item={'name':c.name,'type':c.type,'influence':c.influence}
                for attr in ('subtarget','owner_space','target_space','transform_channel','map_from','map_to','from_min_y','from_max_y','to_min_y','to_max_y','use_offset'):
                    if hasattr(c,attr):item[attr]=getattr(c,attr)
                constraints.append(item)
            eyelids.append({'name':bone.name,'parent':bone.parent.name if bone.parent else None,'constraints':constraints,
                            'location':list(bone.location),'rotation_mode':bone.rotation_mode})
    record={'status':'saved_native_binary_reopened_and_rendered','new_geometry_created':False,'native_blend_sha256':build.study.sha(native),
            'verify_script_sha256':build.study.sha(__file__),'source_report_sha256':build.study.sha(ROOT/'studio/reviews/mom-head-form-r3/report.json'),
            'blender_version':bpy.app.version_string,'embedded_python_executed':False,'basis_max_coordinate_error_m':basis_error,
            'evaluated_neutral_max_coordinate_error_m':neutral_error,'packed_images':images,'render':render,'warm_smile':warm,'warm_smile_render':warm_render,'pose_restore_error_m':restore_error,
            'pose_helper_sha256':build.study.sha(ROOT/'studio/tools/mom_smile_pose_r3.py'),'eyelid_control_graph':eyelids,
            'reopened_vs_original_rgb_mae_255':mae,'reopened_vs_original_rgb_p99_255':p99,
            'pixel_threshold_scope':'Binary persistence/render consistency, not likeness or image beauty. Allow tiny CPU/render variation.',
            'art_approved':False,'user_approved':False,'production_swap_allowed':False,
            'scope':'Reopens real uploaded binary, verifies neutral geometry/keys/weights/rest/packed textures and rerenders neutral. Legacy blink remains visually blocked; balanced smile is a limited pose probe, not full acting acceptance.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0'}
    build.study.write(OUT/'verification.json',record)


if __name__=='__main__':
    main()
