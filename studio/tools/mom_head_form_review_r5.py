#!/usr/bin/env python3
"""R5 real clay/color review. Never warp or repaint the face to match the art."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from mom_head_form_review_r3 import rendered_pupils
from mom_form_review import similarity,inverse_affine
import mom_head_cage as model
import mom_face_finish_r5 as finish
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-form-r5'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_board(warm=False):
    # Use identical geometry-based anchors for colored and clay images. Iris
    # shader contrast must not produce a different registration of the face.
    with Image.open(OUT/'clay-front.png') as im:anchors=rendered_pupils(im)
    inputs=[('CANONICAL IDENTITY',ROOT/'studio/characters/mom/master/face.png',[[282,395],[489,395]]),
            ('R5 - ACTUAL FORM',OUT/'clay-front.png',anchors),
            ('R5 - CANONICAL PALETTE',OUT/('warm-front.png' if warm else 'candidate-front.png'),anchors)]
    board=Image.new('RGB',(1800,930),'#1c2530');draw=ImageDraw.Draw(board);receipts=[]
    for index,(title,path,pupils) in enumerate(inputs):
        with Image.open(path) as im:
            rgba=im.convert('RGBA');background=Image.new('RGBA',rgba.size,'#26313c');background.alpha_composite(rgba)
            transform=similarity(*pupils)
            panel=background.convert('RGB').transform((600,730),Image.Transform.AFFINE,inverse_affine(transform),Image.Resampling.BICUBIC,fillcolor='#26313c')
        board.paste(panel,(index*600,70));draw.text((index*600+18,20),title,fill='white',font_size=25)
        receipts.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'pupil_anchors_px':pupils,
                         'similarity':list(transform),'anchor_uncertainty_px':4 if index==0 else 3,
                         'anchor_source':'manual canonical picks' if index==0 else 'same R5 clay frame; unchanged eye globe geometry'})
    caption='R5 restrained smile amount 0.4; form panel remains neutral.' if warm else 'R5: smaller/tucked original ears, lip/philtrum refinement, attached skin/lip/brow/iris colors.'
    draw.text((18,819),caption,fill='white',font_size=22)
    draw.text((18,856),'Actual Blender frames. Uniform alignment only, no face retouch/warp. Hair/acting unfinished; no art approval.',fill='white',font_size=19)
    draw.text((18,891),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified, CC BY 4.0. Albedo colors are not pixel matches.',fill='white',font_size=19)
    board.save(OUT/('comparison-portrait.png' if warm else 'comparison-identity.png'))
    return receipts


def main():
    report=json.loads((OUT/'report.json').read_text())
    for frame in report['images']:
        if sha(ROOT/frame['path'])!=frame['sha256']:raise ValueError('Actual frame changed')
    neutral=identity_board();portrait=identity_board(True)
    before=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-head-form-r4/head-edit-data.json.gz').read_bytes()))
    after=json.loads(gzip.decompress((OUT/'head-edit-data.json.gz').read_bytes()))
    source=json.loads(gzip.decompress(model.DATA.read_bytes()))['official-source']
    mask=finish.ear_mask(source);a=np.array(before['basis_vertices']);b=np.array(after['basis_vertices'])
    measurements={}
    for side,sign in [('L',1),('R',-1)]:
        select=(mask>.5)&(sign*np.array(source['basis_vertices'])[:,0]>0)
        measurements[side]={'vertices':int(select.sum()),'r4_outer_abs_x_m':float(np.abs(a[select,0]).max()),
                            'r5_outer_abs_x_m':float(np.abs(b[select,0]).max()),
                            'r4_z_extent_m':float(np.ptp(a[select,2])),'r5_z_extent_m':float(np.ptp(b[select,2]))}
    record={'revision':'mom-head-form-r5','script_sha256':sha(Path(__file__)),
            'neutral_inputs':neutral,'portrait_inputs':portrait,'ear_geometry_diagnostics':measurements,
            'method':'Uniform pupil-anchor scale/rotation/translation. Identical R5 transform for clay/color; no anisotropic resize, face warp or retouch.',
            'limitations':['Ear subset extents describe the editable geometry, not aesthetic quality or a reference-calibrated ear size.',
                          'Reference depth/camera unknown; materials/expression/hair differ. No likeness score or exact-pixel color claim.'],
            'new_geometry_created':True,'art_approved':False,'user_approved':False,'production_swap_allowed':False}
    (OUT/'image-review.json').write_text(json.dumps(record,indent=2)+'\n')
    views=Image.new('RGB',(2304,850),'#1c2530');d=ImageDraw.Draw(views)
    for i,view in enumerate(('front','three-quarter','profile')):
        with Image.open(OUT/f'candidate-{view}.png') as im:views.paste(im,(768*i,50))
        d.text((768*i+20,15),'R5 COLOR - '+view.upper(),fill='white',font_size=25)
    d.text((20,820),'Actual native face study; hair/body hidden. Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0',fill='white',font_size=22)
    views.save(OUT/'color-three-views.png')


if __name__=='__main__':main()
