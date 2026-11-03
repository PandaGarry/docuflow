#!/usr/bin/env python3
"""R9: canonical likeness refinement in real nose/lip/cheek volumes and original-UV paint.

Uses official Rain head and its ORIGINAL keys/rig, not accumulated A1-A7 face
fields. A versioned, indexed anatomical cage drives coherent primary volumes.
No personal images read. A neutral head study, not a complete mom/production rig.
"""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import mom_head_cage as model
import mom_face_controls as paired
import mom_face_probe as probe
import mom_smile_pose_r3 as warm_pose
import mom_face_paint_r9 as finish
import mom_head_surface_r2 as surface
import mom_native_form_audit as diagnostic

base=diagnostic.base
study=diagnostic.study
ROOT=study.ROOT
OUT=ROOT/'studio/reviews/mom-head-form-r9'
SPEC=ROOT/'studio/authoring/mom-head-form-r9.json'
AFFECTED=('GEO-rain-head','GEO-rain-eyebrows','GEO-rain-eyelashes',
          'GEO-rain-gums_upper','GEO-rain-gums_lower','GEO-rain-tongue')


def eye_fingerprints(bpy):
    result={}
    for name in ('GEO-rain-eyes','GEO-rain-eye_cornea','GEO-rain-eye_dots'):
        mesh=bpy.data.objects[name].data
        blocks=[k.data for k in mesh.shape_keys.key_blocks] if mesh.shape_keys else [mesh.vertices]
        result[name]=hashlib.sha256(b''.join(base.point_array(block).tobytes() for block in blocks)).hexdigest()
    return result


def apply_head_form(bpy,cage,spec):
    edits=[]
    source_data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
    for name in AFFECTED:
        obj=bpy.data.objects[name];mesh=obj.data;keys=mesh.shape_keys
        blocks=[k.data for k in keys.key_blocks] if keys else [mesh.vertices]
        world=obj.matrix_world.copy();inverse=world.inverted()
        maximum=0;minimum_det=1e10
        for block in blocks:
            original=base.transform_points(base.point_array(block),world)
            changed=cage(original)
            if name=='GEO-rain-head':changed=finish.finish_ears(changed,source_data,spec['ear_finish'])
            if name=='GEO-rain-eyebrows':
                head=bpy.data.objects['GEO-rain-head']
                head_vertices=base.transform_points(base.point_array(head.data.vertices),head.matrix_world)
                changed=surface.author_brows(original,head_vertices,[list(p.vertices) for p in head.data.polygons],spec['brow_curve'])
            if not np.isfinite(changed).all():raise ValueError(f'Nonfinite {name}')
            determinant=np.linalg.det(cage.jacobians(original[::5]))
            minimum_det=min(minimum_det,float(determinant.min()))
            if minimum_det<=0:raise ValueError(f'Sampled cage fold on corrective coordinates: {name}')
            maximum=max(maximum,float(np.linalg.norm(changed-original,axis=1).max()))
            block.foreach_set('co',base.transform_points(changed,inverse).ravel())
        if keys:
            mesh.vertices.foreach_set('co',base.point_array(keys.key_blocks[0].data).ravel());keys.update_tag()
        mesh.update()
        edits.append({'object':name,'vertices':len(mesh.vertices),'transformed_original_key_blocks':len(blocks) if keys else 0,
                      'max_change_m':maximum,'min_sampled_cage_jacobian_det_at_original_key_coordinates':minimum_det})
    bpy.context.view_layer.update()
    return edits


def make_board():
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(1536,2389),'#1c2530');draw=ImageDraw.Draw(canvas)
    draw.text((20,15),'R8 - PREVIOUS VERSION',fill='white',font_size=25)
    draw.text((788,15),'HEAD FORM R9 - WORK IN PROGRESS',fill='white',font_size=25)
    for row,view in enumerate(('front','three-quarter','profile')):
        for column,path in enumerate((ROOT/f'studio/reviews/mom-head-form-r8/clay-{view}.png',OUT/f'clay-{view}.png')):
            with Image.open(path) as image:canvas.paste(image,(column*768,55+row*768))
    draw.text((20,2364),'Actual native geometry / matched clay views. No hair/body approval. Rain Rig (CC) Blender Foundation | studio.blender.org',fill='white',font_size=17)
    canvas.save(OUT/'comparison-clay.png')


