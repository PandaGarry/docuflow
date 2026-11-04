"""Actual Cycles review boards. Only uniform pupil registration or intact views."""
import hashlib,json
from pathlib import Path
from collections import deque
import numpy as np
from PIL import Image,ImageDraw,ImageOps
from mom_head_form_review_r3 import rendered_pupils
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'studio/reviews/mom-character-r15'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
CREDIT='Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. Not final art/acting approval.'
def pupils(im):
 gray=np.array(im.convert('L'));result=[]
 for px in (412,612):
  x0,y0=px-32,420;mask=gray[y0:493,x0:px+32]<32;seen=set();components=[]
  for yy,xx in zip(*np.where(mask)):
   start=(int(yy),int(xx))
   if start in seen:continue
   seen.add(start);queue=deque([start]);points=[]
   while queue:
    y,x=queue.popleft();points.append((x+x0,y+y0))
    for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
     q=(y+dy,x+dx)
     if 0<=q[0]<mask.shape[0] and 0<=q[1]<mask.shape[1] and mask[q] and q not in seen:seen.add(q);queue.append(q)
   if len(points)>25:
    center=np.mean(points,axis=0);score=len(points)/(1+np.linalg.norm(center-[px,455])**2);components.append((score,center))
  if not components:raise ValueError('Inspect actual pupil location before registration')
  center=max(components,key=lambda x:x[0])[1]
  if abs(center[0]-px)>15 or abs(center[1]-455)>22:raise ValueError('Pupil registration outside expected region')
  result.append(center.tolist())
 return result

def registered(entries,path,size=(760,1200),target=((275,410),(485,410))):
 image=Image.new('RGB',(size[0]*len(entries),size[1]+125),'#1c2530');draw=ImageDraw.Draw(image);inputs=[]
 for i,(title,p,anchors) in enumerate(entries):
  with Image.open(p) as im:
   rgba=im.convert('RGBA');bg=Image.new('RGBA',rgba.size,'#0e0b09');bg.alpha_composite(rgba);t=similarity(*anchors,*target)
   panel=bg.convert('RGB').transform(size,Image.Transform.AFFINE,inverse_affine(t),Image.Resampling.BICUBIC,fillcolor='#0e0b09')
  image.paste(panel,(i*size[0],55));draw.text((i*size[0]+18,16),title,fill='white',font_size=25)
  inputs.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'pupil_anchors_px':anchors,'uniform_similarity':list(t)})
 draw.text((18,size[1]+70),'Uniform eye-anchor alignment only. Actual native renders; different framing/expression from canonical art, no likeness score.',fill='white',font_size=18)
 draw.text((18,size[1]+101),CREDIT,fill='white',font_size=17);image.save(path);return inputs

def main():
 r=read(OUT/'report.json');v=read(OUT/'verification.json')
 if r['native_artifact']['sha256']!=v['native_sha256']:raise ValueError('Wrong native reopened')
 for f in r['images']+[v['render']]:
  if sha(ROOT/f['path'])!=f['sha256']:raise ValueError('Native render changed')
 with Image.open(OUT/'clay-front.png') as im:bare=rendered_pupils(im)
 with Image.open(OUT/'portrait-front.png') as im:full=pupils(im)
 with Image.open(ROOT/'studio/reviews/mom-head-form-r13/clay-front.png') as im:old=rendered_pupils(im)
 canon=ROOT/'studio/characters/mom/master/face.png'
 receipt={'character_inputs':registered([('CANONICAL MOM',canon,[[282,395],[489,395]]),('R15 - ACTUAL CYCLES',OUT/'portrait-front.png',full)],OUT/'comparison-character.png'),
 'bare_inputs':registered([('CANONICAL MOM',canon,[[282,395],[489,395]]),('R13 - PRIOR FACE',ROOT/'studio/reviews/mom-head-form-r13/portrait-front.png',[[ (x+.5)*4/3-.5,(y+.5)*4/3-.5] for x,y in old]),('R15 - BARE FACE',OUT/'bare-front.png',[[ (x+.5)*4/3-.5,(y+.5)*4/3-.5] for x,y in bare])],OUT/'comparison-bare-face.png',(600,730),((190,220),(410,220)))}
 image=Image.new('RGB',(1920,880),'#1c2530');d=ImageDraw.Draw(image)
 for i,view in enumerate(('front','three-quarter','profile')):
  with Image.open(OUT/f'portrait-{view}.png') as im:image.paste(im.resize((640,800),Image.Resampling.BICUBIC),(i*640,40))
  d.text((i*640+16,10),'R15 CYCLES - '+view.upper(),fill='white',font_size=21)
 d.text((18,852),CREDIT,fill='white',font_size=18);image.save(OUT/'portrait-three-views.png')
 image=Image.new('RGB',(1536,2360),'#1c2530');d=ImageDraw.Draw(image)
 for row,view in enumerate(('front','three-quarter','profile')):
  for col,folder in enumerate((ROOT/'studio/reviews/mom-head-form-r13',OUT)):
   with Image.open(folder/f'clay-{view}.png') as im:image.paste(im,(col*768,35+768*row))
 d.text((18,10),'R13 / R15 - ACTUAL BARE ANATOMY, NO HAIR HIDING',fill='white',font_size=22);d.text((18,2340),CREDIT,fill='white',font_size=17);image.save(OUT/'comparison-clay.png')
 receipt.update({'script_sha256':sha(__file__),'source_report_sha256':sha(OUT/'report.json'),'method':'Only uniform pupil similarity or intact uniformly resized actual views; no retouch, face warp, generated image or reference texture projection.','art_approved':False,'user_approved':False,'production_swap_allowed':False})
 (OUT/'image-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
