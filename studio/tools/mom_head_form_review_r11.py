"""Actual R10/R11 geometry isolation. No new paint, lights or facial retouch."""
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw
from mom_head_form_review_r3 import rendered_pupils
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2];OLD=ROOT/'studio/reviews/mom-head-form-r10';OUT=ROOT/'studio/reviews/mom-head-form-r11'
CREDIT='Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. Hair/acting incomplete.'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def frames(r):return r['images']+r.get('held_portrait',{}).get('images',[])
def verify(r):
    for f in frames(r):
        if sha(ROOT/f['path'])!=f['sha256']:raise ValueError('Actual native frame changed')

def board(kind,anchors):
    if kind=='portrait':
        paths=[ROOT/'studio/reviews/mom-head-lookdev-r10/r10-warm-front.png',OUT/'portrait-front.png']
        scaled=[[[(x+.5)*4/3-.5,(y+.5)*4/3-.5] for x,y in a] for a in anchors]
    else:
        name='clay-front.png' if kind=='form' else 'candidate-front.png';paths=[OLD/name,OUT/name];scaled=anchors
    inputs=[('CANONICAL IDENTITY',ROOT/'studio/characters/mom/master/face.png',[[282,395],[489,395]]),
            ('R10 - PREVIOUS',paths[0],scaled[0]),('R11 - LOCAL FORM REVISION',paths[1],scaled[1])]
    image=Image.new('RGB',(1800,930),'#1c2530');d=ImageDraw.Draw(image);receipts=[]
    for i,(title,path,pupils) in enumerate(inputs):
        with Image.open(path) as im:
            rgba=im.convert('RGBA');bg=Image.new('RGBA',rgba.size,'#26313c');bg.alpha_composite(rgba);t=similarity(*pupils)
            panel=bg.convert('RGB').transform((600,730),Image.Transform.AFFINE,inverse_affine(t),Image.Resampling.BICUBIC,fillcolor='#26313c')
        image.paste(panel,(i*600,70));d.text((i*600+18,20),title,fill='white',font_size=23)
        receipts.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'pupil_anchors_px':pupils,'similarity':list(t)})
    caption={'form':'Matched clay: upper/lower lip balance and exterior lip-to-chin transition. No colored-material advantage.',
             'neutral':'Same R10 palette/PBR and diagnostic lights. Only authored geometry revised; not another color pass.',
             'portrait':'Same frozen R10 portrait lights, native smile 0.4 and unchanged palette/PBR. Actual native frames.'}[kind]
    for y,text in ((819,caption),(855,'Uniform pupil alignment only, no warp/repaint. Unknown reference camera/depth; no likeness score or final art acceptance.'),(891,CREDIT)):
        d.text((18,y),text,fill='white',font_size=19)
    image.save(OUT/({'form':'comparison-form.png','neutral':'comparison-identity.png','portrait':'comparison-portrait.png'}[kind]));return receipts

def detail(old,current):
    image=Image.new('RGB',(1356,1090),'#1c2530');d=ImageDraw.Draw(image);inputs=[]
    for column,rev in enumerate((10,11)):d.text((column*678+18,15),f'R{rev} - ACTUAL NEUTRAL CLAY',fill='white',font_size=24)
    for row,(view,crop) in enumerate((('front',(275,420,493,570)),('profile',(85,415,303,565)))):
        y=55+row*505;d.text((18,y),view.upper()+' / identical crop and 3x scale',fill='white',font_size=18)
        pair=[]
        for column,r in enumerate((old,current)):
            f=next(f for f in r['images'] if f['path'].endswith(f'clay-{view}.png'))
            with Image.open(ROOT/f['path']) as im:panel=im.crop(crop).resize((654,450),Image.Resampling.BICUBIC)
            image.paste(panel,(12+column*678,y+30));pair.append(f)
        if pair[0]['camera']!=pair[1]['camera']:raise ValueError('Mismatched detail camera')
        inputs.append({'view':view,'crop_px':list(crop),'uniform_scale':3,'inputs':pair})
    d.text((18,1065),CREDIT,fill='white',font_size=17);image.save(OUT/'comparison-oral-clay-detail.png');return inputs

def main():
    old=read(OLD/'report.json');current=read(OUT/'report.json');held=read(ROOT/'studio/reviews/mom-head-lookdev-r10/report.json')
    for r in (old,current,held):verify(r)
    reopen=read(OUT/'reopen/verification.json')
    if current['native_artifact']['sha256']!=reopen['native_blend_sha256']:raise ValueError('Wrong saved file reopened')
    if current['held_portrait']['lights']!=held['lights']:raise ValueError('Portrait lights changed')
    if current['portrait_smile_amount']!=held['portrait_smile_amount']:raise ValueError('Smile amount changed')
    if current['materials']['palette_srgb']!=old['materials']['palette_srgb']:raise ValueError('Palette changed')
    anchors=[]
    for path in (OLD/'clay-front.png',OUT/'clay-front.png'):
        with Image.open(path) as im:anchors.append(rendered_pupils(im))
    receipt={kind+'_inputs':board(kind,anchors) for kind in ('neutral','form','portrait')}
    receipt.update({'detail_inputs':detail(old,current),'script_sha256':sha(__file__),'new_geometry_created':True,
                    'geometry_changed_since_r10':True,'material_and_light_values_held':True,
                    'packed_exr_hashes_equal_r10':{key:old['materials']['uv_paint'][key]==current['materials']['uv_paint'][key] for key in ('albedo_exr_sha256','roughness_exr_sha256')},
                    'method':'Uniform pupil alignment only; same-version unchanged-eye clay anchors scaled by pixel-center formula for 1024 portrait frames. Detail uses same crop and 3x uniform scale.',
                    'limitations':['No calibrated reference camera/depth or likeness score.','Held lighting/palette does not certify anatomy, expression, corrective shapes or full rig rest migration.'],
                    'art_approved':False,'user_approved':False,'production_swap_allowed':False})
    (OUT/'image-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
    image=Image.new('RGB',(1920,720),'#1c2530');d=ImageDraw.Draw(image)
    for i,view in enumerate(('front','three-quarter','profile')):
        with Image.open(OUT/f'portrait-{view}.png') as im:image.paste(im.resize((640,640),Image.Resampling.BICUBIC),(640*i,40))
        d.text((640*i+18,12),'R11 HELD LIGHT - '+view.upper(),fill='white',font_size=21)
    d.text((18,692),CREDIT,fill='white',font_size=17);image.save(OUT/'portrait-three-views.png')

if __name__=='__main__':main()
