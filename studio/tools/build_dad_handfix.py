#!/usr/bin/env python3
"""R5 native thumb-root weight correction; frozen R4 art and geometry preserved."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.authoring.refined_hands import hand
from studio.pipeline.contracts import file_hash,safe_path
from studio.tools.build_dad_lookdev import build as build_r4


def build(output):
    import bpy
    build_r4(output/'_r4')
    package=json.loads((output/'_r4/package.json').read_text())
    changes=[]
    for sign,side in [(1,'R'),(-1,'L')]:
        obj=bpy.data.objects[f'DadHandR4{side}'];mesh,tips=hand(sign)
        if len(obj.data.vertices)!=len(mesh.vertices):raise ValueError('R4 topology changed')
        if any(abs(v.co[k]-p[k])>1e-6 for v,p in zip(obj.data.vertices,mesh.vertices) for k in range(3)):
            raise ValueError('R5 weight-only correction changed geometry')
        old=[{obj.vertex_groups[g.group].name:g.weight for g in v.groups} for v in obj.data.vertices]
        obj.vertex_groups.clear()
        groups={b:obj.vertex_groups.new(name=b) for b in sorted({b for w in mesh.weights for b in w})}
        for i,weights in enumerate(mesh.weights):
            for bone,w in weights.items():groups[bone].add([i],w,'REPLACE')
        changes.append({'object':obj.name,'vertices':len(mesh.vertices),
                        'vertices_with_changed_weights':sum(any(abs(w.get(k,0)-v.get(k,0))>1e-6 for k in set(w)|set(v)) for w,v in zip(old,mesh.weights)),
                        'geometry_unchanged':True,'tip_ids_unchanged':True})
    bpy.context.view_layer.update();blend=output/'dad-handfix.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),check_existing=False)
    dependencies=package['provenance']['dependencies']+[{'path':'studio/tools/build_dad_lookdev.py','sha256':file_hash(ROOT/'studio/tools/build_dad_lookdev.py')},
                                                        {'path':'studio/authoring/refined_hands.py','sha256':file_hash(ROOT/'studio/authoring/refined_hands.py')}]
    package.update(revision='r5',blend={'path':blend.relative_to(ROOT).as_posix(),'sha256':file_hash(blend),'collection':package['blend']['collection']})
    package['provenance']={'authoring_script':'studio/tools/build_dad_handfix.py','script_sha256':file_hash(__file__),'license':'project-original','dependencies':dependencies}
    (output/'package.json').write_text(json.dumps(package,indent=2)+'\n')
    (output/'weight-audit.json').write_text(json.dumps({'revision':'r5','scope':'weight-only technical correction; no art/anatomy acceptance','changes':changes},indent=2)+'\n')
    print('DAD_HANDFIX_R5',output/'package.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='studio/out/dad-handfix-r5')
    args=parser.parse_args();build(safe_path(ROOT,args.output))
