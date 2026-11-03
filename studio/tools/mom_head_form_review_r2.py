#!/usr/bin/env python3
"""Unretouched public identity / A7 clay / new head review.

Eye-anchor registration is uniform similarity ONLY, never a facial warp. Black
components are measured in known synthetic-render eye windows, not a biometric
recognizer. The canonical portrait uses documented manual pupil picks. No private
image is opened and no numerical likeness/acceptance score is computed.
"""
from __future__ import annotations
from collections import deque
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from mom_form_review import similarity,inverse_affine

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-form-r2'


def rendered_pupils(image):
    gray=np.asarray(image.convert('L'));result=[]
    for predicted_x in (309,459):
        x0,x1=predicted_x-38,predicted_x+38;y0,y1=345,418
        mask=gray[y0:y1,x0:x1]<28;seen=set();components=[]
        for y,x in zip(*np.where(mask)):
            if (int(y),int(x)) in seen:continue
            queue=deque([(int(y),int(x))]);seen.add((int(y),int(x)));points=[]
            while queue:
                py,px=queue.popleft();points.append((px+x0,py+y0))
                for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
                    qy,qx=py+dy,px+dx
                    if 0<=qy<mask.shape[0] and 0<=qx<mask.shape[1] and mask[qy,qx] and (qy,qx) not in seen:
                        seen.add((qy,qx));queue.append((qy,qx))
            if len(points)>30:
                center=np.mean(points,axis=0)
                score=len(points)/(1+np.linalg.norm(center-[predicted_x,384])**2)
                components.append((score,center,len(points)))
        if not components:raise ValueError('No supported synthetic pupil component; inspect manually')
        _,center,count=max(components,key=lambda c:c[0])
        if abs(center[0]-predicted_x)>15 or abs(center[1]-384)>15:raise ValueError('Unexpected render pupil location')
        result.append(center.tolist())
    return result


def main():
    report=json.loads((OUT/'report.json').read_text())
    if not report['new_geometry_created']:raise ValueError('Do not label diagnostic-only geometry as new')
    for entry in report['images']:
        if hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Native frame changed')
    inputs=[('CANONICAL IDENTITY',ROOT/'studio/characters/mom/master/face.png',[[282,395],[489,395]]),
            ('A7 CLAY - REJECTED',ROOT/'studio/reviews/mom-form-audit/native-v2/existing-a7-clay-front.png',None),
            ('NEW HEAD R2 - WIP',OUT/'candidate-front.png',None)]
    board=Image.new('RGB',(1800,930),'#1c2530');draw=ImageDraw.Draw(board);receipts=[]
    for index,(title,path,anchors) in enumerate(inputs):
        with Image.open(path) as original:
            rgba=original.convert('RGBA');ground=Image.new('RGBA',rgba.size,'#26313c');ground.alpha_composite(rgba)
            source=ground.convert('RGB')
            if anchors is None:anchors=rendered_pupils(source)
            transform=similarity(*anchors)
            panel=source.transform((600,730),Image.Transform.AFFINE,inverse_affine(transform),Image.Resampling.BICUBIC,fillcolor='#26313c')
        board.paste(panel,(index*600,70));draw.text((index*600+18,20),title,fill='white',font_size=25)
        receipts.append({'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'pupil_anchors_px':anchors,'similarity':list(transform),'anchor_uncertainty_px':4 if index==0 else 3})
    draw.text((18,819),'Actual native head rebuild, not hair/material polish. Clay views intentionally expose the form.',fill='white',font_size=23)
    draw.text((18,856),'ONLY uniform eye-anchor alignment. Camera/expression/shading differ from art; no likeness score or approval.',fill='white',font_size=20)
    draw.text((18,891),'Private images excluded. Rain Rig (CC) Blender Foundation | studio.blender.org - modified, CC BY 4.0',fill='white',font_size=19)
    board.save(OUT/'comparison-identity.png')
    data={'new_geometry_created':True,'art_approved':False,'user_approved':False,'production_swap_allowed':False,
          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'inputs':receipts,
          'method':'Two pupil anchors; only uniform scale, rotation and translation. No anisotropic resizing, face warp or retouch.',
          'limitations':['Synthetic-render pupil dark components manually reviewable; centers have shading/glint uncertainty.','Cartoon portrait has no calibrated camera or 3D depth. This registration is a visual diagnostic, not a fitting target or likeness score.'],
          'scope':'Actual modified geometry, initial primary-head review. No hair/body/wardrobe/acting acceptance.'}
    (OUT/'image-review.json').write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    main()
