"""Subprocess-only bpy entry point. Never imports bpy in the coordinator."""
from __future__ import annotations

import argparse
import json
import importlib.metadata
import platform
from pathlib import Path
import resource
import time

from ..contracts import ROOT, file_hash, load_bundle
from ..timeline import apply_controls, bind_controls, evaluate
from .rig_probe import build_scene


def _write(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def _overlay(path, version):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.open(path).convert('RGB')
    width, height = image.size
    scale = width / 1920
    font_path = ROOT / 'studio/fonts/Nunito-700.ttf'
    font = lambda n: ImageFont.truetype(str(font_path), max(8, round(n * scale)))
    draw = ImageDraw.Draw(image)
    margin = round(68 * scale)
    draw.text((margin, round(40 * scale)), 'Технический тест ядра', font=font(43), fill='#18342e')
    draw.text((margin, round(99 * scale)),
              f'Blender {version} · Cycles CPU · {width} × {height}', font=font(25), fill='#49655b')
    draw.text((margin, height - round(105 * scale)), 'IK + skinning + shape key', font=font(31), fill='#18342e')
    draw.text((margin, height - round(58 * scale)), 'Не персонаж семьи. Звук — тестовый тон.',
              font=font(24), fill='#49655b')
    image.save(path)


def run(inputs, output):
    import bpy

    started = time.perf_counter()
    bundle = load_bundle(inputs)
    project, shot, rig = (bundle[k] for k in ('project', 'shot', 'rig'))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frames = output / 'frames'
    frames.mkdir(exist_ok=True)
    scene = build_scene(bpy, project)
    start, end = shot['frame_range']
    scene.frame_start, scene.frame_end = start, end - 1
    bindings = bind_controls(bpy, rig)
    # Export a genuinely playable .blend, in addition to the canonical JSON tracks.
    for track in shot['tracks']:
        typ, target = bindings[track['control']]
        for key in track['keys']:
            apply_controls(bindings, {track['control']: key['value']})
            target.keyframe_insert(data_path='location' if typ == 'OBJECT_LOCATION' else 'value', frame=key['frame'])
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = 'LINEAR'
    scene.frame_set(start)
    apply_controls(bindings, evaluate(shot, start))
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str((output / 'scene.blend').resolve()), check_existing=False)
    measurements = []
    arm = bpy.data.objects['Rig']
    for frame in range(start, end):
        tick = time.perf_counter()
        scene.frame_set(frame)
        apply_controls(bindings, evaluate(shot, frame))
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        pose_arm = arm.evaluated_get(deps)
        wrist = arm.matrix_world @ pose_arm.pose.bones['forearm.R'].tail
        target = bpy.data.objects['HandTarget'].matrix_world.translation
        record = {'frame': frame, 'ik_error_m': (wrist - target).length,
                  'jaw_control': bpy.data.objects['Jaw'].data.shape_keys.key_blocks['Open'].value,
                  'bone_relative_length_error': max(abs(pose_arm.pose.bones[b.name].length / b.length - 1)
                                                    for b in arm.data.bones)}
        for name, metric in [('SkinnedArm', 'arm_vertex_m'), ('Jaw', 'jaw_centroid_m')]:
            obj = bpy.data.objects[name].evaluated_get(deps)
            mesh = obj.to_mesh()
            if name == 'SkinnedArm':
                point = obj.matrix_world @ mesh.vertices[-1].co
            else:
                from mathutils import Vector
                point = obj.matrix_world @ (sum((v.co for v in mesh.vertices), Vector()) / len(mesh.vertices))
            record[metric] = list(point)
            obj.to_mesh_clear()
        # Output sequence always starts at zero; source frame can be a subrange.
        path = frames / f'{frame - start:06d}.png'
        scene.render.filepath = str(path.resolve())
        bpy.ops.render.render(write_still=True)
        record['raw_png_sha256'] = file_hash(path)
        _overlay(path, bpy.app.version_string)
        record['seconds'] = round(time.perf_counter() - tick, 4)
        measurements.append(record)
        print(f'PROBE_FRAME {frame - start + 1}/{end - start} {record["seconds"]:.2f}s', flush=True)
        _write(output / 'progress.json', {'completed': len(measurements), 'expected': end - start})
    package = Path(importlib.metadata.distribution('bpy').locate_file('bpy'))
    ocio = package / f'{bpy.app.version[0]}.{bpy.app.version[1]}/datafiles/colormanagement/config.ocio'
    report = {'worker_exit_scope': 'successful_worker_completion',
              'blender': bpy.app.version_string,
              'blender_build_hash': bpy.app.build_hash.decode(),
              'background': bpy.app.background, 'python': platform.python_version(),
              'engine': scene.render.engine, 'device': scene.cycles.device,
              'samples': scene.cycles.samples, 'denoise': scene.cycles.use_denoising,
              'color_management': {'view_transform': scene.view_settings.view_transform,
                                   'ocio_sha256': file_hash(ocio)},
              'measurements': measurements, 'wall_seconds': round(time.perf_counter() - started, 4),
              'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
    _write(output / 'worker-report.json', report)
    print('PROBE_WORKER_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.inputs, args.output)
