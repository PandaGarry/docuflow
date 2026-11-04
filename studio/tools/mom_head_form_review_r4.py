#!/usr/bin/env python3
"""R4 actual native frame review. Uniform pupil alignment only, no face warp."""
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw
from mom_head_form_review_r3 import rendered_pupils
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-form-r4'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frames(report_path):
    report=json.loads(report_path.read_text())
    for frame in report['images']:
        if sha(ROOT/frame['path'])!=frame['sha256']:raise ValueError('Native frame hash mismatch')
    return report


def identity_board(warm=False):
    before=ROOT/'studio/reviews/mom-head-form-r3'
    inputs=[('CANONICAL IDENTITY',ROOT/'studio/characters/mom/master/face.png',[[282,395],[489,395]]),
            ('R3 - PREVIOUS',before/('reopen/warm-smile.png' if warm else 'candidate-front.png'),None),
            ('R4 - LIKENESS STUDY',OUT/('warm-front.png' if warm else 'candidate-front.png'),None)]
    board=Image.new('RGB',(1800,930),'#1c2530');draw=ImageDraw.Draw(board);receipts=[]
    for index,(title,path,anchors) in enumerate(inputs):
        with Image.open(path) as image:
            rgba=image.convert('RGBA');ground=Image.new('RGBA',rgba.size,'#26313c');ground.alpha_composite(rgba)
            source=ground.convert('RGB')
            if anchors is None:anchors=rendered_pupils(source)
            transform=similarity(*anchors)
            panel=source.transform((600,730),Image.Transform.AFFINE,inverse_affine(transform),Image.Resampling.BICUBIC,fillcolor='#26313c')
        board.paste(panel,(index*600,70));draw.text((index*600+18,20),title,fill='white',font_size=25)
        receipts.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'pupil_anchors_px':anchors,
                         'similarity':list(transform),'anchor_uncertainty_px':4 if index==0 else 3})
    caption='Same balanced smile helper on R3 and R4; actual native frames.' if warm else 'Neutral R3 / R4: mouth raised and widened, rounder nasal tip, tapered lower jaw.'
    draw.text((18,819),caption,fill='white',font_size=23)
    draw.text((18,856),'Uniform eye-anchor alignment only. No face retouch/warp. Camera/material differ; no likeness score or approval.',fill='white',font_size=19)
    draw.text((18,891),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified, CC BY 4.0. Hair/body/acting unfinished.',fill='white',font_size=19)
    board.save(OUT/('comparison-warm.png' if warm else 'comparison-identity.png'))
    return receipts


def main():
    verify_frames(ROOT/'studio/reviews/mom-head-form-r3/report.json')
    report=verify_frames(OUT/'report.json')
    previous=json.loads((ROOT/'studio/reviews/mom-head-form-r3/reopen/verification.json').read_text())
    if sha(ROOT/previous['warm_smile_render']['path'])!=previous['warm_smile_render']['sha256']:
        raise ValueError('R3 balanced warm frame changed')
    neutral=identity_board();warm=identity_board(True)
    build=json.loads((OUT/'reopen/verification.json').read_text())
    if build['native_blend_sha256']!=report['native_artifact']['sha256']:raise ValueError('Wrong saved binary reopened')
    record={'revision':'mom-head-form-r4','script_sha256':sha(Path(__file__)),
            'neutral_inputs':neutral,'warm_inputs':warm,
            'method':'Uniform pupil-anchor scale/rotation/translation, no anisotropic resizing, facial warp or retouch.',
            'limitations':['Reference camera/depth unknown; positions are diagnostic, not calibrated 3D targets.',
                          'Clothes/hair/material and expression differences remain; no automated likeness score.'],
            'new_geometry_created':True,'art_approved':False,'user_approved':False,'production_swap_allowed':False}
    (OUT/'image-review.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':main()
