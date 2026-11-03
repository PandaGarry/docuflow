#!/usr/bin/env python3
"""Native evaluated-surface stress test. Heuristics, NOT artistic/collision approval."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from studio.pipeline.contracts import file_hash,load_json,canonical_hash
from studio.pipeline.packages import validate_bundle,append_package,bind,apply
from studio.pipeline.kinematics import contact_audit
from studio.pipeline.timeline import evaluate
from studio.pipeline.run_probe import write_json


def poses():
    result=[('neutral',{})]
    for side,sign in [('R',1),('L',-1)]:
        for name,target,clavicle in [('forward',(.62,.52,1.72),.10),('overhead',(.53,.08,2.44),.20),
                                      ('abduction',(1.11,0,1.84),.10),('elbow_fold',(.48,.25,1.67),.05)]:
            result.append((f'{side}_{name}',{f'arm.{side}.target':[sign*target[0],target[1],target[2]],f'clavicle.{side}.rotation':[clavicle,0,0]}))
        for name,angle in [('flexion',.6),('extension',-.5),('deviation',.35)]:
            result.append((f'{side}_wrist_{name}',{f'wrist.{side}.rotation':([0,0,angle] if name=='deviation' else [angle,0,0])}))
        curl={f'finger.{side}.{n}.{j:02d}':[a,0,0] for n in ('index','middle','ring','pinky','thumb') for j,a in enumerate((.6,.8,.5),1)}
        result.append((f'{side}_curl',curl))
    return result


def run(package_path,output,render_dir=None,animation=False):
    import bpy
    from mathutils import Vector
    from studio.pipeline.backends.geometry_probes import measure
    from studio.pipeline.backends.package_worker import stage
    p,a,s=validate_bundle(load_json(ROOT/'studio/production/dad-refined/project.json'),load_json(package_path),load_json(ROOT/'studio/production/dad-refined/shot.json'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects=append_package(bpy,a);bindings=bind(objects,a)
    defaults={c:[0,0,0] for c,(typ,target) in bindings.items() if typ=='POSE_ROTATION'}
    defaults.update({'arm.R.target':[.75,.02,1.11],'arm.L.target':[-.75,.02,1.11]})
    meshes=[o for o in objects.values() if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers) and o.name.startswith(('DadSweater','DadPants','DadHand'))]

    def snapshot(obj,deps):
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            points=[evaluated.matrix_world@v.co for v in mesh.vertices]
            triangles=[(p.vertices[0],p.vertices[i],p.vertices[i+1]) for p in mesh.polygons for i in range(1,len(p.vertices)-1)]
            areas=[(points[b]-points[a]).cross(points[c]-points[a]).length/2 for a,b,c in triangles]
            edges=sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
            lengths=[(points[b]-points[a]).length for a,b in edges]
            if any(not math.isfinite(v) or v<=1e-12 for v in areas+lengths):raise ValueError('degenerate/nonfinite evaluated surface')
            return {'areas':areas,'lengths':lengths,'triangles':triangles,'vertices':len(points)}
        finally:evaluated.to_mesh_clear()

    scene=None
    if render_dir:
        render_dir.mkdir(parents=True,exist_ok=True)
        review=json.loads(json.dumps(p));review['resolution']=[768,576];review['render']['samples']=16
        review['camera']={'position':[2.5,7,2.9],'target':[.05,0,1.42],'ortho_scale':4.6}
        scene=stage(bpy,review)
    reference={};rows=[];geometry_rows=[]
    cases=[(f'frame_{f:03d}',evaluate(s,f)) for f in range(*s['frame_range'])] if animation else poses()
    for index,(name,values) in enumerate(cases):
        apply(bindings,defaults);apply(bindings,values);bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get();errors=[]
        for check in a['ik_checks']:
            rig=objects[check['armature']].evaluated_get(deps)
            errors.append((rig.matrix_world@rig.pose.bones[check['bone']].tail-objects[check['target']].matrix_world.translation).length)
        stats={}
        for obj in meshes:
            current=snapshot(obj,deps)
            if index==0:reference[obj.name]=current
            base=reference[obj.name]
            if current['triangles']!=base['triangles']:raise ValueError('probe topology changed between poses')
            ratios=[x/y for x,y in zip(current['areas'],base['areas'])]
            stretches=[x/y for x,y in zip(current['lengths'],base['lengths'])]
            stats[obj.name]={'vertices':current['vertices'],'area_ratio_min':min(ratios),'area_ratio_max':max(ratios),'edge_ratio_max':max(stretches)}
        measured=measure(objects,a,deps);geometry_rows.append({'frame':index,**measured})
        passed=max(errors)<=.005 and measured['bone_relative_length_error']<=.001 and all(v['area_ratio_min']>.025 and v['area_ratio_max']<6 and v['edge_ratio_max']<3 for v in stats.values())
        rows.append({'pose':name,'passed':passed,'max_ik_error_m':max(errors),'surface_metrics':stats})
        print('EXTREME_POSE',name,passed,max(errors),flush=True)
        if scene and name in ('neutral','R_overhead','R_curl'):
            scene.render.filepath=str((render_dir/f'{name}.png').resolve());bpy.ops.render.render(write_still=True)
    contacts=contact_audit(geometry_rows,[{'probe':q['id'],'frame_range':[0,len(rows)]} for q in a['contact_probes']],a['contact_probes'],[0,len(rows)])
    report={'status':'passed' if all(r['passed'] for r in rows) and contacts['passed'] else 'failed','scope':f'{len(rows)} '+('animated frames' if animation else 'static poses')+'; heuristic strain/IK/contact safety, NOT collision/likeness/artistic approval',
            'fixture_sha256':canonical_hash({'project':p,'package':a,'shot':s}) if animation else canonical_hash(poses()),
            'max_native_weight_sum_error':max(abs(sum(g.weight for g in v.groups)-1) for o in meshes for v in o.data.vertices),
            'blend_sha256':a['blend']['sha256'],'checker_sha256':file_hash(__file__),'poses':rows,'contacts':contacts,
            'limits':{'min_area_ratio':.025,'max_area_ratio':6,'max_edge_ratio':3,'max_ik_error_m':.005},
            'review_renders':[{'path':p.resolve().relative_to(ROOT).as_posix(),'sha256':file_hash(p)} for p in sorted(render_dir.glob('*.png'))] if render_dir else []}
    write_json(output,report);return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,default=ROOT/'studio/out/dad-refined-r3/package.json')
    parser.add_argument('--output',type=Path,default=ROOT/'studio/production/dad-r3-extremes.json')
    parser.add_argument('--render-dir',type=Path)
    parser.add_argument('--animation',action='store_true',help='Evaluate all fixture frames, not just static extreme cases')
    args=parser.parse_args();raise SystemExit(run(args.package,args.output,args.render_dir,args.animation))
