#!/usr/bin/env python3
"""R3 deformation experiment; not an approved production character or beauty pass."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studio.pipeline.contracts import file_hash, safe_path
from studio.authoring.mesh import Mesh, topology
from studio.authoring.refined_body import digits, hand, shoulders
from studio.tools.build_dad_rig import build as build_r2


def build(output):
    import bpy
    import bmesh
    from mathutils import Vector
    build_r2(output / '_r2')
    bpy.context.preferences.filepaths.save_version = 0
    package = json.loads((output / '_r2/package.json').read_text())
    collection = bpy.data.collections['DadBodyRig']; collection.name = 'DadBodyRefined'
    rig = bpy.data.objects['DadRig']
    receipt = {'revision': 'r3', 'scope': 'connected hands, shoulder seam/weights and rest-pose pole calibration; unreviewed'}

    def geometry(name, mesh, material, old=None):
        data = bpy.data.meshes.new(name + 'Mesh')
        data.from_pydata(mesh.vertices, [], mesh.faces); data.update()
        bm = bmesh.new(); bm.from_mesh(data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces)); bm.to_mesh(data); bm.free()
        obj = old or bpy.data.objects.new(name, data)
        if old:
            obj.data = data; obj.name = name; obj.vertex_groups.clear()
        else:
            collection.objects.link(obj); obj.parent = rig
            obj.modifiers.new('Body skin', 'ARMATURE').object = rig
        data.materials.append(material)
        for poly in data.polygons:
            poly.use_smooth = True
        groups = {b: obj.vertex_groups.new(name=b) for b in sorted({b for w in mesh.weights for b in w})}
        for i, weights in enumerate(mesh.weights):
            for bone, weight in weights.items():
                groups[bone].add([i], weight, 'REPLACE')
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE': mod.use_deform_preserve_volume = True
        receipt[name] = topology(mesh.vertices, mesh.faces)
        return obj

    # Keep r2 source and its Blender package intact; edit only this independent build.
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True); bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    for side, sign in [('R', 1), ('L', -1)]:
        for name, points in digits(sign).items():
            for j in range(3):
                bone = rig.data.edit_bones[f'{name}.{j+1:02d}.{side}']
                bone.head, bone.tail = points[j], points[j+1]
                bone.align_roll(Vector((0, 1, 0)))
        fore=rig.data.edit_bones[f'forearm.{side}']
        helper=rig.data.edit_bones.new(f'elbow_deform.{side}')
        helper.head=fore.head; helper.tail=fore.head+(fore.tail-fore.head)*.35
        helper.roll=fore.roll; helper.parent=rig.data.edit_bones[f'upper_arm.{side}']; helper.use_connect=True
    bpy.ops.object.mode_set(mode='OBJECT'); rig.select_set(False)
    for side in ('R','L'):
        copy=rig.pose.bones[f'elbow_deform.{side}'].constraints.new('COPY_ROTATION')
        copy.target=rig; copy.subtarget=f'forearm.{side}'
        copy.owner_space='WORLD'; copy.target_space='WORLD'; copy.influence=.5
    geometry('DadSweaterR3', shoulders(), bpy.data.materials['Dad warm gray knit blockout'], bpy.data.objects['DadSweaterR2'])
    for side, sign in [('R', 1), ('L', -1)]:
        mesh, tips = hand(sign)
        obj = geometry(f'DadHandR3{side}', mesh, bpy.data.materials['Dad skin'], bpy.data.objects[f'DadHandR2{side}'])
        for probe in package['fingertip_probes']:
            if probe['id'].startswith(f'finger.{side}.'):
                probe['object'] = obj.name; probe['vertex_indices'] = tips[probe['id'].split('.')[-1]]
        package['bindings'][f'clavicle.{side}.rotation'] = {'type': 'POSE_ROTATION', 'object': rig.name, 'target': f'clavicle.{side}'}
    # Anatomical rest bend defines the pole plane; default pole_angle=0 did not.
    calibration = {}
    for side, sign in [('R', 1), ('L', -1)]:
        constraint = next(c for c in rig.pose.bones[f'forearm.{side}'].constraints if c.type == 'IK')
        root, elbow, wrist = [Vector(p) for p in [(sign*.4, 0, 1.79), (sign*.67, -.015, 1.47), (sign*.75, .02, 1.11)]]
        bpy.context.view_layer.update()
        before = (rig.pose.bones[f'forearm.{side}'].head - elbow).length
        axis = (wrist-root).normalized(); projection = root + axis * (elbow-root).dot(axis)
        constraint.pole_target.location = elbow + 4 * (elbow-projection)
        constraint.iterations = 500; constraint.pole_angle = 0
        bpy.context.view_layer.update()
        actual = (rig.pose.bones[f'forearm.{side}'].head-projection).normalized()
        wanted = (elbow-projection).normalized()
        angle = math.atan2(axis.dot(actual.cross(wanted)), actual.dot(wanted))
        candidates = []
        for candidate in (0, angle, -angle, math.pi, -math.pi):
            constraint.pole_angle = candidate; bpy.context.view_layer.update()
            candidates.append(((rig.pose.bones[f'forearm.{side}'].head-elbow).length, candidate))
        error, angle = min(candidates)
        # Refine around the analytic estimate; Blender's pole convention and
        # finite IK convergence need not match the signed-angle estimate exactly.
        lo, hi = angle-.08, angle+.08
        def residual(value):
            constraint.pole_angle = value; bpy.context.view_layer.update()
            return (rig.pose.bones[f'forearm.{side}'].head-elbow).length
        for _ in range(26):
            a, b = lo+(hi-lo)/3, hi-(hi-lo)/3
            if residual(a) < residual(b): hi = b
            else: lo = a
        angle = (lo+hi)/2; error = residual(angle)
        calibration[side] = {'before_elbow_error_m': before, 'after_elbow_error_m': error, 'pole_angle_rad': angle}
        if error > .0002:
            raise ValueError(f'rest pole calibration failed: {side} {error}')
    receipt['pole_calibration'] = calibration
    # Fill the bald gaps behind r2 clumps; no claim of reference-matched hair sculpt.
    hair = bpy.data.materials['Dad beard']
    hair.diffuse_color = (.065, .030, .018, 1)
    hair.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = hair.diffuse_color
    hair.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .5
    mesh = Mesh(); previous = None
    for i in range(21):
        ring = []
        for j in range(64):
            phi = 2*math.pi*j/64
            theta = .025 + (1.16 - .37*math.sin(phi) - .025)*i/20
            ring.append(mesh.vertex((.345*math.sin(theta)*math.cos(phi), -.012+.286*math.sin(theta)*math.sin(phi), 2.28+.433*math.cos(theta)), {'head': 1}))
        if previous: mesh.bridge(previous, ring)
        else: mesh.cap(ring)
        previous = ring
    mesh.cap(previous); geometry('DadScalpR3', mesh, hair)
    # Subtle procedural cloth bump, no external textures or fake drawn folds.
    mat = bpy.data.materials['Dad warm gray knit blockout']
    tree = mat.node_tree; bsdf = tree.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = .86
    noise = tree.nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 180
    noise.inputs['Detail'].default_value = 2
    bump = tree.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .15; bump.inputs['Distance'].default_value = .001
    tree.links.new(noise.outputs['Fac'], bump.inputs['Height']); tree.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bpy.context.view_layer.update()
    receipt['bone_count'] = len(rig.data.bones)
    receipt['unweighted_vertices'] = sum(not v.groups for o in collection.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers) for v in o.data.vertices)
    receipt['hand_note'] = 'One connected closed all-quad surface per hand; this does NOT prove no self-intersection under every curl.'
    blend = output / 'dad-refined.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()), check_existing=False)
    dependencies = ['studio/tools/build_dad_blockout.py', 'studio/tools/build_dad_rig.py', 'studio/authoring/mesh.py', 'studio/authoring/refined_body.py']
    package.update(revision='r3', blend={'path': blend.relative_to(ROOT).as_posix(), 'sha256': file_hash(blend), 'collection': collection.name})
    package['provenance'] = {'authoring_script': 'studio/tools/build_dad_refined.py', 'script_sha256': file_hash(__file__), 'license': 'project-original',
                             'dependencies': [{'path': p, 'sha256': file_hash(ROOT/p)} for p in dependencies]}
    (output/'package.json').write_text(json.dumps(package, indent=2)+'\n')
    (output/'model-audit.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('DAD_REFINED_R3', output/'package.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='studio/out/dad-refined-r3')
    args = parser.parse_args(); build(safe_path(ROOT, args.output))
