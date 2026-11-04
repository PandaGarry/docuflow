#!/usr/bin/env python3
"""Actual bpy pose/contact evaluation without rendering; not an animation/art pass."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.pipeline.contracts import load_json,file_hash,canonical_hash
from studio.pipeline.packages import validate_bundle,append_package,bind,apply
from studio.pipeline.timeline import evaluate
from studio.pipeline.kinematics import contact_audit,finger_audit
from studio.pipeline.run_probe import write_json


def run(inputs,package,output,scene=None):
    import bpy
    from studio.pipeline.backends.geometry_probes import measure
    p,a,s=validate_bundle(load_json(inputs/'project.json'),load_json(package),load_json(inputs/'shot.json'))
    if scene:
        bpy.ops.wm.open_mainfile(filepath=str(scene.resolve()),load_ui=False,use_scripts=False)
        objects={o.name:o for o in bpy.context.scene.objects}
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        objects=append_package(bpy,a)
    bindings=bind(objects,a);rows=[];max_ik=0
    for frame in range(*s['frame_range']):
        bpy.context.scene.frame_set(frame)
        if not scene:apply(bindings,evaluate(s,frame))
        bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        for entry in a['ik_checks']:
            rig=objects[entry['armature']].evaluated_get(deps)
            max_ik=max(max_ik,(rig.matrix_world@rig.pose.bones[entry['bone']].tail-objects[entry['target']].matrix_world.translation).length)
        rows.append({'frame':frame,**measure(objects,a,deps)})
    contacts=contact_audit(rows,s['contacts'],a['contact_probes'],s['frame_range'])
    fingers=finger_audit(rows,s['finger_checks'])
    bones=max(r['bone_relative_length_error'] for r in rows)
    passed=contacts['passed'] and fingers['passed'] and max_ik<.005 and bones<.001
    report={'mode':'native_baked_animation' if scene else 'direct_ir_application',
            'scene_sha256':file_hash(scene) if scene else None,'fixture_sha256':canonical_hash({'project':p,'package':a,'shot':s}),
            'scope':'actual bpy pose evaluation, no render/artistic acceptance','status':'passed' if passed else 'failed',
            'asset_id':a['asset_id'],'revision':a['revision'],'blend_sha256':a['blend']['sha256'],
            'frames_evaluated':len(rows),'max_ik_error_m':max_ik,'max_bone_relative_error':bones,
            'contacts':contacts,'fingers':fingers,'measurements':rows}
    write_json(output,report)
    print('POSE_EVALUATION',report['status'],contacts,fingers,max_ik,bones)
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',type=Path,default=ROOT/'studio/production/dad-rig')
    parser.add_argument('--package',type=Path,default=ROOT/'studio/out/dad-rig-r2/package.json')
    parser.add_argument('--out',type=Path,default=ROOT/'studio/production/dad-rig-pose-report.json')
    parser.add_argument('--scene',type=Path,help='Reopen exported native animation; do NOT reapply IR controls')
    args=parser.parse_args();raise SystemExit(run(args.inputs,args.package,args.out,args.scene))
