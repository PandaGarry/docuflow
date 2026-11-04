"""Actual native evidence, uniformly eye-registered; no feature or color warps."""
import json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from mom_character_review_r17 import pupils
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'studio/reviews/mom-character-r18'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def register(entries,path,size=(650,780),target=((220,310),(430,310))):
 board=Image.new('RGB',(size[0]*len(entries),size[1]+115),'#1c2530');d=ImageDraw.Draw(board);records=[]
 for i,(label,source,anchors) in enumerate(entries):
  with Image.open(source) as image:
   rgba=image.convert('RGBA');bg=Image.new('RGBA',rgba.size,'#0e0b09');bg.alpha_composite(rgba);matrix=similarity(*anchors,*target);panel=bg.convert('RGB').transform(size,Image.Transform.AFFINE,inverse_affine(matrix),Image.Resampling.BICUBIC,fillcolor='#0e0b09')
  board.paste(panel,(i*size[0],45));d.text((i*size[0]+16,12),label,fill='white',font_size=20);records.append({'path':source.relative_to(ROOT).as_posix(),'sha256':sha(source),'pupils_px':anchors,'uniform_similarity':list(matrix)})
 d.text((16,size[1]+56),'Actual Cycles | uniform eye registration only | no render retouch, no automatic art approval',fill='white',font_size=16)
 d.text((16,size[1]+81),'Rain Rig (CC) Blender Foundation | studio.blender.org - CC BY4.0; acquired hair: MakeHuman CC0',fill='white',font_size=16);board.save(path);return records

def main():
 r=json.loads((BASE/'report.json').read_text())
 if r['preview_only']:raise ValueError('Expected actual full native build')
 for f in r['images']:
  if sha(ROOT/f['path'])!=f['sha256']:raise ValueError('Native frame differs '+f['path'])
 canon=ROOT/'studio/characters/mom/master/face.png';old=ROOT/'studio/reviews/mom-character-r17';receipt={'method':'Uniform eye registration, original images retained; no local feature deformation, color grading or reference projection. Compare gray anatomy independently of material.','art_approved':False,'user_approved':False,'production_swap_allowed':False}
 receipt['portrait_comparison']=register([('CANONICAL',canon,[[282,395],[489,395]]),('R17 - REJECTED',old/'portrait-front.png',pupils(old/'portrait-front.png')),('R18 - ACTUAL NATIVE',BASE/'portrait-front.png',pupils(BASE/'portrait-front.png'))],BASE/'comparison-face-hair.png')
 receipt['bare_comparison']=register([('CANONICAL',canon,[[282,395],[489,395]]),('R17 - HELD LIGHT',old/'bare-front.png',pupils(old/'bare-front.png',1.47)),('R18 - SAME LIGHT',BASE/'bare-front.png',pupils(BASE/'bare-front.png',1.47))],BASE/'comparison-held-light-face.png',(600,690),((195,260),(405,260)))
 for kind,views,dimensions in [('portrait',('front','three-quarter','profile','rear'),(480,600)),('clay',('front','three-quarter','profile'),(600,600))]:
  w,h=dimensions;board=Image.new('RGB',(w*len(views),h+90),'#1c2530');d=ImageDraw.Draw(board)
  for i,view in enumerate(views):
   with Image.open(BASE/f'{kind}-{view}.png') as image:board.paste(image.convert('RGB').resize(dimensions,Image.Resampling.LANCZOS),(i*w,38))
   d.text((i*w+14,10),'R18 '+kind.upper()+' - '+view.upper(),fill='white',font_size=18)
  d.text((16,h+55),'Actual native views; Rain CC BY4.0 / MakeHuman hair CC0. Full acting, blink and dynamics NOT approved.',fill='white',font_size=16);board.save(BASE/f'{kind}-views.png')
 (BASE/'image-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
