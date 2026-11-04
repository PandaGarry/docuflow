#!/usr/bin/env python3
"""A slow reach/curl/recovery fixture, not a full acting or walk performance."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from studio.tools.build_body_test import sample


def build(output):
    project = json.loads((ROOT/'studio/production/dad-rig/project.json').read_text())
    project['project_id'] = 'dad-r3-deformation-test'
    shot = {'schema_version':2,'kind':'shot','shot_id':'dad-r3-extreme-reach-and-curl','project_id':project['project_id'],
            'asset_id':'dad-body-rig','asset_revision':'r3','frame_range':[0,72],'tracks':[],
            'contacts':[{'probe':f'sole.{s}','frame_range':[0,72]} for s in ('R','L')],
            'finger_checks':[{'probe':f'finger.R.{n}','min_span_m':.025} for n in ('index','middle','ring','pinky','thumb')]}
    tracks = {}
    for f in range(72):
        reach = sample([(0,[0]),(8,[0]),(30,[1]),(44,[1]),(71,[0])],f)[0]
        curl = sample([(0,[0]),(30,[0]),(41,[1]),(48,[1]),(65,[0]),(71,[0])],f)[0]
        # A spatial arc avoids pulling the wrist straight through a deeply
        # folded elbow halfway to the raised pose. Not just scalar easing.
        target = [(1-reach)**2*a+2*(1-reach)*reach*b+reach**2*c
                  for a,b,c in zip((.75,.02,1.11),(1.24,.12,1.32),(.65,.44,1.90))]
        values = {'arm.R.target':target,'arm.L.target':[-.75,.02,1.11],
                  'clavicle.R.rotation':[.15*reach,0,0],'clavicle.L.rotation':[0,0,0],
                  'wrist.R.rotation':[.1*reach,0,0],'head.rotation':[0,0,-.06*reach]}
        for side,sign in [('R',1),('L',-1)]:
            values[f'foot.{side}.target'] = [sign*.215,0,.20]
            values[f'foot.{side}.rotation'] = [0,0,0]
        for name in ('index','middle','ring','pinky','thumb'):
            for j,angle in enumerate((.6,.8,.5),1): values[f'finger.R.{name}.{j:02d}'] = [angle*curl,0,0]
        for control,value in values.items(): tracks.setdefault(control,[]).append({'frame':f,'value':value})
    shot['tracks'] = [{'control':c,'keys':keys} for c,keys in tracks.items()]
    output.mkdir(parents=True,exist_ok=True)
    for name,doc in [('project',project),('shot',shot)]: (output/f'{name}.json').write_text(json.dumps(doc,indent=2)+'\n')


if __name__ == '__main__': build(ROOT/'studio/production/dad-refined')
