"""Matched native R4/R7 ear/form crops, same crop and uniform scale only."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-form-r7'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    old=json.loads((ROOT/'studio/reviews/mom-head-form-r4/report.json').read_text())
    new=json.loads((OUT/'report.json').read_text())
    board=Image.new('RGB',(1286,1310),'#1c2530');draw=ImageDraw.Draw(board);inputs=[]
    draw.text((15,15),'R4 - BEFORE',fill='white',font_size=24)
    draw.text((658,15),'R7 - COMPACT EARS',fill='white',font_size=24)
    for row,view in enumerate(('front','three-quarter','profile')):
        a=next(f for f in old['images'] if f['path'].endswith(f'candidate-{view}.png'))
        b=next(f for f in new['images'] if f['path'].endswith(f'clay-{view}.png'))
        if a['camera']!=b['camera']:raise ValueError('Mismatched native cameras')
        for column,frame in enumerate((a,b)):
            path=ROOT/frame['path']
            if sha(path)!=frame['sha256']:raise ValueError('Native frame changed')
            with Image.open(path) as im:
                panel=im.crop((130,290,638,610)).resize((635,400),Image.Resampling.BICUBIC)
            board.paste(panel,(column*643+8,55+row*400));inputs.append(frame)
    draw.text((15,1270),'Same native cameras/crop/scale. Ears adjusted, not hidden. Rain Rig (CC) Blender Foundation | studio.blender.org',fill='white',font_size=16)
    board.save(OUT/'comparison-ears.png')
    (OUT/'ear-image-review.json').write_text(json.dumps({'inputs':inputs,'crop_px':[130,290,638,610],
        'uniform_scale':1.25,'script_sha256':sha(Path(__file__)),
        'method':'Identical matched-camera crop and uniform enlargement of actual native clay frames. No repaint/warp.',
        'limitations':'R4 to R7 also includes documented lip refinements; not an ear-only geometric ablation. Reference ears obscured; no calibrated target ear size.',
        'art_approved':False,'production_swap_allowed':False},indent=2)+'\n')

if __name__=='__main__':main()
