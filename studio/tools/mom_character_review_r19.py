"""Unretouched actual physical-hair comparison; unchanged face reuse explicit."""
import json
from pathlib import Path
from PIL import Image,ImageDraw
from mom_character_review_r18 import register,sha
from mom_character_review_r17 import pupils
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-character-r19'

def main():
 r=json.loads((OUT/'report.json').read_text());v=json.loads((OUT/'verification.json').read_text())
 for f in r['images']+[v['render']]:
  if sha(ROOT/f['path'])!=f['sha256']:raise ValueError('Actual native frame changed '+f['path'])
 canon=ROOT/'studio/characters/mom/master/face.png';old=ROOT/'studio/reviews/mom-character-r18';entries=[('CANONICAL',canon,[[282,395],[489,395]]),('R18 - REJECTED RIBBONS',old/'portrait-front.png',pupils(old/'portrait-front.png')),('R19 - ACTUAL FINE HAIR',OUT/'portrait-front.png',pupils(OUT/'portrait-front.png'))]
 record={'review_script_sha256':sha(__file__),'method':'Intact actual native frames; uniform eye registration only. No local feature/skin/hair image warp or color retouch. R19 original face/eyes unchanged from R18; bare/clay frames explicitly reused.','comparison':register(entries,OUT/'comparison-face-hair.png'),'art_approved':False,'user_approved':False,'production_swap_allowed':False};views=('front','three-quarter','profile','rear');w,h=480,600;board=Image.new('RGB',(w*4,h+90),'#1c2530');d=ImageDraw.Draw(board)
 for i,view in enumerate(views):
  with Image.open(OUT/f'portrait-{view}.png') as im:board.paste(im.convert('RGB').resize((w,h),Image.Resampling.LANCZOS),(i*w,38))
  d.text((i*w+14,10),'R19 NATIVE - '+view.upper(),fill='white',font_size=19)
 d.text((16,h+54),'Actual Cycles, real fine HAIR curves. Original R18 face/rig retained; acting/blink/dynamics NOT approved.',fill='white',font_size=16);d.text((16,h+74),'Rain Rig (CC) Blender Foundation | studio.blender.org - CC BY4.0 / acquired growth-guide data MakeHuman CC0',fill='white',font_size=15);board.save(OUT/'portrait-views.png');(OUT/'image-review.json').write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':main()
