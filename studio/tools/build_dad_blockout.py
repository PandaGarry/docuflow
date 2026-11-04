#!/usr/bin/env python3
"""Author a reproducible UNREVIEWED 3D blockout, not a production family model.

Run with the isolated bpy interpreter. Geometry is original procedural work;
reference identity: broad build, brown beard/hair, gray sweater, dark jeans.
"""
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


def build(output):
    import bpy
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.data.collections.new('DadBlockout')
    bpy.context.scene.collection.children.link(collection)

    def move(obj):
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        collection.objects.link(obj)
        return obj

    def mat(name, color):
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*color, 1)
        m.use_nodes = True
        bsdf = m.node_tree.nodes['Principled BSDF']
        bsdf.inputs['Base Color'].default_value = (*color, 1)
        bsdf.inputs['Roughness'].default_value = .65
        return m

    skin = mat('Dad skin', (.72, .43, .28))
    hair = mat('Dad beard', (.074, .038, .024))
    sweater = mat('Dad warm gray knit blockout', (.52, .50, .46))
    jeans = mat('Dad dark denim', (.045, .055, .073))
    shoe = mat('Dad brown shoes', (.095, .058, .036))
    whites = mat('Eye white', (.89, .86, .78))
    iris = mat('Brown iris', (.12, .057, .022))
    black = mat('Pupil and mouth', (.012, .008, .006))
    lip = mat('Lip blockout', (.44, .19, .13))

    def ellipsoid(name, loc, scale, material, segments=32):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=20, location=loc)
        obj = move(bpy.context.object)
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material)
        for p in obj.data.polygons:
            p.use_smooth = True
        return obj

    headparts = []
    ellipsoid('DadSweater', (0, 0, 1.43), (.43, .265, .49), sweater)
    ellipsoid('DadShoulders', (0, 0, 1.72), (.435, .25, .19), sweater)
    ellipsoid('DadHem', (0, .005, 1.08), (.365, .245, .10), sweater)
    ellipsoid('DadNeck', (0, 0, 1.94), (.15, .15, .16), skin)
    bpy.ops.mesh.primitive_torus_add(major_radius=.145, minor_radius=.025, location=(0, 0, 1.90))
    collar = move(bpy.context.object)
    collar.name = 'DadCollar'
    collar.data.materials.append(sweater)
    headparts.append(ellipsoid('DadHead', (0, 0, 2.28), (.34, .28, .42), skin))
    for sign in (-1, 1):
        headparts.append(ellipsoid('DadEar', (sign*.345, 0, 2.30), (.068, .065, .11), skin))
        headparts.append(ellipsoid('DadInnerEar', (sign*.372, .039, 2.30), (.028, .024, .065), lip))
    headparts.append(ellipsoid('DadBeard', (0, .035, 2.065), (.305, .255, .215), hair))
    # Skin mouth island gives a visible opening without claiming anatomical lipsync.
    headparts.append(ellipsoid('DadMouthIsland', (0, .284, 2.13), (.155, .025, .083), skin))
    mouth = ellipsoid('DadMouth', (0, .31, 2.125), (.106, .012, .008), black)
    mouth.shape_key_add(name='Basis')
    opened = mouth.shape_key_add(name='Open')
    for v in opened.data:
        v.co.z = v.co.z * 7 - .025
    headparts.append(mouth)
    for x in (-.083, .083):
        moustache = ellipsoid('DadMoustache', (x, .301, 2.18), (.095, .036, .025), hair)
        moustache.rotation_euler.y = .14 if x < 0 else -.14
        headparts.append(moustache)
    headparts.append(ellipsoid('DadNose', (0, .283, 2.27), (.073, .10, .082), skin))
    headparts.append(ellipsoid('DadHairCap', (0, -.025, 2.58), (.325, .265, .16), hair))
    for i in range(7):
        x = -.23 + i*.075
        lock = ellipsoid('DadHairLock', (x, .035, 2.665+(.05 if i < 4 else 0)), (.068, .15, .105), hair, 20)
        lock.rotation_euler.y = -.40
        headparts.append(lock)
    bindings = {}
    for side, sign in [('L', -1), ('R', 1)]:
        x = sign*.139
        eye = ellipsoid(f'DadEye{side}', (x, .241, 2.395), (.10, .072, .088), whites)
        ring = ellipsoid('Iris', (x, .302, 2.395), (.052, .025, .054), iris)
        pupil = ellipsoid('Pupil', (x, .323, 2.395), (.027, .010, .032), black)
        highlight = ellipsoid('Highlight', (x-.012, .332, 2.414), (.009, .004, .010), whites, 16)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in (eye, ring, pupil, highlight):
            obj.select_set(True)
        bpy.context.view_layer.objects.active = eye
        bpy.ops.object.join()
        eye.shape_key_add(name='Basis')
        blink = eye.shape_key_add(name='Blink')
        for v in blink.data:
            v.co.z *= .04
        headparts.append(eye)
        brow = ellipsoid('DadBrow', (x, .249, 2.515), (.11, .037, .026), hair)
        brow.rotation_euler.y = sign*.12
        headparts.append(brow)
        bindings[f'eye.{side}.blink'] = {'type': 'SHAPE_KEY', 'object': eye.name, 'target': 'Blink'}

    data = bpy.data.armatures.new('DadSkeleton')
    rig = bpy.data.objects.new('DadRig', data)
    collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    root = data.edit_bones.new('root')
    root.head, root.tail = (0, 0, .98), (0, 0, 1.78)
    neck = data.edit_bones.new('head')
    neck.head, neck.tail, neck.parent = (0, 0, 1.91), (0, 0, 2.55), root
    chains = {}
    for side, sign in [('L', -1), ('R', 1)]:
        shoulder, elbow, wrist = [Vector(p) for p in [(sign*.40, 0, 1.79), (sign*.67, -.015, 1.47), (sign*.75, .02, 1.11)]]
        upper = data.edit_bones.new(f'upper_arm.{side}')
        upper.head, upper.tail, upper.parent = shoulder, elbow, root
        fore = data.edit_bones.new(f'forearm.{side}')
        fore.head, fore.tail, fore.parent, fore.use_connect = elbow, wrist, upper, True
        chains[side] = (shoulder, elbow, wrist)
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.select_set(False)
    for obj in headparts:
        matrix = obj.matrix_world.copy()
        obj.parent, obj.parent_type, obj.parent_bone = rig, 'BONE', 'head'
        obj.matrix_world = matrix

    def tube(name, points, radius, material, side=None):
        vertices, faces, blends = [], [], []
        a, b, c = points
        sides, rings = 12, 17
        for i in range(rings):
            t = i/(rings-1)
            center = a.lerp(b, t*2) if t <= .5 else b.lerp(c, t*2-1)
            tangent = ((b-a) if t <= .5 else (c-b)).normalized()
            u = Vector((0, 1, 0))
            u = (u-tangent*u.dot(tangent)).normalized()
            v = tangent.cross(u).normalized()
            r = radius * (1 - .25*t)
            for j in range(sides):
                angle = 2*math.pi*j/sides
                vertices.append(center+r*(u*math.cos(angle)+v*math.sin(angle)))
                blends.append(max(0, min(1, (t-.4)/.2)))
                if i:
                    q=(i-1)*sides+j; n=(i-1)*sides+(j+1)%sides
                    faces.append((q,n,n+sides,q+sides))
        faces.extend([tuple(reversed(range(sides))),tuple((rings-1)*sides+j for j in range(sides))])
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj);mesh.materials.append(material)
        for polygon in mesh.polygons:polygon.use_smooth=True
        if side:
            groups=[obj.vertex_groups.new(name=f'{b}.{side}') for b in ('upper_arm','forearm')]
            for i,w in enumerate(blends):
                if w<1:groups[0].add([i],1-w,'REPLACE')
                if w>0:groups[1].add([i],w,'REPLACE')
            mod=obj.modifiers.new('Arm deformation','ARMATURE');mod.object=rig
        return obj

    checks=[]
    for side,sign in [('L',-1),('R',1)]:
        shoulder,elbow,wrist=chains[side]
        tube(f'DadSleeve{side}',(shoulder,elbow,wrist),.123,sweater,side)
        target=bpy.data.objects.new(f'DadHandTarget{side}',None);collection.objects.link(target);target.location=wrist
        pole=bpy.data.objects.new(f'DadElbowPole{side}',None);collection.objects.link(pole);pole.location=(sign*.9,-1,1.4)
        ik=rig.pose.bones[f'forearm.{side}'].constraints.new('IK');ik.target=target;ik.pole_target=pole;ik.chain_count=2;ik.use_stretch=False
        # Five separate digits in a simple mitten-free hand blockout.
        parts=[ellipsoid(f'DadPalm{side}',wrist+Vector((0,0,-.067)),(.076,.04,.085),skin)]
        for j in range(4):
            parts.append(ellipsoid(f'DadFinger{side}{j}',wrist+Vector(((j-1.5)*.035,0,-.165+(abs(j-1.5)*.012))),(.018,.022,.065-abs(j-1.5)*.009),skin,16))
        thumb=ellipsoid(f'DadThumb{side}',wrist+Vector((-sign*.085,.01,-.07)),(.024,.028,.058),skin,16);thumb.rotation_euler.y=sign*.5;parts.append(thumb)
        bpy.context.view_layer.update()
        for obj in parts:
            matrix=obj.matrix_world.copy();obj.parent=target;obj.matrix_world=matrix
        bindings[f'arm.{side}.target']={'type':'OBJECT_LOCATION','object':target.name}
        bindings[f'hand.{side}.rotation']={'type':'OBJECT_ROTATION','object':target.name}
        checks.append({'armature':rig.name,'bone':f'forearm.{side}','target':target.name})
        ellipsoid(f'DadJeanLeg{side}',(sign*.21,0,.64),(.17,.17,.47),jeans)
        ellipsoid(f'DadShoe{side}',(sign*.21,.075,.115),(.18,.28,.115),shoe)
    bindings['head.rotation']={'type':'POSE_ROTATION','object':rig.name,'target':'head'}
    bindings['jaw.open']={'type':'SHAPE_KEY','object':mouth.name,'target':'Open'}
    bpy.context.view_layer.update()
    output.mkdir(parents=True,exist_ok=True)
    blend=output/'dad.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),check_existing=False)
    package={'schema_version':2,'kind':'asset_package','asset_id':'dad-blockout','revision':'r1','art_status':'unreviewed','coordinate_system':'RH_Z_UP_METERS','forward_axis':'+Y','rotation_unit':'radian','blend':{'path':blend.relative_to(ROOT).as_posix(),'sha256':file_hash(blend),'collection':collection.name},'provenance':{'authoring_script':'studio/tools/build_dad_blockout.py','script_sha256':file_hash(__file__),'license':'project-original'},'bindings':bindings,'ik_checks':checks}
    (output/'package.json').write_text(json.dumps(package,indent=2)+'\n')
    print('DAD_BLOCKOUT_PACKAGE',output/'package.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='studio/out/dad-blockout')
    args=parser.parse_args()
    build(safe_path(ROOT,args.output))
