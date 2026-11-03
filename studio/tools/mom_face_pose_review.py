"""Read-only native pose comparison; no warp, retouch or geometry editing."""
from pathlib import Path
import hashlib
import json
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studio/reviews/mom-head-form-r3'


def main():
    report=json.loads((OUT/'report.json').read_text())
    verify=json.loads((OUT/'reopen/verification.json').read_text())
    entries=report['images']+report['paired_source_diagnostics']['images']+[verify['warm_smile_render']]
    for entry in entries:
        if hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Native pose image changed')
    layouts=[('comparison-smile.png',[
        ('R2 - MIXED ACTUATOR AXES',ROOT/'studio/reviews/mom-head-form-r2/candidate-smile.png'),
        ('R3 - BALANCED BILATERAL POSE',OUT/'reopen/warm-smile.png')]),
        ('source-smile-diagnosis.png',[
        ('ORIGINAL RAIN - MIXED AXES',OUT/'source-legacy-mixed-smile.png'),
        ('SAME ORIGINAL RAIN - COMMON Z',OUT/'source-paired-z-smile.png')])]
    for filename,panels in layouts:
        board=Image.new('RGB',(1536,850),'#1c2530');draw=ImageDraw.Draw(board)
        for column,(title,path) in enumerate(panels):
            draw.text((column*768+18,12),title,fill='white',font_size=25)
            with Image.open(path) as image:board.paste(image,(column*768,50))
        draw.text((18,824),'Actual native frames / same camera. Limited pose test, not full acting approval. Rain Rig (CC) Blender Foundation',fill='white',font_size=18)
        board.save(OUT/filename)


if __name__=='__main__':main()
