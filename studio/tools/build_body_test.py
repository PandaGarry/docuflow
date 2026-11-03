#!/usr/bin/env python3
"""Author a slow technical weight-shift/two-short-steps fixture; not a walk system."""
from __future__ import annotations
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.authoring.mesh import smooth


def sample(keys,frame):
    for (a,va),(b,vb) in zip(keys,keys[1:]):
        if a<=frame<=b:
            t=smooth((frame-a)/(b-a))
            return [x+(y-x)*t for x,y in zip(va,vb)]
    return keys[0][1] if frame<keys[0][0] else keys[-1][1]


def build(output):
    project={'schema_version':2,'kind':'project','project_id':'dad-r2-body-test','purpose':'rig_preview','fps':{'num':24,'den':1},
             'resolution':[640,360],'render':{'samples':6,'threads':2,'denoise':True,'seed':67},
             'resources':{'chunk_frames':4,'rss_limit_mb':1536,'timeout_seconds':180}}
    shot={'schema_version':2,'kind':'shot','shot_id':'dad-r2-support-and-fingers','project_id':project['project_id'],
          'asset_id':'dad-body-rig','asset_revision':'r2','frame_range':[0,72],'tracks':[],
          'contacts':[{'probe':'sole.L','frame_range':[0,49]},{'probe':'sole.L','frame_range':[61,72]},
                      {'probe':'sole.R','frame_range':[0,13]},{'probe':'sole.R','frame_range':[37,72]}],
          'finger_checks':[{'probe':f'finger.R.{name}','min_span_m':.025} for name in ('index','middle','ring','pinky','thumb')]}
    values={}
    roots=[(0,[0,0,0]),(8,[-.08,0,-.025]),(20,[-.08,.01,-.04]),(36,[0,.07,-.03]),(48,[.08,.1,-.025]),(60,[.08,.18,-.015]),(71,[0,.2,0])]
    for f in range(72):
        root=sample(roots,f);values.setdefault('body.translation',[]).append(root)
        for side,sign in [('R',1),('L',-1)]:
            values.setdefault(f'arm.{side}.target',[]).append([sign*.75+root[0],.02+root[1],1.11+root[2]])
            if side=='R':a,b,lift=12,36,.12
            else:a,b,lift=48,60,.10
            u=max(0,min(1,(f-a)/(b-a)))
            values.setdefault(f'foot.{side}.target',[]).append([sign*.215,.2*smooth(u),.20+lift*math.sin(math.pi*u)])
            values.setdefault(f'foot.{side}.rotation',[]).append([0,0,0])
        curl=sample([(0,[0]),(35,[0]),(49,[1]),(58,[1]),(71,[0])],f)[0]
        values.setdefault('wrist.R.rotation',[]).append([.12*curl,0,0])
        for name in ('index','middle','ring','pinky','thumb'):
            for j,angle in enumerate((.6,.8,.5),1):
                values.setdefault(f'finger.R.{name}.{j:02d}',[]).append([angle*curl,0,0])
        head=sample([(0,[0,0,0]),(24,[0,0,-.06]),(48,[0,0,.06]),(71,[0,0,0])],f)
        values.setdefault('head.rotation',[]).append(head)
    for name,sequence in values.items():shot['tracks'].append({'control':name,'keys':[{'frame':f,'value':v} for f,v in enumerate(sequence)]})
    output.mkdir(parents=True,exist_ok=True)
    for name,doc in [('project',project),('shot',shot)]:
        (output/f'{name}.json').write_text(json.dumps(doc,indent=2)+'\n')


if __name__=='__main__':build(ROOT/'studio/production/dad-rig')
