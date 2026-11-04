"""Small authored diagnostic scene: IK-skinned arm and a jaw shape key.

This is deliberately NOT a family character, walk cycle, facial rig, or lip sync.
Blender imports are confined to worker-side functions.
"""
from __future__ import annotations

import math


def build_scene(bpy, project):
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    render = project['render']
    scene.cycles.device = 'CPU'
    scene.cycles.samples = render['samples']
    scene.cycles.use_denoising = render['denoise']
    scene.cycles.seed = render['seed']
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = render['threads']
    scene.render.resolution_x, scene.render.resolution_y = project['resolution']
    scene.render.resolution_percentage = 100
    scene.render.fps = project['fps']['num']
    scene.render.fps_base = project['fps']['den']
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.view_settings.view_transform = render['view_transform']
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.world = bpy.data.worlds.new('StudioWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.65, .71, .74, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .3

    def material(name, color, roughness=.5, metallic=0):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (*color, 1)
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
        return mat

    mint = material('Mint ceramic', (.12, .51, .38))
    cream = material('Warm ceramic', (.78, .68, .48))
    dark = material('Joint graphite', (.045, .065, .075), .35)
    floor = material('Studio matte', (.73, .75, .68), .8)
    orange = material('Diagnostic orange', (.93, .27, .065), .4)

    def cube(name, location, scale, mat, bevel=.08):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(mat)
        if bevel:
            mod = obj.modifiers.new('Rounded edges', 'BEVEL')
            mod.width = bevel
            mod.segments = 4
            obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
        return obj

    def sphere(name, loc, radius, mat):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=loc)
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(mat)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        return obj

    cube('Stage', (0, 0, -.12), (200, 200, .2), floor, 0)
    cube('Pedestal', (.18, 0, .12), (2.9, 1.6, .24), dark, .12)
    for x in (-.24, .24):
        cube('Static boot', (x, .12, .33), (.36, .65, .2), cream, .06)
        cube('Static leg', (x, 0, .77), (.25, .29, .73), dark, .06)
    cube('Torso', (0, 0, 1.45), (.87, .58, .85), mint)
    cube('Chest marker', (0, .31, 1.49), (.21, .025, .21), orange, .025)
    sphere('Neck', (0, 0, 1.98), .14, dark)
    cube('Head', (0, 0, 2.35), (.82, .62, .61), cream, .14)
    for x in (-.19, .19):
        eye = sphere('Diagnostic eye', (x, .305, 2.4), .082, dark)
        eye.scale.y = .48
    cube('Mouth cavity', (0, .312, 2.16), (.45, .05, .2), dark, .025)
    jaw = cube('Jaw', (0, .35, 2.105), (.51, .18, .15), mint, .025)
    jaw.shape_key_add(name='Basis')
    key = jaw.shape_key_add(name='Open')
    for vertex in key.data:
        vertex.co.z -= .19
    key.slider_min, key.slider_max = 0, 1
    sphere('Static shoulder', (-.51, 0, 1.79), .15, dark)
    cube('Static arm', (-.64, 0, 1.46), (.22, .27, .56), cream, .07)

    # Two-bone chain. One continuous mesh with blended vertex weights.
    shoulder = Vector((.48, 0, 1.81))
    elbow = Vector((.98, -.04, 1.53))
    wrist = Vector((1.38, 0, 1.78))
    sphere('Arm shoulder', shoulder, .14, dark)
    data = bpy.data.armatures.new('ProbeSkeleton')
    arm = bpy.data.objects.new('Rig', data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    upper = data.edit_bones.new('upper_arm.R')
    upper.head, upper.tail = shoulder, elbow
    fore = data.edit_bones.new('forearm.R')
    fore.head, fore.tail = elbow, wrist
    fore.parent = upper
    fore.use_connect = True
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.select_set(False)
    target = bpy.data.objects.new('HandTarget', None)
    scene.collection.objects.link(target)
    target.location = wrist
    pole = bpy.data.objects.new('ElbowPole', None)
    scene.collection.objects.link(pole)
    pole.location = (.9, -1.2, 1.3)
    constraint = arm.pose.bones['forearm.R'].constraints.new('IK')
    constraint.target = target
    constraint.pole_target = pole
    constraint.chain_count = 2
    constraint.use_stretch = False
    constraint.iterations = 200

    vertices, faces, weights = [], [], []
    rings, sides = 17, 12
    for i in range(rings):
        t = i / (rings - 1)
        if t <= .5:
            center = shoulder.lerp(elbow, t * 2)
            tangent = (elbow - shoulder).normalized()
        else:
            center = elbow.lerp(wrist, t * 2 - 1)
            tangent = (wrist - elbow).normalized()
        side = Vector((0, 1, 0))
        side = (side - tangent * side.dot(tangent)).normalized()
        other = tangent.cross(side).normalized()
        # Small transition region around the elbow to exercise skin deformation.
        blend = max(0.0, min(1.0, (t - .40) / .20))
        for j in range(sides):
            angle = j * 2 * math.pi / sides
            vertices.append(center + .105 * (math.cos(angle) * side + math.sin(angle) * other))
            weights.append(blend)
            if i:
                a = (i - 1) * sides + j
                b = (i - 1) * sides + (j + 1) % sides
                faces.append((a, b, b + sides, a + sides))
    faces.extend([tuple(reversed(range(sides))), tuple((rings - 1) * sides + j for j in range(sides))])
    mesh = bpy.data.meshes.new('Weighted arm mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    skin = bpy.data.objects.new('SkinnedArm', mesh)
    scene.collection.objects.link(skin)
    skin.data.materials.append(cream)
    vg_upper = skin.vertex_groups.new(name='upper_arm.R')
    vg_fore = skin.vertex_groups.new(name='forearm.R')
    for idx, blend in enumerate(weights):
        if blend < 1:
            vg_upper.add([idx], 1 - blend, 'REPLACE')
        if blend > 0:
            vg_fore.add([idx], blend, 'REPLACE')
    modifier = skin.modifiers.new('Live skinning', 'ARMATURE')
    modifier.object = arm
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    hand = sphere('Diagnostic hand', wrist, .14, mint)
    hand.parent = target
    hand.location = (0, 0, 0)

    for name, loc, energy, size in [('Key', (1.5, 4.5, 6), 650, 4),
                                     ('Fill', (-4, 1, 3.5), 450, 5),
                                     ('Rim', (2, -3, 4), 800, 3)]:
        bpy.ops.object.light_add(type='AREA', location=loc)
        lamp = bpy.context.object
        lamp.name = name
        lamp.data.energy = energy
        lamp.data.shape = 'DISK'
        lamp.data.size = size
        lamp.rotation_euler = (Vector((0, 0, 1.3)) - lamp.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add(location=(3.4, 6.8, 3.3))
    cam = bpy.context.object
    cam.name = 'ProbeCamera'
    cam.rotation_euler = (Vector((.27, 0, 1.36)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = 5.8
    scene.camera = cam
    return scene
