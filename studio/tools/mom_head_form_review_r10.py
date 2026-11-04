#!/usr/bin/env python3
"""Matched native R9/R10 geometry/material review, no facial retouch or warp."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw
from mom_head_form_review_r3 import rendered_pupils
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-form-r10'
OLD=ROOT/'studio/reviews/mom-head-form-r9'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path):
    r=json.loads(path.read_text())
    for frame in r['images']:
        if sha(ROOT/frame['path'])!=frame['sha256']:raise ValueError('Actual native frame changed')
    return r


def board(kind):
    with Image.open(OLD/'clay-front.png') as im:a=rendered_pupils(im)
    with Image.open(OUT/'clay-front.png') as im:b=rendered_pupils(im)
    name='clay-front.png' if kind=='form' else 'warm-front.png' if kind=='portrait' else 'candidate-front.png'
    inputs=[('CANONICAL IDENTITY',ROOT/'studio/characters/mom/master/face.png',[[282,395],[489,395]]),
            ('R9 - PREVIOUS',OLD/name,a),('R10 - FORM + ORIGINAL UV PAINT',OUT/name,b)]
    image=Image.new('RGB',(1800,930),'#1c2530');draw=ImageDraw.Draw(image);receipts=[]
    for i,(title,path,anchors) in enumerate(inputs):
        with Image.open(path) as im:
            rgba=im.convert('RGBA');background=Image.new('RGBA',rgba.size,'#26313c');background.alpha_composite(rgba)
            t=similarity(*anchors)
            panel=background.convert('RGB').transform((600,730),Image.Transform.AFFINE,inverse_affine(t),Image.Resampling.BICUBIC,fillcolor='#26313c')
        image.paste(panel,(600*i,70));draw.text((600*i+18,20),title,fill='white',font_size=23)
        receipts.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'pupil_anchors_px':anchors,
                         'similarity':list(t),'anchor_uncertainty_px':4 if i==0 else 3,
                         'anchor_source':'manual canonical picks' if i==0 else 'same-version native clay frame; original eye geometry unchanged'})
    caption={'form':'Neutral clay isolates the local lip/corner revision; no colored material advantage.',
             'color':'R10: reduced lip projection/height, raised corners, warmer localized vermilion response. Nose/cheeks retained.',
             'portrait':'Same native smile helper and amount 0.4 on R9/R10; not complete acting or exact expression matching.'}[kind]
    draw.text((18,819),caption,fill='white',font_size=21)
    draw.text((18,856),'Actual Blender frames; only uniform pupil alignment. No face warp/repaint. Hair/acting incomplete; no art approval.',fill='white',font_size=19)
    draw.text((18,891),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. No calibrated likeness score.',fill='white',font_size=19)
    names={'color':'comparison-identity.png','form':'comparison-form.png','portrait':'comparison-portrait.png'}
    image.save(OUT/names[kind]);return receipts


def main():
    verify(OLD/'report.json');r=verify(OUT/'report.json')
    v=json.loads((OUT/'reopen/verification.json').read_text())
    if r['native_artifact']['sha256']!=v['native_blend_sha256']:raise ValueError('Wrong native file reopened')
    receipt={kind+'_inputs':board(kind) for kind in ('color','form','portrait')}
    receipt.update({'revision':'mom-head-form-r10','script_sha256':sha(Path(__file__)),
                    'new_geometry_created':True,'geometry_changed_since_r9':True,
                    'method':'Uniform pupil alignment only; each version uses its own unchanged-globe clay anchors for color/neutral/pose. Matched clay views isolate geometry from original-UV material changes.',
                    'limitations':['Reference camera/depth not calibrated; visual diagnostic, not a 3D fitting target or likeness score.',
                                  'R10 also changes material. Do not attribute all colored-image differences to geometry.',
                                  'Hair/frame/acting incomplete; single smile-helper comparison does not certify full rig migration.'],
                    'art_approved':False,'user_approved':False,'production_swap_allowed':False})
    (OUT/'image-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
    views=Image.new('RGB',(2304,850),'#1c2530');d=ImageDraw.Draw(views)
    for i,view in enumerate(('front','three-quarter','profile')):
        with Image.open(OUT/f'candidate-{view}.png') as im:views.paste(im,(768*i,50))
        d.text((768*i+20,15),'R10 - '+view.upper(),fill='white',font_size=25)
    d.text((20,820),'Real native face study / original-UV paint. Hair/body hidden. Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0',fill='white',font_size=20)
    views.save(OUT/'color-three-views.png')


if __name__=='__main__':main()
