#!/usr/bin/env python3
"""Archive exact native PNGs and compose a labelled board, not a beauty retouch."""
from pathlib import Path
import json
import shutil
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.pipeline.contracts import file_hash, load_json


def build():
    from PIL import Image, ImageDraw, ImageFont
    source=ROOT/'studio/out/dad-r4-review';out=ROOT/'studio/reviews/dad-r4'
    out.mkdir(parents=True,exist_ok=True)
    report=load_json(source/'render-report.json');entries=[]
    for item in report['renders']:
        name=item['view'];path=source/f'{name}.png'
        if file_hash(path)!=item['png_sha256']:raise ValueError('source PNG hash mismatch')
        shutil.copyfile(path,out/path.name)
        entries.append({'view':name,'path':(out/path.name).relative_to(ROOT).as_posix(),
                        'sha256':file_hash(out/path.name),'native_source':path.relative_to(ROOT).as_posix()})
    board=Image.new('RGB',(2192,1152),'#eef1f3');draw=ImageDraw.Draw(board)
    def text(x,y,value,size=20,bold=False):
        font=ImageFont.truetype(str(ROOT/'studio/fonts'/('Nunito-800.ttf' if bold else 'Nunito-400.ttf')),size)
        draw.text((x,y),value,fill='#243342',font=font)
    text(32,17,'ПАПА / LOOK-DEVELOPMENT R4',34,True)
    text(32,65,'Контрольные кадры модели. Художественная и анатомическая приёмка не пройдены.',22)
    y=142
    text(32,108,'ПОРТРЕТ · ¾',18,True)
    text(1016,108,'ПРОПОРЦИИ · ПОЛНЫЙ РОСТ',18,True)
    text(1680,108,'КИСТЬ · РАСКРЫТАЯ / СГИБАНИЕ',18,True)
    with Image.open(out/'hero.png') as im:board.paste(im.convert('RGB').resize((960,960),Image.Resampling.LANCZOS),(32,y))
    with Image.open(out/'full.png') as im:
        # Horizontal display crop only; the raw square original is archived too.
        im=im.convert('RGB').resize((960,960),Image.Resampling.LANCZOS)
        board.paste(im.crop((160,0,800,960)),(1016,y))
    for name,top in [('hand_open',y),('hand_curl',y+486)]:
        with Image.open(out/f'{name}.png') as im:
            board.paste(im.convert('RGB').resize((474,474),Image.Resampling.LANCZOS),(1680,top))
    text(32,1111,'Blender 4.5 · Cycles / AgX · исходники 1024×1024, 48 samples · без дорисовки и ретуши',20)
    path=out/'review-board.jpg';board.save(path,quality=96,subsampling=0)
    record={'scope':'Exact native PNG archive plus labelled display board. NOT art/anatomy approval.',
            'sources':entries,'render_report_sha256':file_hash(source/'render-report.json'),
            'board':{'path':path.relative_to(ROOT).as_posix(),'sha256':file_hash(path),'dimensions':list(board.size),
                     'operations':'Labels, Lanczos display resizing, horizontal crop of full view only. Raw originals unchanged.'},
            'composer_sha256':file_hash(__file__)}
    (out/'manifest.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
    print(path)


if __name__=='__main__':build()
