"""Paired original/candidate native control diagnostics, never art scores."""
import gzip
import json
import numpy as np
import mom_head_cage as model
import mom_native_form_audit as diagnostic
import mom_face_controls as paired
import rain_mom_pass_a2 as legacy
import rain_mom_pass_a3 as expressions


def neutral_points(bpy):
    return np.asarray(diagnostic.head_data(bpy)['neutral_evaluated_vertices_without_subdivision'])


def mouth_displacement_symmetry(neutral,posed):
    original=np.asarray(json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']['basis_vertices'])
    buckets={}
    for i,p in enumerate(original):buckets.setdefault(tuple(np.round(p,6)),[]).append(i)
    pairs=[]
    for i,p in enumerate(original):
        if not (0.002<p[0]<.085 and p[1]<-.09 and 1.36<p[2]<1.43):continue
        candidates=buckets.get(tuple(np.round(p*[-1,1,1],6)),[])
        if len(candidates)==1:pairs.append((i,candidates[0]))
    if len(pairs)<50:raise ValueError('Insufficient unambiguous mirrored mouth samples')
    a,b=np.asarray(pairs).T;delta=posed-neutral
    residual=np.linalg.norm(delta[a]*[-1,1,1]-delta[b],axis=1)
    return {'unique_mirrored_mouth_pairs':len(pairs),'mean_displacement_asymmetry_m':float(residual.mean()),
            'max_displacement_asymmetry_m':float(residual.max()),
            'scope':'Mirrored actuator displacement diagnostic, not anatomy/likeness/artistic symmetry approval.'}


def key_values(bpy):
    return {k.name:float(k.value) for k in bpy.data.objects['GEO-rain-head'].data.shape_keys.key_blocks}


def eyelid_driver_metadata(bpy):
    output=[]
    for name in ('GEO-rain-head','GEO-rain-eyelashes'):
        keys=bpy.data.objects[name].data.shape_keys
        for curve in keys.animation_data.drivers if keys and keys.animation_data else []:
            if name=='GEO-rain-head' and 'Eyelid' not in curve.data_path:continue
            output.append({'object':name,'path':curve.data_path,'expression':curve.driver.expression,
                           'variables':[{'name':v.name,'targets':[{'bone':t.bone_target,'transform':t.transform_type,'path':t.data_path} for t in v.targets]} for v in curve.driver.variables]})
    return output


def source_probe(bpy,source,out):
    study=diagnostic.study
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False);bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain'];matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones}
    neutral=neutral_points(bpy);scene,camera,_=diagnostic.diagnostic_stage(bpy)
    results={'images':[],'poses':[],'eyelid_driver_metadata':eyelid_driver_metadata(bpy)}
    for label in ('legacy-mixed-smile','paired-z-smile','blink-70-30'):
        legacy.restore(bpy,rig,matrices)
        if label=='legacy-mixed-smile':
            rig.pose.bones['ACT-Lips_Corner.L'].location.z=.0075
            rig.pose.bones['ACT-Lips_Corner.R'].location.y=.015
            rig.update_tag();bpy.context.view_layer.update();act={'policy':'Reproduce R2 mixed-axis solver choice, L:Z .0075 / R:Y .015'}
        elif label=='paired-z-smile':act=paired.set_symmetric_smile(bpy,rig,.6)
        else:act=expressions.set_blink(bpy,rig,1)
        points=neutral_points(bpy)
        results['poses'].append({'pose':label,'controls':act,'final_keys':key_values(bpy),
                                 'mouth_displacement_symmetry':mouth_displacement_symmetry(neutral,points)})
        results['images'].append(study.render(bpy,scene,camera,out/f'source-{label}.png',(0,-4,1.5),(0,0,1.47),.48))
    legacy.restore(bpy,rig,matrices)
    results['scope']='Original unmodified Rain geometry. Source scripts OFF; diagnostic source control/visibility changes discarded by reopening source before candidate build.'
    return results
