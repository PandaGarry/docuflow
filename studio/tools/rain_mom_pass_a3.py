#!/usr/bin/env python3
"""A3: reference-directed face authoring on actual Rain, NOT a likeness pass.

A1/A2 recipes and evidence are immutable. New coordinates are transported through
ALL original corrective keys; source bone rest, weights and drivers stay intact.
Stock wardrobe and haircut retained, hair/iris palette adjusted toward the canon.
"""
from __future__ import annotations

import json
import numpy as np
import rain_mom_pass as base
import rain_mom_pass_a2 as controls

ROOT = base.ROOT
study = base.study
OUT = ROOT / 'studio/reviews/rain-mom-a3'


def smoothstep(a, b, x):
    t = np.clip((x-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def face_field(points):
    """Authored smooth deformation in A2 world-rest coordinates, meters.

    Reference observations, not a fitted 3D scan: smaller/narrower button nose,
    less pout, wider curved lip line, shorter/tapered lower face, reduced ear
    prominence, subtle outer-eye tilt. Eye centers/spread intentionally retained.
    """
    p = np.asarray(points, dtype=np.float64)
    x, y, z = p.T
    q = p.copy()
    front = smoothstep(-.025, -.080, y)
    # Narrow the broad source nasal base; pull tip back and slightly up.
    nose = np.exp(-((x/.029)**4 + ((z-1.425)/.026)**4))*front
    q[:, 0] -= .25*x*nose
    q[:, 1] += .010*np.exp(-((x/.025)**2+((z-1.426)/.023)**2))*front
    q[:, 2] += .0025*np.exp(-((x/.025)**2+((z-1.425)/.020)**2))*front
    # Retain full upper cheeks, taper jowls; shorten bottom of the face.
    jaw = np.exp(-((z-1.365)/.035)**2)*np.exp(-(x/.12)**8)
    jaw *= .3+.7*smoothstep(.030,.065,np.abs(x))
    q[:, 0] -= .12*x*jaw
    q[:, 2] += .008*np.exp(-((z-1.343)/.030)**2)*np.exp(-(x/.12)**8)
    # Reference lips: wider, thinner, less projected, gently raised corners.
    mouth = np.exp(-((x/.047)**6+((z-1.389)/.018)**4))*front
    q[:, 0] += .13*x*mouth
    q[:, 2] -= .23*(z-1.389)*mouth
    q[:, 1] += .0055*mouth
    q[:, 2] += .0035*(np.exp(-((x-.031)/.014)**2)+np.exp(-((x+.031)/.014)**2))*np.exp(-((z-1.390)/.016)**2)*front
    # Eye dimensions already similar to reference: small change, not a big shrink.
    for center in (-.047,.047):
        eye = np.exp(-(((x-center)/.029)**4+((z-1.472)/.034)**4))*front
        dx=x-center
        q[:, 0] -= .035*dx*eye
        q[:, 2] += (-.035*(z-1.472)+.055*np.sign(center)*dx)*eye
    # Ears distract from the reference's hair-framed face. Keep attachment smooth.
    ear=smoothstep(.104,.130,np.abs(x))*np.exp(-((z-1.465)/.080)**4)
    q[:, 0] -= np.sign(x)*.012*ear
    q[:, 2] -= .18*(z-1.465)*ear
    return q


def change_face(bpy):
    records=[]
    for obj in bpy.data.objects:
        if obj.type!='MESH' or not obj.name.startswith('GEO-rain-'):
            continue
        world=obj.matrix_world.copy(); inv=world.inverted()
        keys=obj.data.shape_keys
        blocks=[k.data for k in keys.key_blocks] if keys else [obj.data.vertices]
        maximum=0
        for block in blocks:
            original=base.transform_points(base.point_array(block),world)
            changed=face_field(original)
            if obj.name=='GEO-rain-eyebrows':
                # Taper the outer tail; keep the existing A1 brow's smooth arch.
                arch=.0025*np.exp(-((np.abs(original[:,0])-.059)/.023)**2)
                changed[:,2]+=arch
            maximum=max(maximum,float(np.linalg.norm(changed-original,axis=1).max()))
            block.foreach_set('co',base.transform_points(changed,inv).ravel())
        if keys:
            obj.data.vertices.foreach_set('co',base.point_array(keys.key_blocks[0].data).ravel()); keys.update_tag()
        obj.data.update()
        records.append({'object':obj.name,'corrective_blocks_transported':len(blocks) if keys else 0,'maximum_additional_rest_change_m':maximum})
    bpy.context.view_layer.update()
    return records


def insert_color_node(tree, socket, node):
    if len(socket.links)!=1:
        raise ValueError('Unexpected source shader: review before changing it')
    source=socket.links[0].from_socket
    tree.links.new(source,node.inputs['Color'])
    tree.links.new(node.outputs['Color'],socket)


def complexion(bpy):
    """Attached color attribute, not a painted-over render. No source UV loss."""
    for obj in bpy.data.objects:
        if obj.type!='MESH' or not any(m and m.name=='MAT-rain.body' for m in obj.data.materials):
            continue
        mesh=obj.data
        layer=mesh.color_attributes.new(name='Docuflow complexion A3',type='FLOAT_COLOR',domain='CORNER')
        p=base.transform_points(base.point_array(mesh.vertices),obj.matrix_world)
        x,y,z=p.T; front=smoothstep(-.025,-.080,y)
        blush=.24*np.exp(-((np.abs(x)-.066)/.028)**2-((z-1.430)/.025)**2)*front
        lips=.28*np.exp(-((x/.042)**6+((z-1.391)/.010)**4))*front
        tint=np.zeros((len(p),4),dtype=np.float32)
        rose=np.array(base.linear_color('#D5907F')[:3]); lip=np.array(base.linear_color('#B76F63')[:3])
        total=blush+lips
        tint[:,:3]=(blush[:,None]*rose+lips[:,None]*lip)/np.maximum(total[:,None],1e-12)
        tint[:,3]=np.clip(total,0,1)
        loops=np.empty(len(mesh.loops),dtype=np.int32);mesh.loops.foreach_get('vertex_index',loops)
        layer.data.foreach_set('color',tint[loops].ravel())
    tree=bpy.data.materials['MAT-rain.body'].node_tree
    socket=tree.nodes['Principled BSDF'].inputs['Base Color']
    source=socket.links[0].from_socket
    attr=tree.nodes.new('ShaderNodeVertexColor');attr.layer_name='Docuflow complexion A3'
    mix=tree.nodes.new('ShaderNodeMixRGB');mix.name='A3 attached complexion';mix.blend_type='MIX'
    tree.links.new(source,mix.inputs[1]);tree.links.new(attr.outputs['Color'],mix.inputs[2]);tree.links.new(attr.outputs['Alpha'],mix.inputs[0]);tree.links.new(mix.outputs[0],socket)
    # Desaturate iris texture: white sclera and dark pupil remain neutral.
    tree=bpy.data.materials['MAT-rain.eyes'].node_tree
    hsv=tree.nodes.new('ShaderNodeHueSaturation');hsv.name='A3 gray blue iris';hsv.inputs['Saturation'].default_value=.30
    insert_color_node(tree,tree.nodes['Principled BSDF'].inputs['Base Color'],hsv)
    # Keep actual source hair geometry; move palette from near-black to warm brown.
    tree=bpy.data.materials['MAT-rain.hair'].node_tree
    for node in list(tree.nodes):
        if node.type!='BSDF_PRINCIPLED':
            continue
        socket=node.inputs['Base Color']
        if len(socket.links)!=1:
            continue
        original=socket.links[0].from_socket
        lift=tree.nodes.new('ShaderNodeHueSaturation');lift.name='A3 warm hair lift';lift.inputs['Value'].default_value=2.0
        tree.links.new(original,lift.inputs['Color'])
        tint=tree.nodes.new('ShaderNodeMixRGB');tint.name='A3 canonical hair palette';tint.inputs[0].default_value=.35;tint.inputs[2].default_value=base.linear_color('#9A7856')
        tree.links.new(lift.outputs[0],tint.inputs[1]);tree.links.new(tint.outputs[0],socket)
    bpy.data.materials['MAT-rain.eyebrows'].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=base.linear_color('#785339')


def set_blink(bpy,rig,amount):
    records=[]
    # Upper + lower motion rather than burying the upper lid at the lower rim.
    for side in ('L','R'):
        for name,value in ((f'ACT-Eyelid_Upper.{side}',-.04*.70*amount),(f'ACT-Eyelid_Lower.{side}',.04*.30*amount)):
            bone=rig.pose.bones[name];bone.location.y=value
            records.append({'bone':name,'local_y':value})
    rig.update_tag();bpy.context.view_layer.update()
    return records


def expression_checks(bpy,rig,matrices,scene,camera,prefix):
    neutral=base.head_geometry(bpy)
    records=[];images=[]
    for label in ('blink','smile'):
        controls.restore(bpy,rig,matrices)
        if label=='blink':
            actuators=set_blink(bpy,rig,1)
        else:
            actuators=[controls.set_key_via_actuator(bpy,rig,f'Smile.{side}',.65,'ACT-Lips') for side in ('L','R')]
        posed=base.head_geometry(bpy)
        records.append({'pose':label,'actuators':actuators,'finite':bool(np.isfinite(posed).all()),'maximum_head_displacement_m':float(np.linalg.norm(posed-neutral,axis=1).max())})
        images.append(study.render(bpy,scene,camera,OUT/f'{prefix}-{label}.png',(0,-4,1.5),(0,0,1.45),.60))
    sweep=[]
    for value in (0,.25,.5,.75,1,.75,.5,.25,0):
        controls.restore(bpy,rig,matrices);set_blink(bpy,rig,value)
        vertices=base.head_geometry(bpy)
        sweep.append({'blink_amplitude':value,'finite':bool(np.isfinite(vertices).all()),'maximum_head_displacement_m':float(np.linalg.norm(vertices-neutral,axis=1).max())})
    controls.restore(bpy,rig,matrices)
    return images,records,sweep


def review_board():
    from PIL import Image,ImageDraw
    # Cropping is for side-by-side review only; individual native frames untouched.
    board=Image.new('RGB',(1800,940),'#202b36');draw=ImageDraw.Draw(board)
    panels=[('REFERENCE MOM',ROOT/'studio/characters/mom/master/turnaround.png',(105,245,250,395)),
            ('PREVIOUS A2',ROOT/'studio/reviews/rain-mom-a2/candidate-face.png',(205,215,565,585)),
            ('CANDIDATE A3',OUT/'candidate-face.png',(205,215,565,585))]
    for i,(label,path,crop) in enumerate(panels):
        with Image.open(path) as im:
            panel=im.crop(crop);panel=panel.resize((570,round(panel.height*570/panel.width)),Image.Resampling.LANCZOS)
            panel.thumbnail((570,690),Image.Resampling.LANCZOS)
            board.paste(panel,(i*600+(600-panel.width)//2,70+(690-panel.height)//2))
        draw.text((i*600+24,24),label,fill='white',font_size=26)
    draw.text((24,805),'A2/A3: same camera, lighting, pose. Reference crop is 2D art with different lighting.',fill='white',font_size=23)
    draw.text((24,850),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. Not approved.',fill='white',font_size=22)
    board.save(OUT/'comparison-reference.png')


def main():
    import bpy
    OUT.mkdir(parents=True,exist_ok=True)
    source=study.acquire(ROOT/'.cache/rain-v3')
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False);bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain'];signature=base.rig_signature(rig)
    matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones}
    topology={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'}
    invalid_before=base.invalid_drivers(bpy)
    scene,camera=study.stage(bpy)
    source_images,source_poses,source_sweep=expression_checks(bpy,rig,matrices,scene,camera,'source')
    a1_changes=base.change_meshes(bpy);base.change_materials(bpy)
    edits=change_face(bpy);complexion(bpy)
    neutral=base.head_geometry(bpy)
    images=[study.render(bpy,scene,camera,OUT/'candidate-face.png',(0,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-three-quarter.png',(2.2,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-profile.png',(4,0,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-full.png',(0,-4,1.05),(0,0,.85),1.95)]
    pose_images,poses,sweep=expression_checks(bpy,rig,matrices,scene,camera,'candidate')
    invalid_after=base.invalid_drivers(bpy)
    records={'revision':'rain-mom-a3','source_blend_sha256':study.sha(source),'archive_sha256':study.ARCHIVE_SHA,'source_url':study.URL,
             'blender_version':bpy.app.version_string,'source_scripts_executed':False,
             'scripts':{name:study.sha(ROOT/'studio/tools'/name) for name in ('rain_study.py','rain_mom_pass.py','rain_mom_pass_a2.py','rain_mom_pass_a3.py')},
             'reference_sha256':study.sha(ROOT/'studio/characters/mom/master/turnaround.png'),
             'change_notice':'A1 body/skin retained. A3 smaller/narrower nose, tapered/shorter lower face, less pout, wider curved mouth, reduced ears, subtle eye-contour tilt, attached blush/lip color, desaturated iris, warmer hair palette. Original haircut/wardrobe retained.',
             'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
             'base_edits':a1_changes,'face_edits':edits,'images':images+source_images+pose_images,
             'source_expressions':source_poses,'candidate_expressions':poses,'source_blink_sweep':source_sweep,'candidate_blink_sweep':sweep,
             'rig_rest_signature_before':signature,'rig_rest_signature_after':base.rig_signature(rig),
             'topology_unchanged':topology=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'},
             'source_invalid_drivers':invalid_before,'candidate_invalid_drivers':invalid_after,'new_invalid_drivers':sorted(set(invalid_after)-set(invalid_before)),
             'neutral_head_restore_error_m':float(np.linalg.norm(base.head_geometry(bpy)-neutral,axis=1).max()),
             'art_approved':False,'production_swap_allowed':False,'scope':'Reference-directed still study and limited native blink sweep, not a full animation/anatomy/likeness acceptance.'}
    if not records['topology_unchanged'] or records['rig_rest_signature_after']!=signature:
        raise ValueError('Unexpected topology/rest rig change')
    if not all(s['finite'] for s in source_sweep+sweep+poses+source_poses):
        raise ValueError('Nonfinite evaluated geometry')
    # Record useful rest geometry bounds for subsequent authored face/rig work.
    records['rest_bounds']={o.name:{'min':base.transform_points(base.point_array(o.data.vertices),o.matrix_world).min(axis=0).tolist(),
                                  'max':base.transform_points(base.point_array(o.data.vertices),o.matrix_world).max(axis=0).tolist()}
                            for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('GEO-rain-')}
    text=bpy.data.texts.new('DOCUFLOW_A3_CHANGES.txt');text.write(records['credit']+'\nCC BY 4.0 '+records['license_url']+'\n'+records['change_notice']+'\nExperimental, not approved. Asset Python scripts NOT executed.\n')
    bpy.ops.file.pack_all();native=ROOT/'.cache/rain-v3/rain-mom-a3.blend';bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()),compress=True)
    records['native_artifact']={'filename':native.name,'sha256':study.sha(native),'textures_packed':True,'storage':'GitHub Actions artifact, 14 days; scripts reconstruct the candidate.'}
    study.write(OUT/'report.json',records)
    review_board()


if __name__=='__main__':
    main()
