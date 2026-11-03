#!/usr/bin/env python3
"""Like-for-like r2/r3 still review plus a native hand close-up; not art approval."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.pipeline.contracts import file_hash,load_json
from studio.pipeline.packages import validate_bundle,append_package,bind,apply
from studio.pipeline.run_probe import write_json


def run():
    import bpy
    from studio.pipeline.backends.package_worker import stage
    from PIL import Image,ImageDraw,ImageFont
    output=ROOT/'studio/out/dad-r3-review';output.mkdir(exist_ok=True,parents=True)
    metadata=[]
    for revision,filename,package,closeup in [
        ('r2','r2-neutral.png','studio/out/dad-rig-r2/package.json',False),
        ('r3','hand-closeup.png','studio/out/dad-refined-r3/package.json',True)]:
        a=load_json(ROOT/package);p=load_json(ROOT/'studio/production/dad-refined/project.json')
        p['resolution']=[768,576];p['render']['samples']=16
        p['camera']={'position':[2.5,7,2.9],'target':[.05,0,1.42],'ortho_scale':4.6}
        if closeup:p['camera']={'position':[1.25,3,1.22],'target':[.76,.03,1.025],'ortho_scale':.5}
        s={'schema_version':2,'kind':'shot','shot_id':'static-review','project_id':p['project_id'],'asset_id':a['asset_id'],'asset_revision':revision,
           'frame_range':[0,2],'tracks':[{'control':'head.rotation','keys':[{'frame':0,'value':[0,0,0]},{'frame':1,'value':[0,0,0]}]}]}
        validate_bundle(p,a,s)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        objects=append_package(bpy,a);bindings=bind(objects,a)
        if closeup:
            apply(bindings,{f'finger.R.{n}.{j:02d}':[v,0,0] for n in ('index','middle','ring','pinky','thumb') for j,v in enumerate((.6,.8,.5),1)})
        bpy.context.view_layer.update();scene=stage(bpy,p)
        scene.render.filepath=str(output/filename);bpy.ops.render.render(write_still=True)
        metadata.append({'revision':revision,'blend_sha256':a['blend']['sha256'],'path':(output/filename).relative_to(ROOT).as_posix(),'sha256':file_hash(output/filename),'project':p})
    board=Image.new('RGB',(1536,656),'#f0f1eb');draw=ImageDraw.Draw(board)
    font=ImageFont.truetype(str(ROOT/'studio/fonts/Nunito-700.ttf'),24)
    draw.text((28,18),'ДО: r2 — исходный технический блокинг',font=font,fill='#253c32')
    draw.text((796,18),'ПОСЛЕ: r3 — тело и кисти, не финальный арт',font=font,fill='#253c32')
    for x,name in [(0,'r2-neutral.png'),(768,'neutral.png')]:
        with Image.open(output/name) as image:board.paste(image,(x,64))
    board.save(output/'comparison.png')
    metadata.append({'path':(output/'comparison.png').relative_to(ROOT).as_posix(),'sha256':file_hash(output/'comparison.png'),
                     'r3_neutral_sha256':file_hash(output/'neutral.png'),'note':'Same native camera, lights, resolution, samples; no face/beauty approval implied.'})
    write_json(ROOT/'studio/production/dad-r3-visual-review.json',{'scope':'native stills; review, not approval','recipe_sha256':file_hash(__file__),'renders':metadata})


if __name__=='__main__':run()
