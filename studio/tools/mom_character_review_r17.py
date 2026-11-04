"""Native evidence boards: uniform pupil registration, no feature warping."""
import json,hashlib
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from mom_form_review import similarity,inverse_affine
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'studio/reviews/mom-character-r17'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def pupils(path,target_z=1.455,scale=.48):
 with Image.open(path) as im:gray=np.array(im.convert('L'));w,h=im.size
 up=np.array([1.5-target_z,4]);up/=np.linalg.norm(up);py=h/2-(-.145*up[0]+(1.47326-target_z)*up[1])/scale*h;result=[]
 for px in (w/2-.046632/scale*h,w/2+.046632/scale*h):
  x0=max(0,int(px-h*.045));x1=min(w,int(px+h*.045));y0=max(0,int(py-h*.045));y1=min(h,int(py+h*.045));mask=gray[y0:y1,x0:x1]<40;seen=set();candidates=[]
  for yy,xx in zip(*np.where(mask)):
   start=(int(yy),int(xx))
   if start in seen:continue
   seen.add(start);queue=deque([start]);points=[]
   while queue:
    y,x=queue.popleft();points.append((x+x0,y+y0))
    for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
     q=(y+dy,x+dx)
     if 0<=q[0]<mask.shape[0] and 0<=q[1]<mask.shape[1] and mask[q] and q not in seen:seen.add(q);queue.append(q)
   if len(points)>20:
    p=np.array(points);c=p.mean(0);aspect=np.ptp(p[:,0])/max(1,np.ptp(p[:,1]));score=len(points)/(1+np.linalg.norm(c-[px,py])**2/(.015*h)**2)
    if .5<aspect<1.8:candidates.append((score,c))
  if not candidates:raise ValueError('Inspect native pupils before registering '+str(path))
  result.append(max(candidates,key=lambda a:a[0])[1].tolist())
 return result

def register(entries,output,size=(700,870),target=((245,400),(455,400))):
 board=Image.new('RGB',(size[0]*len(entries),size[1]+110),'#1c2530');d=ImageDraw.Draw(board);inputs=[]
 for i,(label,path,anchors) in enumerate(entries):
  with Image.open(path) as im:
   rgba=im.convert('RGBA');bg=Image.new('RGBA',rgba.size,'#0e0b09');bg.alpha_composite(rgba);transform=similarity(*anchors,*target);panel=bg.convert('RGB').transform(size,Image.Transform.AFFINE,inverse_affine(transform),Image.Resampling.BICUBIC,fillcolor='#0e0b09')
  board.paste(panel,(i*size[0],45));d.text((i*size[0]+18,13),label,fill='white',font_size=22);inputs.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'pupils_px':anchors,'uniform_similarity':list(transform)})
 d.text((16,size[1]+55),'Actual Cycles | uniform eye alignment only | face/hair focus; R16 clothes unchanged',fill='white',font_size=17);d.text((16,size[1]+81),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. No art/acting approval.',fill='white',font_size=16);board.save(output)
 return inputs

def main(preview=False):
 out=BASE/'preview-3' if preview else BASE;r=json.loads((out/'report.json').read_text())
 for f in r['images']:
  if sha(ROOT/f['path'])!=f['sha256']:raise ValueError('Native frame modified')
 canon=ROOT/'studio/characters/mom/master/face.png';comparison_output=out/'comparison-face-hair.png'
 receipt={'comparison_inputs':register([('CANONICAL MOM',canon,[[282,395],[489,395]]),('R17 - ACTUAL CYCLES',out/'portrait-front.png',pupils(out/'portrait-front.png'))],comparison_output),'method':'Uniform eye alignment only, intact native frame. Head/hair crop; clothes explicitly unchanged and unapproved. No canonical texture projection, no render retouch.','art_approved':False,'user_approved':False,'production_swap_allowed':False}
 bare_output=out/'comparison-bare-face.png';receipt['bare_inputs']=register([('CANONICAL MOM',canon,[[282,395],[489,395]]),('R17 - UNOBSCURED FACE',out/'bare-front.png',pupils(out/'bare-front.png',1.47))],bare_output,(650,710),((220,260),(430,260)))
 views=('front','three-quarter') if preview else ('front','three-quarter','profile');board=Image.new('RGB',(512*len(views),700),'#1c2530');draw=ImageDraw.Draw(board)
 for i,v in enumerate(views):
  with Image.open(out/f'portrait-{v}.png') as im:board.paste(im.resize((512,640),Image.Resampling.LANCZOS),(512*i,35))
  draw.text((512*i+16,10),'R17 NATIVE - '+v.upper(),fill='white',font_size=20)
 draw.text((16,680),'Actual views, no retouch. Clothes retained from R16; acting/dynamics not accepted.',fill='white',font_size=16);board.save(out/'portrait-views.png')
 (out/'image-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':
 import sys
 main('--preview' in sys.argv)
