#!/usr/bin/env python3
"""Public-art/A7 form audit: comparable alignment, not another design revision.

Two manually picked pupil centers define only translation/rotation/uniform scale.
No warping, beauty retouch, silhouette hallucination, face recognition or score.
Private references are never opened; all inputs already exist in tracked assets.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-form-audit'


def similarity(left,right,target_left=(190,220),target_right=(410,220)):
    lx,ly=left;rx,ry=right;tx,ty=target_left;ux,uy=target_right
    dx,dy=rx-lx,ry-ly
    denominator=dx*dx+dy*dy
    if denominator<=1e-12:raise ValueError('Coincident eye anchors')
    a=((ux-tx)*dx+(uy-ty)*dy)/denominator
    b=((uy-ty)*dx-(ux-tx)*dy)/denominator
    return (a,b,tx-a*lx+b*ly,ty-b*lx-a*ly)


def point(transform,p):
    a,b,tx,ty=transform;x,y=p
    return (a*x-b*y+tx,b*x+a*y+ty)


def inverse_affine(transform):
    a,b,tx,ty=transform;denominator=a*a+b*b
    return (a/denominator,b/denominator,(-a*tx-b*ty)/denominator,
            -b/denominator,a/denominator,(b*tx-a*ty)/denominator)


def ratios(points):
    t=similarity(points['pupil_l'],points['pupil_r'],(0,0),(1,0))
    aligned={name:point(t,p) for name,p in points.items()}
    return {'eye_opening_width_l':abs(aligned['eye_inner_l'][0]-aligned['eye_outer_l'][0]),
            'nasal_base_width':abs(aligned['nasal_base_r'][0]-aligned['nasal_base_l'][0]),
            'mouth_width':abs(aligned['mouth_corner_r'][0]-aligned['mouth_corner_l'][0]),
            'eye_line_to_subnasale':aligned['subnasale'][1],
            'eye_line_to_mouth':aligned['stomion'][1],
            'eye_line_to_chin':aligned['chin'][1],
            'mouth_to_chin':aligned['chin'][1]-aligned['stomion'][1]}


def make_review():
    from PIL import Image,ImageDraw,ImageOps
    OUT.mkdir(parents=True,exist_ok=True)
    spec=json.loads((OUT/'landmarks.json').read_text())
    panels=[];records={}
    for name,entry in spec['images'].items():
        path=ROOT/entry['path'];marks=entry['points']
        transform=similarity(marks['pupil_l'],marks['pupil_r'])
        with Image.open(path) as source:
            # Composite transparent canonical portrait over the same neutral ground.
            rgba=source.convert('RGBA')
            background=Image.new('RGBA',rgba.size,'#26313c');background.alpha_composite(rgba)
            aligned=background.convert('RGB').transform((600,730),Image.Transform.AFFINE,
                      inverse_affine(transform),Image.Resampling.BICUBIC,fillcolor='#26313c')
        panels.append(aligned)
        records[name]={'input':entry['path'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'similarity':list(transform),'manual_uncertainty_px':entry['manual_uncertainty_px'],
                       'ratios_in_inter_pupil_units':ratios(marks)}
    overlay=Image.blend(panels[0],panels[1],.5)
    board=Image.new('RGB',(1800,930),'#1c2530');draw=ImageDraw.Draw(board)
    titles=['CANON: HIGH-RES IDENTITY','A7: EXISTING, REJECTED','50/50 ALIGNED OVERLAY']
    for i,panel in enumerate(panels+[overlay]):
        board.paste(panel,(600*i,70));draw.text((600*i+18,20),titles[i],fill='white',font_size=23)
    for i,(name,entry) in enumerate(spec['images'].items()):
        t=records[name]['similarity'];color='#79e0c6' if i==0 else '#ffb374'
        for key in ('pupil_l','pupil_r','subnasale','stomion','chin'):
            x,y=point(t,entry['points'][key]);x+=i*600;y+=70
            draw.ellipse((x-3,y-3,x+3,y+3),outline=color,width=2)
        for key in ('subnasale','stomion','chin'):
            _,y=point(t,entry['points'][key]);y+=70
            draw.line((1200,y,1800,y),fill=color,width=2)
    draw.text((1210,770),'CYAN: canon / AMBER: A7',fill='white',font_size=19)
    draw.text((18,819),'Eye anchors aligned by uniform scale/rotation/translation ONLY. No new model or likeness pass.',fill='white',font_size=23)
    draw.text((18,856),'Manual picks + different camera/gaze/expression: ratios are clues, not calibrated 3D targets or an approval score.',fill='white',font_size=20)
    draw.text((18,891),'Public canonical art + actual old A7. Private photographs excluded. Rain Rig (CC) Blender Foundation | studio.blender.org',fill='white',font_size=17)
    board.save(OUT/'eye-aligned-audit.png')
    # A whole-body comparison explicitly declares the unresolved pose mismatch.
    body=Image.new('RGB',(1200,1110),'#1c2530');bd=ImageDraw.Draw(body)
    sources=[ROOT/'studio/characters/mom/views/front.png',ROOT/'studio/reviews/rain-mom-a7/candidate-full.png']
    for i,path in enumerate(sources):
        with Image.open(path) as im:
            if i==0:
                rgba=im.convert('RGBA');ground=Image.new('RGBA',rgba.size,'#26313c');ground.alpha_composite(rgba);im=ground.convert('RGB')
            else:
                # Existing native framing: retain complete body/arms, not a silhouette warp.
                im=im.convert('RGB')
            panel=ImageOps.contain(im,(580,950),Image.Resampling.LANCZOS)
            body.paste(panel,(i*600+(600-panel.width)//2,65+(950-panel.height)//2))
    bd.text((20,20),'CANONICAL FRONT',fill='white',font_size=25)
    bd.text((620,20),'A7 EXISTING / DIFFERENT POSE',fill='white',font_size=23)
    bd.text((20,1030),'Pose/projection differ: NOT a calibrated body-proportion comparison.',fill='white',font_size=23)
    bd.text((20,1069),'A7 wardrobe/silhouette/design remain unaccepted. No new body geometry here.',fill='white',font_size=21)
    body.save(OUT/'whole-character-audit.png')
    report={'status':'rejected_requires_major_rework','new_geometry_created':False,
            'scope':'Public-image form audit only; no new native geometry or likeness claim.',
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'landmark_spec_sha256':hashlib.sha256((OUT/'landmarks.json').read_bytes()).hexdigest(),
            'aligned_inputs':records,'ratio_unit':'Inter-pupil distance in original 2D image',
            'limitations':spec['limits'],
            'finding':'A7 failure is broad design/form/style, not only seams. Need deliberate primary-form and multi-view reconstruction before more hair/material polish.',
            'art_approved':False,'production_swap_allowed':False,
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0 https://creativecommons.org/licenses/by/4.0/'}
    (OUT/'image-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    make_review()
