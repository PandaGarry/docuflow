"""Controlled portrait presentation plus explicit SAME-ASSET lighting comparison."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-head-lookdev-r10'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def panel(path,anchors):
    with Image.open(path) as im:
        rgba=im.convert('RGBA');bg=Image.new('RGBA',rgba.size,'#26313c');bg.alpha_composite(rgba)
        t=similarity(*anchors)
        result=bg.convert('RGB').transform((600,730),Image.Transform.AFFINE,inverse_affine(t),Image.Resampling.BICUBIC,fillcolor='#26313c')
    return result,{'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'pupil_anchors_px':anchors,'similarity':list(t)}

def board(name,inputs,captions):
    image=Image.new('RGB',(600*len(inputs),930),'#1c2530');d=ImageDraw.Draw(image);receipts=[]
    for i,(title,path,anchors) in enumerate(inputs):
        p,r=panel(path,anchors);image.paste(p,(600*i,70));d.text((600*i+18,20),title,fill='white',font_size=22);receipts.append(r)
    for i,text in enumerate(captions):d.text((18,819+36*i),text,fill='white',font_size=18)
    image.save(OUT/name);return receipts

def main():
    r=read(OUT/'report.json');primary=read(ROOT/'studio/reviews/mom-head-form-r10/image-review.json')
    for f in r['images']+[r['sources']['10']['independent_neutral_render']]:
        if sha(ROOT/f['path'])!=f['sha256']:raise ValueError('Actual downloaded-native frame changed')
    anchors={}
    for i,rev in ((1,9),(2,10)):
        old=primary['color_inputs'][i]['pupil_anchors_px']
        # Identical camera/framing and unchanged eyes. Convert pixel centers
        # from 768 diagnostic frames to 1024; don't rediscover different glints.
        anchors[rev]=[[(x+.5)*4/3-.5,(y+.5)*4/3-.5] for x,y in old]
    credit='Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. Hair/acting incomplete.'
    a=board('comparison-portrait.png',[
        ('CANONICAL IDENTITY',ROOT/'studio/characters/mom/master/face.png',[[282,395],[489,395]]),
        ('R9 - MATCHED PORTRAIT LIGHT',OUT/'r9-warm-front.png',anchors[9]),
        ('R10 - CURRENT PORTRAIT LIGHT',OUT/'r10-warm-front.png',anchors[10])],
        ['Same lights, camera, native smile 0.4; actual DOWNLOADED binaries. Includes form + material changes, not geometry-only evidence.',
         'Only uniform pupil alignment; no face warp/repaint. Reference camera/depth unknown; no calibrated likeness or final art acceptance.',credit])
    b=board('comparison-lighting.png',[
        ('SAME R10 - DIAGNOSTIC LIGHT',ROOT/'studio/reviews/mom-head-form-r10/candidate-front.png',primary['color_inputs'][2]['pupil_anchors_px']),
        ('SAME R10 - PORTRAIT LIGHT',OUT/'r10-neutral-front.png',anchors[10])],
        ['Same neutral geometry AND materials. Only light/view settings/sampling differ.',
         'Not another form improvement. Actual native frames; uniform alignment only.',credit])
    image=Image.new('RGB',(1920,720),'#1c2530');d=ImageDraw.Draw(image)
    for i,view in enumerate(('front','three-quarter','profile')):
        with Image.open(OUT/f'r10-warm-{view}.png') as im:image.paste(im.resize((640,640),Image.Resampling.BICUBIC),(640*i,40))
        d.text((640*i+18,12),'R10 PORTRAIT - '+view.upper(),fill='white',font_size=21)
    d.text((18,692),credit,fill='white',font_size=17);image.save(OUT/'portrait-three-views.png')
    receipt={'script_sha256':sha(__file__),'source_report_sha256':sha(OUT/'report.json'),'portrait_inputs':a,'lighting_inputs':b,
             'anchor_method':'Same-version unchanged-eye primary clay pupil anchors; explicit 768-to-1024 pixel-center scale, not beauty-glint tracking.',
             'method':'Only uniform similarity alignment or whole-frame uniform thumbnail scale, no face warp or pixel recolor.',
             'new_geometry_created_by_lookdev':False,'art_approved':False,'production_swap_allowed':False}
    (OUT/'image-review.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':main()
