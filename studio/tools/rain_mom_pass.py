#!/usr/bin/env python3
"""Real Rain v3 -> mom A1; conservative rest-space edits, stock wardrobe.

No embedded asset scripts are executed. Source rig, weights, topology, bone rest
matrices and animation drivers are retained. This is a review candidate, not a
likeness/animation/anatomical acceptance gate. See docs/44-RAIN-MOM-STUDY.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

import rain_study as study

ROOT = study.ROOT
OUT = ROOT / 'studio/reviews/rain-mom-a1'


def gaussian(value, center, radius):
    return np.exp(-((value - center) / radius) ** 2)


def rest_field(points):
    """Smooth, symmetric, bounded world-space change; Blender meters, Z up.

    Widen waist without moving the midline or changing height. Round lower
    cheeks/chin without moving eye centers. Pull nose tip back by at most 4mm.
    Apply this SAME map to every shape-key position, not only the Basis mesh.
    Skeleton is intentionally NOT edited; pose compatibility still needs tests.
    """
    p = np.asarray(points, dtype=np.float64)
    x, y, z = p.T
    q = p.copy()
    torso = gaussian(z, .97, .14) * np.exp(-(x / .29) ** 6)
    q[:, 0] *= 1 + .14 * torso
    q[:, 1] *= 1 + .09 * torso
    cheeks = gaussian(z, 1.405, .052) * np.exp(-(x / .135) ** 8)
    chin = gaussian(z, 1.35, .027) * np.exp(-(x / .105) ** 8)
    q[:, 0] += x * (.09 * cheeks + .075 * chin)
    front = .5 * (1 + np.tanh((-y - .055) / .015))
    q[:, 1] += .004 * gaussian(x, 0, .020) * gaussian(z, 1.426, .020) * front
    return q


def point_array(data):
    p = np.empty(len(data) * 3, dtype=np.float64)
    data.foreach_get('co', p)
    return p.reshape(-1, 3)


def transform_points(points, matrix):
    m = np.array(matrix, dtype=np.float64)
    return points @ m[:3, :3].T + m[:3, 3]


def change_meshes(bpy):
    records = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not obj.name.startswith('GEO-rain-'):
            continue
        world = obj.matrix_world.copy()
        inv = world.inverted()
        keys = obj.data.shape_keys
        blocks = [k.data for k in keys.key_blocks] if keys else [obj.data.vertices]
        maximum = 0.0
        for data in blocks:
            original = transform_points(point_array(data), world)
            changed = rest_field(original)
            if obj.name == 'GEO-rain-eyebrows':
                # Keep the source arch, reduce the solid brow's vertical bulk.
                centerline = np.polyval(np.polyfit(np.abs(original[:, 0]), original[:, 2], 2), np.abs(original[:, 0]))
                changed[:, 2] = centerline + .58 * (original[:, 2] - centerline)
            maximum = max(maximum, float(np.linalg.norm(changed - original, axis=1).max()))
            data.foreach_set('co', transform_points(changed, inv).ravel())
        if keys:
            obj.data.vertices.foreach_set('co', point_array(keys.key_blocks[0].data).ravel())
            keys.update_tag()
        obj.data.update()
        records.append({'object': obj.name, 'vertices': len(obj.data.vertices),
                        'shape_key_blocks_transformed': len(blocks) if keys else 0,
                        'maximum_rest_displacement_m': maximum})
    bpy.context.view_layer.update()
    return records


def linear_color(hex_value):
    channels = [int(hex_value[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels) + (1,)


def change_materials(bpy):
    records = []
    for name in ('MAT-rain.body', 'MAT-rain.hands'):
        mat = bpy.data.materials[name]
        tree = mat.node_tree
        socket = tree.nodes['Principled BSDF'].inputs['Base Color']
        if len(socket.links) != 1:
            raise ValueError(f'{name}: unexpected source shader graph; stop for review')
        source = socket.links[0].from_socket
        hsv = tree.nodes.new('ShaderNodeHueSaturation')
        hsv.name = 'Docuflow A1 skin lift'
        hsv.inputs['Value'].default_value = 1.45
        hsv.inputs['Saturation'].default_value = .95
        tree.links.new(source, hsv.inputs['Color'])
        tint = tree.nodes.new('ShaderNodeMixRGB')
        tint.name = 'Docuflow A1 peach target'
        tint.blend_type = 'MIX'
        tint.inputs[0].default_value = .10
        tint.inputs[2].default_value = linear_color('#E8B48F')
        tree.links.new(hsv.outputs['Color'], tint.inputs[1])
        tree.links.new(tint.outputs[0], socket)
        records.append({'material': name, 'skin_target_srgb': '#E8B48F',
                        'value_multiplier': 1.45, 'saturation_multiplier': .95,
                        'target_mix': .10, 'note': 'Albedo adjustment, not an exact displayed pixel-color match. Texture and lip variation retained.'})
    mat = bpy.data.materials['MAT-rain.eyebrows']
    socket = mat.node_tree.nodes['Principled BSDF'].inputs['Base Color']
    for link in list(socket.links):
        mat.node_tree.links.remove(link)
    socket.default_value = linear_color('#88684D')
    records.append({'material': mat.name, 'base_color_srgb': '#88684D'})
    return records


def invalid_drivers(bpy):
    result = []
    for collection_name in ('objects', 'shape_keys', 'materials', 'node_groups'):
        for block in getattr(bpy.data, collection_name):
            animation = block.animation_data
            if animation:
                for curve in animation.drivers:
                    if not curve.driver.is_valid:
                        result.append(f'{collection_name}:{block.name}:{curve.data_path}:{curve.array_index}')
    return sorted(result)


def rig_signature(rig):
    content = []
    for bone in rig.data.bones:
        content.append((bone.name, bone.parent.name if bone.parent else None,
                        list(bone.head_local), list(bone.tail_local),
                        [list(row) for row in bone.matrix_local]))
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def head_geometry(bpy):
    obj = bpy.data.objects['GEO-rain-head']
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return transform_points(point_array(mesh.vertices), evaluated.matrix_world)
    finally:
        evaluated.to_mesh_clear()


def driver_metadata(bpy):
    keys = bpy.data.objects['GEO-rain-head'].data.shape_keys
    return [{'path': f.data_path, 'expression': f.driver.expression,
             'variables': [{'name': v.name, 'type': v.type,
                            'targets': [{'bone': t.bone_target, 'transform': t.transform_type,
                                         'space': t.transform_space, 'data_path': t.data_path} for t in v.targets]} for v in f.driver.variables]}
            for f in keys.animation_data.drivers]


def drive_key(bpy, rig, key_name, target_value, prefix):
    """Exercise existing ACT control -> existing driver -> existing shape key.

    Read actual driver variables; do not replace/mute drivers or set driven key
    values directly. Search the documented actuator range, recording responses.
    This calibrates a diagnostic pose, NOT a strain/quality threshold.
    """
    keys = bpy.data.objects['GEO-rain-head'].data.shape_keys
    curve = next(f for f in keys.animation_data.drivers if f.data_path == f'key_blocks["{key_name}"].value')
    candidates = []
    for var in curve.driver.variables:
        for target in var.targets:
            if target.id == rig and target.bone_target.startswith(prefix) and target.transform_type.startswith('LOC_'):
                candidates.append((target.bone_target, 'XYZ'.index(target.transform_type[-1])))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        return {'key': key_name, 'status': 'blocked-no-supported-native-actuator', 'expression': curve.driver.expression}
    trials = []
    baseline = {name: rig.pose.bones[name].location.copy() for name, _ in candidates}
    for name, axis in candidates:
        bone = rig.pose.bones[name]
        for value in (-1, -.5, -.1, 0, .1, .25, .5, .75, 1):
            bone.location = baseline[name]
            bone.location[axis] = value
            rig.update_tag()
            bpy.context.view_layer.update()
            response = float(keys.key_blocks[key_name].value)
            trials.append({'bone': name, 'axis': axis, 'input': value, 'key_value': response})
        bone.location = baseline[name]
        rig.update_tag()
        bpy.context.view_layer.update()
    best = min(trials, key=lambda t: (abs(t['key_value'] - target_value), abs(t['input'])))
    bone = rig.pose.bones[best['bone']]
    bone.location[best['axis']] = best['input']
    rig.update_tag()
    bpy.context.view_layer.update()
    actual = float(keys.key_blocks[key_name].value)
    return {'key': key_name, 'status': 'actuated' if abs(actual-target_value) < .15 else 'partial-actuation',
            'target': target_value, 'actual_key_value': actual, 'selected': best, 'trials': trials,
            'driver_expression': curve.driver.expression}


def build_board():
    from PIL import Image, ImageDraw
    canvas = Image.new('RGB', (1536, 1640), '#1c2530')
    draw = ImageDraw.Draw(canvas)
    for col, label in enumerate(('ORIGINAL RAIN v3', 'MOM STUDY A1 - NOT APPROVED')):
        draw.text((col*768+24, 12), label, fill='white', font_size=24)
    for row, view in enumerate(('full', 'face')):
        for col, directory in enumerate((ROOT/'studio/reviews/rain-study', OUT)):
            name = f'source-{view}.png' if col == 0 else f'candidate-{view}.png'
            with Image.open(directory/name) as image:
                canvas.paste(image, (col*768, 48+row*768))
    draw.text((24, 1596), 'Same native camera/light. Stock clothes + hair retained. Rain Rig (CC) Blender Foundation | studio.blender.org', fill='white', font_size=18)
    canvas.save(OUT/'comparison.png')


def main():
    import bpy
    OUT.mkdir(parents=True, exist_ok=True)
    source = study.acquire(ROOT/'.cache/rain-v3')
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()), use_scripts=False)
    bpy.context.view_layer.update()
    rig = bpy.data.objects['RIG-rain']
    signature_before = rig_signature(rig)
    original_basis = {b.name: b.matrix_basis.copy() for b in rig.pose.bones}
    source_invalid = invalid_drivers(bpy)
    topology = {o.name: (len(o.data.vertices), len(o.data.polygons)) for o in bpy.data.objects if o.type == 'MESH'}
    receipt = {'revision': 'rain-mom-a1', 'source_blend_sha256': study.sha(source),
               'script_sha256': study.sha(__file__), 'render_helper_sha256': study.sha(study.__file__),
               'reference_sha256': study.sha(ROOT/'studio/characters/mom/master/turnaround.png'),
               'credit': 'Rain Rig (CC) Blender Foundation | studio.blender.org', 'license': 'CC-BY-4.0',
               'changes': 'A1 skin color lift, softer waist/cheeks/chin/nose/brows. Original wardrobe/haircut retained.',
               'blender_version': bpy.app.version_string, 'embedded_python_executed': False,
               'head_shape_key_drivers': driver_metadata(bpy),
               'rig_rest_signature_before': signature_before, 'source_invalid_drivers': source_invalid,
               'meshes': change_meshes(bpy), 'materials': change_materials(bpy),
               'art_approved': False, 'production_swap_allowed': False}
    scene, camera = study.stage(bpy)
    neutral = head_geometry(bpy)
    images = [study.render(bpy, scene, camera, OUT/'candidate-full.png', (0,-4,1.05), (0,0,.85), 1.95),
              study.render(bpy, scene, camera, OUT/'candidate-face.png', (0,-4,1.5), (0,0,1.45), .60),
              study.render(bpy, scene, camera, OUT/'candidate-three-quarter.png', (2.2,-4,1.5), (0,0,1.45), .60)]
    expressions = []
    for label, names, target, prefix in [('blink', ('EyelidsClose.L','EyelidsClose.R'), 1.0, 'ACT-Eyelid'),
                                         ('smile', ('Smile.L','Smile.R'), .5, 'ACT-Lips')]:
        for name, matrix in original_basis.items():
            rig.pose.bones[name].matrix_basis = matrix
        rig.update_tag()
        bpy.context.view_layer.update()
        controls = [drive_key(bpy, rig, name, target, prefix) for name in names]
        posed = head_geometry(bpy)
        expressions.append({'expression': label, 'controls': controls,
                            'finite_head_vertices': bool(np.isfinite(posed).all()),
                            'head_displacement_max_m': float(np.linalg.norm(posed-neutral, axis=1).max()),
                            'scope': 'Native actuator smoke test + image for review, not full animation or anatomical certification.'})
        images.append(study.render(bpy, scene, camera, OUT/f'candidate-{label}.png', (0,-4,1.5), (0,0,1.45), .60))
    for name, matrix in original_basis.items():
        rig.pose.bones[name].matrix_basis = matrix
    rig.update_tag()
    bpy.context.view_layer.update()
    receipt.update({'images': images, 'expressions': expressions,
                    'rig_rest_signature_after': rig_signature(rig),
                    'topology_unchanged': topology == {o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'},
                    'candidate_invalid_drivers': invalid_drivers(bpy),
                    'pose_restored_max_head_error_m': float(np.linalg.norm(head_geometry(bpy)-neutral,axis=1).max())})
    receipt['new_invalid_drivers'] = sorted(set(receipt['candidate_invalid_drivers'])-set(source_invalid))
    # Fail before publication if the bounded edit corrupts rest topology/rig.
    if not receipt['topology_unchanged'] or receipt['rig_rest_signature_after'] != signature_before:
        raise ValueError('Unexpected rig/topology modification')
    if not all(e['finite_head_vertices'] for e in expressions):
        raise ValueError('Nonfinite evaluated expression geometry')
    text = bpy.data.texts.new('DOCUFLOW_A1_CHANGES.txt')
    text.write(receipt['credit']+'\nCC BY 4.0 https://creativecommons.org/licenses/by/4.0/\n'+receipt['changes']+'\nExperimental, not approved. Embedded asset Python was NOT executed during build.\n')
    bpy.ops.file.pack_all()
    native = ROOT/'.cache/rain-v3/rain-mom-a1.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()), compress=True)
    receipt['native_artifact'] = {'filename': native.name, 'sha256': study.sha(native), 'textures_packed': True,
                                  'storage': 'GitHub Actions artifact; reconstruct with this script. Not committed to Git.'}
    study.write(OUT/'report.json', receipt)
    build_board()


if __name__ == '__main__':
    main()