def main():
    import bpy
    import rain_mom_pass_a2 as controls
    import rain_mom_pass_a3 as expressions
    OUT.mkdir(parents=True,exist_ok=True)
    spec,vertices,cage=model.load_cage(SPEC)
    determinants=np.linalg.det(cage.jacobians(vertices))
    safety={'controls':len(spec['controls']),'condition_number':cage.condition_number,
            'min_sampled_jacobian_determinant':float(determinants.min()),
            'max_sampled_jacobian_determinant':float(determinants.max()),
            'maximum_basis_change_m':float(np.linalg.norm(cage(vertices)-vertices,axis=1).max()),
            'control_interpolation_error_m':float(np.abs(cage(cage.centers)-cage.centers-cage.displacements).max()),
            'scope':'Sampled mathematical safety only, not continuous invertibility, anatomy, likeness or pose approval.'}
    if determinants.min()<=0 or safety['maximum_basis_change_m']>.04:raise ValueError('Unsafe cage samples')
    source_data=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
    normals=surface.vertex_normals(vertices,source_data['polygons'])
    for control in spec['controls']:
        if control.get('binding_kind')=='verified outward-facing lip surface' and normals[control['source_vertex'],1]>=-.25:
            raise ValueError('Lip control bound to inward/nonexternal surface')
    source=study.acquire(ROOT/'.cache/rain-v3')
    if study.sha(source)!=spec['source_blend_sha256']:raise ValueError('Wrong source blend')
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    source_diagnostics={'historical_report':'studio/reviews/mom-head-form-r3/report.json', 'scope':'Original-source controller ambiguity already reproduced in R3; no new source pose claim.'}
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False);bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain'];rest=base.rig_signature(rig)
    matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones}
    invalid=base.invalid_drivers(bpy)
    topology={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'}
    # Confirm the live source coordinates match the indexed cage source BEFORE editing.
    head=bpy.data.objects['GEO-rain-head']
    current=base.transform_points(base.point_array(head.data.vertices),head.matrix_world)
    if not np.allclose(current,vertices,rtol=0,atol=6e-8):raise ValueError('Source indexed Basis does not match verified data')
    eyes_before=eye_fingerprints(bpy)
    uv_coords=np.empty(len(finish.render_uv(head.data).data)*2,dtype=np.float32)
    finish.render_uv(head.data).data.foreach_get('uv',uv_coords)
    original_uv_sha256=hashlib.sha256(uv_coords.tobytes()).hexdigest()
    edits=apply_head_form(bpy,cage,spec)
    if eyes_before!=eye_fingerprints(bpy):raise ValueError('Unexpected globe/cornea geometry change')
    neutral=base.head_geometry(bpy)
    indexed_neutral=probe.neutral_points(bpy)
    indexed=diagnostic.head_data(bpy)
    indexed.update({'revision':spec['revision'],'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0','source_blend_sha256':study.sha(source)})
    (OUT/'head-edit-data.json.gz').write_bytes(gzip.compress(json.dumps(indexed,separators=(',',':')).encode(),mtime=0))
    scene,camera,visibility=diagnostic.diagnostic_stage(bpy)
    images=[]
    for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:
        images.append(study.render(bpy,scene,camera,OUT/f'clay-{view}.png',position,(0,0,1.47),.48))
    materials=finish.apply_palette(bpy,source_data,spec['palette_srgb'])
    material_state=finish.saved_material_state(bpy)
    if original_uv_sha256!=material_state['original_uv_sha256']:raise ValueError('Original UVs changed')
    for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:
        images.append(study.render(bpy,scene,camera,OUT/f'candidate-{view}.png',position,(0,0,1.47),.48))
    poses=[];sweep=[]
    for amount in (0,.25,.5,.75,1,.75,.5,.25,0):
        controls.restore(bpy,rig,matrices);actuators=expressions.set_blink(bpy,rig,amount)
        points=base.head_geometry(bpy)
        sweep.append({'amplitude':amount,'finite':bool(np.isfinite(points).all()),'max_displacement_m':float(np.linalg.norm(points-neutral,axis=1).max())})
        if len(sweep) in (3,5):
            label='blink-half' if amount==.5 else 'blink'
            images.append(study.render(bpy,scene,camera,OUT/f'candidate-{label}.png',(0,-4,1.5),(0,0,1.47),.48))
            poses.append({'pose':label,'actuators':actuators})
    controls.restore(bpy,rig,matrices)
    actuators=warm_pose.set_warm_smile(bpy,rig,spec['portrait_smile_amount'])
    smile_symmetry=probe.mouth_displacement_symmetry(indexed_neutral,probe.neutral_points(bpy))
    points=base.head_geometry(bpy)
    poses.append({'pose':'smile','actuators':actuators,'finite':bool(np.isfinite(points).all())})
    for view,position in [('front',(0,-4,1.5)),('three-quarter',(2.2,-4,1.5)),('profile',(4,0,1.5))]:
        images.append(study.render(bpy,scene,camera,OUT/f'warm-{view}.png',position,(0,0,1.47),.48))
    controls.restore(bpy,rig,matrices)
    restore_error=float(np.linalg.norm(base.head_geometry(bpy)-neutral,axis=1).max())
    intact=all((len(bpy.data.objects[n].data.vertices),len(bpy.data.objects[n].data.polygons))==counts for n,counts in topology.items())
    new_invalid=sorted(set(base.invalid_drivers(bpy))-set(invalid))
    if not intact or rest!=base.rig_signature(rig) or new_invalid or restore_error>1e-7 or not all(p['finite'] for p in sweep):
        raise ValueError('Native integrity/restore failure; preserve diagnostic, do not publish acceptance')
    attribution='Rain Rig (CC) Blender Foundation | studio.blender.org\nCC BY4.0 https://creativecommons.org/licenses/by/4.0/\n'
    text=bpy.data.texts.new('DOCUFLOW_HEAD_FORM_R9.txt')
    text.write(attribution+'Actual head form experiment. Official source head, 83 indexed cage controls, R9 Cupid/philtrum plus weighted ear reduction and attached canonical colors with verified external lip bindings and re-authored surface-attached brow centerline; all original corrective coordinates transported. Colored head study with source body/hair preserved but hidden, only scarf visibility driver muted. Original pose/shape drivers active. Not a final mom or approved animation rig. Facial rest/control migration still pending. No private images.\n')
    # Save neutral with front camera, not last profile expression.
    from mathutils import Vector
    camera.location=(0,-4,1.5);camera.rotation_euler=(Vector((0,0,1.47))-camera.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.file.pack_all();native=ROOT/'.cache/rain-v3/mom-head-form-r9.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()),compress=True)
    record={'revision':spec['revision'],'status':'new_primary_form_requires_visual_review','new_geometry_created':True,
            'source_url':study.URL,'source_blend_sha256':study.sha(source),'archive_sha256':study.ARCHIVE_SHA,
            'scripts':{n:study.sha(ROOT/'studio/tools'/n) for n in ('mom_head_form_r9.py','mom_face_paint_r9.py','mom_face_finish_r7.py','mom_face_finish_r6.py','mom_face_finish_r5.py','mom_face_controls.py','mom_smile_pose_r3.py','mom_face_probe.py','mom_head_surface_r2.py','mom_head_cage.py','mom_native_form_audit.py','rain_study.py','rain_mom_pass.py','rain_mom_pass_a2.py','rain_mom_pass_a3.py')},
            'original_uv_sha256':original_uv_sha256,'materials':materials,'saved_material_state':material_state,'ear_finish':spec['ear_finish'],'portrait_smile_amount':spec['portrait_smile_amount'],'spec_sha256':study.sha(SPEC),'indexed_source_sha256':study.sha(model.DATA),
            'canonical_face_sha256':study.sha(ROOT/'studio/characters/mom/master/face.png'),
            'blender_version':bpy.app.version_string,'embedded_python_executed':False,
            'base':'Official original Rain head; A1-A7 and R1 deformations are NOT stacked. Revised indexed cage rebuilt from source.',
            'change_notice':'R9: retain R8 nasal dome, mouth placement, anterior cheeks and compact ears; reduce only four authored upper-lip/Cupid/philtrum targets by .8–1.2mm and slight projection. Refine source-rest upper pigment height and separate upper/lower roughness. 2048px ORIGINAL-UV albedo/roughness maps improve vermilion border and canonical warmth; no portrait projection. Authored eyes/brow curve preserved. Restrained smile amount .4. Matched neutral clay and colored views; no hair/body/wardrobe, full blink remains blocked.',
            'edits':edits,'cage_safety':safety,'images':images,'poses':poses,'blink_sweep':sweep,'smile_displacement_symmetry':smile_symmetry,'paired_source_diagnostics':source_diagnostics,
            'source_topology_unchanged':intact,'source_rest_signature':rest,'candidate_rest_signature':base.rig_signature(rig),
            'source_invalid_drivers':invalid,'new_invalid_drivers':new_invalid,'neutral_restore_error_m':restore_error,
            'diagnostic_visibility_driver_mutes':visibility,'pose_and_shape_drivers_muted':False,
            'eye_globes_and_cornea_unchanged':eyes_before==eye_fingerprints(bpy),'eye_coordinate_hashes':eyes_before,'known_blink_visual_failure':True,'blink_visual_approved':False,
            'rig_migration_status':'pending primary-form review; original rest is not an art constraint. Finite ACT diagnostics do not certify the moved lids/brows/correctives.',
            'native_artifact':{'filename':native.name,'sha256':study.sha(native),'textures_packed':True,'storage':'GitHub Actions artifact, 14 days'},
            'indexed_candidate_sha256':study.sha(OUT/'head-edit-data.json.gz'),
            'art_approved':False,'user_approved':False,'production_swap_allowed':False,
            'scope':'Neutral primary head work-in-progress. Not exact likeness, final anatomy, complete character, full acting or production rig approval.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0 https://creativecommons.org/licenses/by/4.0/'}
    study.write(OUT/'report.json',record);make_board()


if __name__=='__main__':
    main()
