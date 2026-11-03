"""Actual matched native R8/R9 lip detail. Same crop/uniform enlargement only."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-head-form-r9'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    image=Image.new('RGB',(1356,560),'#1c2530');d=ImageDraw.Draw(image);inputs=[]
    for i,rev in enumerate((8,9)):
        path=ROOT/f'studio/reviews/mom-head-form-r{rev}/candidate-front.png'
        report=json.loads((path.parent/'report.json').read_text())
        frame=next(f for f in report['images'] if f['path']==path.relative_to(ROOT).as_posix())
        if frame['sha256']!=sha(path):raise ValueError('Native frame changed')
        if inputs and inputs[0]['camera']!=frame['camera']:raise ValueError('Different cameras')
        with Image.open(path) as im:panel=im.crop((275,420,493,570)).resize((654,450),Image.Resampling.BICUBIC)
        image.paste(panel,(i*678+12,55));d.text((i*678+18,18),f'R{rev} - ACTUAL NATIVE DETAIL',fill='white',font_size=24)
        inputs.append(frame)
    d.text((18,520),'Same crop/scale, no repaint/warp. Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0',fill='white',font_size=17)
    image.save(OUT/'comparison-lips.png')
    (OUT/'lip-image-review.json').write_text(json.dumps({'inputs':inputs,'crop_px':[275,420,493,570],
        'uniform_scale':3,'script_sha256':sha(Path(__file__)),
        'scope':'Local shape plus pigment/roughness changes; not a geometry-only or likeness score.',
        'art_approved':False,'production_swap_allowed':False},indent=2)+'\n')

if __name__=='__main__':main()
