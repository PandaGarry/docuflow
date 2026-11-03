#!/usr/bin/env python3
"""Author unreviewed Dad r2: continuous garments, leg IK, articulated fingers.

Not final likeness, production topology, an IK/FK switch rig or a facial rig.
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
from studio.authoring.mesh import Mesh, pants, shoe, smooth, sweater, topology
from studio.tools.build_dad_blockout import build as build_base


def digits(sign):
    wrist = (sign*.75, .02, 1.11)
    result = {}
    for j, (name, length) in enumerate(zip(('index','middle','ring','pinky'),(.115,.13,.125,.10))):
        base = (wrist[0]+(j-1.5)*.034, wrist[1], wrist[2]-.105)
        result[name] = [(base[0],base[1]+.006*t,base[2]-length*t) for t in (0,.4,.75,1)]
    base=(wrist[0]-sign*.055,wrist[1]+.012,wrist[2]-.045)
    result['thumb']=[(base[0]-sign*.085*t,base[1]+.01*t,base[2]-.085*t) for t in (0,.4,.75,1)]
    return result


def hand_mesh(sign):
    mesh=Mesh();side='R' if sign>0 else 'L'
    wrist=(sign*.75,.02,1.11);previous=None
    for z,rx,ry in [(0,.06,.035),(-.035,.075,.04),(-.08,.076,.04),(-.115,.061,.032)]:
        ring=[mesh.vertex((wrist[0]+rx*math.cos(2*math.pi*j/16),wrist[1]+ry*math.sin(2*math.pi*j/16),wrist[2]+z),{f'hand.{side}':1}) for j in range(16)]
        if previous:mesh.bridge(previous,ring)
        else:mesh.cap(ring)
        previous=ring
    mesh.cap(previous)
    tips={}
    for name,points in digits(sign).items():
        previous=None
        for i in range(25):
            t=i/24
            segment=0 if t<.4 else (1 if t<.75 else 2)
            low,high=(0,.4,.75)[segment],(.4,.75,1)[segment]
            u=(t-low)/(high-low)
            a,b=points[segment:segment+2]
            center=[a[k]+(b[k]-a[k])*u for k in range(3)]
            tangent=[b[k]-a[k] for k in range(3)]
            norm=math.sqrt(sum(v*v for v in tangent));tangent=[v/norm for v in tangent]
            # One radial axis roughly faces the palm normal, the other lies sideways.
            axis=[0,1,0];dot=sum(a*b for a,b in zip(axis,tangent))
            axis=[axis[k]-dot*tangent[k] for k in range(3)]
            norm=math.sqrt(sum(v*v for v in axis));axis=[v/norm for v in axis]
            cross=[tangent[1]*axis[2]-tangent[2]*axis[1],tangent[2]*axis[0]-tangent[0]*axis[2],tangent[0]*axis[1]-tangent[1]*axis[0]]
            if t<.30:weights={f'{name}.01.{side}':1}
            elif t<.50:
                w=smooth((t-.30)/.20);weights={f'{name}.01.{side}':1-w,f'{name}.02.{side}':w}
            elif t<.65:weights={f'{name}.02.{side}':1}
            elif t<.85:
                w=smooth((t-.65)/.20);weights={f'{name}.02.{side}':1-w,f'{name}.03.{side}':w}
            else:weights={f'{name}.03.{side}':1}
            radius=(.021 if name=='thumb' else .018)*(1-.35*t)
            if t>.9:radius*=1-.65*(t-.9)/.1
            ring=[mesh.vertex([center[k]+radius*(axis[k]*math.cos(2*math.pi*j/10)+cross[k]*math.sin(2*math.pi*j/10)) for k in range(3)],weights) for j in range(10)]
            if previous:mesh.bridge(previous,ring)
            else:mesh.cap(ring)
            previous=ring
        mesh.cap(previous);tips[name]=previous
    return mesh,tips


def build(output):
    import bpy
    import bmesh
    from mathutils import Vector

    build_base(output/'_base')
    collection=bpy.data.collections['DadBlockout'];collection.name='DadBodyRig'
    rig=bpy.data.objects['DadRig']
    bpy.context.view_layer.update()
    for obj in list(collection.objects):
        if obj.name.startswith(('DadSweater','DadShoulders','DadHem','DadSleeve','DadJeanLeg','DadShoe','DadPalm','DadFinger','DadThumb','DadHairLock','DadHairCap')):
            bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    bones=rig.data.edit_bones
    pelvis=bones['root'];pelvis.name='pelvis';pelvis.head=(0,0,1.03);pelvis.tail=(0,0,1.20)

    def bone(name,a,b,parent=None,connected=False):
        item=bones.new(name);item.head=a;item.tail=b;item.parent=parent;item.use_connect=connected
        return item

    spine=bone('spine',(0,0,1.20),(0,0,1.50),pelvis)
    chest=bone('chest',(0,0,1.50),(0,0,1.86),spine)
    neck=bone('neck',(0,0,1.86),(0,0,1.98),chest)
    bones['head'].parent=neck
    for side,sign in [('R',1),('L',-1)]:
        clavicle=bone(f'clavicle.{side}',(0,0,1.79),(sign*.40,0,1.79),chest)
        bones[f'upper_arm.{side}'].parent=clavicle
        hand=bone(f'hand.{side}',(sign*.75,.02,1.11),(sign*.75,.02,1.01),bones[f'forearm.{side}'],True)
        hand.align_roll(Vector((0,1,0)))
        for name,points in digits(sign).items():
            parent=hand
            for j in range(3):
                parent=bone(f'{name}.{j+1:02d}.{side}',points[j],points[j+1],parent,j>0)
                parent.align_roll(Vector((0,1,0)))
        thigh=bone(f'thigh.{side}',(sign*.205,0,1.07),(sign*.215,.035,.64),pelvis)
        shin=bone(f'shin.{side}',(sign*.215,.035,.64),(sign*.215,0,.20),thigh,True)
        foot=bone(f'foot.{side}',(sign*.215,0,.20),(sign*.215,.24,.20),shin,True)
        foot.align_roll(Vector((0,0,1)))
    bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)

    def attach(name,mesh,material,subdivide=False):
        data=bpy.data.meshes.new(name);data.from_pydata(mesh.vertices,[],mesh.faces);data.update()
        bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
        obj=bpy.data.objects.new(name,data);collection.objects.link(obj);obj.parent=rig;data.materials.append(material)
        for poly in data.polygons:poly.use_smooth=len(poly.vertices)==4
        groups={name:obj.vertex_groups.new(name=name) for name in {b for w in mesh.weights for b in w}}
        for i,weights in enumerate(mesh.weights):
            for name,w in weights.items():groups[name].add([i],w,'REPLACE')
        mod=obj.modifiers.new('Body skin','ARMATURE');mod.object=rig;mod.use_deform_preserve_volume=True
        if subdivide:
            sub=obj.modifiers.new('Surface subdivision','SUBSURF');sub.levels=1;sub.render_levels=1
        return obj

    receipt={}
    for name,mesh,material in [('DadSweaterR2',sweater(),bpy.data.materials['Dad warm gray knit blockout']),('DadPantsR2',pants(),bpy.data.materials['Dad dark denim'])]:
        attach(name,mesh,material,True);receipt[name]=topology(mesh.vertices,mesh.faces)
        if receipt[name]['components']!=1 or receipt[name]['nonmanifold_edges']:
            raise ValueError(f'garment topology failed: {name}')
    # Collar and neck must follow the body, not remain in world space.
    for name,owner in [('DadCollar','neck'),('DadNeck','neck')]:
        obj=bpy.data.objects[name];matrix=obj.matrix_world.copy();obj.parent=rig;obj.matrix_world=matrix;group=obj.vertex_groups.new(name=owner);group.add(list(range(len(obj.data.vertices))),1,'REPLACE')
        mod=obj.modifiers.new('Neck skin','ARMATURE');mod.object=rig
    source=json.loads((output/'_base/package.json').read_text())
    bindings={k:v for k,v in source['bindings'].items() if not k.startswith('hand.')}
    bindings['body.translation']={'type':'OBJECT_LOCATION','object':rig.name}
    for name in ('pelvis','spine','chest','neck'):
        bindings[f'body.{name}.rotation']={'type':'POSE_ROTATION','object':rig.name,'target':name}
    contacts=[];fingertips=[];checks=list(source['ik_checks'])
    for side,sign in [('R',1),('L',-1)]:
        goal=bpy.data.objects.new(f'DadFootTarget{side}',None);collection.objects.link(goal);goal.location=(sign*.215,0,.20)
        pole=bpy.data.objects.new(f'DadKneePole{side}',None);collection.objects.link(pole);pole.location=(sign*.215,1.2,.65)
        ik=rig.pose.bones[f'shin.{side}'].constraints.new('IK');ik.target=goal;ik.pole_target=pole;ik.chain_count=2;ik.use_stretch=False;ik.iterations=500
        rotation=rig.pose.bones[f'foot.{side}'].constraints.new('COPY_ROTATION');rotation.target=goal;rotation.owner_space='WORLD';rotation.target_space='WORLD'
        mesh,ids=shoe(sign);obj=attach(f'DadShoeR2{side}',mesh,bpy.data.materials['Dad brown shoes'])
        contacts.append({'id':f'sole.{side}','object':obj.name,'vertex_indices':ids,'ground_z':0})
        bindings[f'foot.{side}.target']={'type':'OBJECT_LOCATION','object':goal.name}
        bindings[f'foot.{side}.rotation']={'type':'OBJECT_ROTATION','object':goal.name}
        checks.append({'armature':rig.name,'bone':f'shin.{side}','target':goal.name})
        mesh,tips=hand_mesh(sign);obj=attach(f'DadHandR2{side}',mesh,bpy.data.materials['Dad skin'])
        receipt[obj.name]=topology(mesh.vertices,mesh.faces)
        bindings[f'wrist.{side}.rotation']={'type':'POSE_ROTATION','object':rig.name,'target':f'hand.{side}'}
        for name,indices in tips.items():
            fingertips.append({'id':f'finger.{side}.{name}','object':obj.name,'vertex_indices':indices,'armature':rig.name,'reference_bone':f'hand.{side}'})
            for j in range(1,4):bindings[f'finger.{side}.{name}.{j:02d}']={'type':'POSE_ROTATION','object':rig.name,'target':f'{name}.{j:02d}.{side}'}
    # Replace the pillow-like hair locks with tapered swept clumps. Still blockout art.
    hair=bpy.data.materials['Dad beard'];hair.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.035,.016,.009,1)
    for lobe,x in enumerate([-.22,-.11,0,.11,.22]):
        mesh=Mesh();previous=None
        for i in range(13):
            t=i/12;cy=.09-.27*t;cz=2.60+.17*math.sin(t*math.pi*.75)+.035*(1-abs(x)/.24)
            width=.075*(1-t)**.7+.003;depth=.085*(1-t)**.6+.003
            ring=[mesh.vertex((x-.035*t+width*math.cos(2*math.pi*j/12),cy,cz+depth*math.sin(2*math.pi*j/12)),{'head':1}) for j in range(12)]
            if previous:mesh.bridge(previous,ring)
            else:mesh.cap(ring)
            previous=ring
        mesh.cap(previous);attach(f'DadHairR2{lobe}',mesh,hair,True)
    bpy.context.view_layer.update()
    unweighted=0;weight_error=0
    for obj in collection.objects:
        if obj.type!='MESH' or not any(m.type=='ARMATURE' for m in obj.modifiers):continue
        for v in obj.data.vertices:
            total=sum(g.weight for g in v.groups)
            unweighted+=int(total<=0);weight_error=max(weight_error,abs(total-1))
    receipt.update(bone_count=len(rig.data.bones),unweighted_vertices=unweighted,max_weight_sum_error=weight_error,
                   hand_surface_components_note='6 closed intersecting surfaces per hand; not final continuous hand topology')
    if unweighted or weight_error>1e-5:raise ValueError('invalid skin weights')
    blend=output/'dad-rig.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),check_existing=False)
    dependencies=['studio/tools/build_dad_blockout.py','studio/authoring/mesh.py']
    package={'schema_version':2,'kind':'asset_package','asset_id':'dad-body-rig','revision':'r2','art_status':'unreviewed',
             'coordinate_system':'RH_Z_UP_METERS','forward_axis':'+Y','rotation_unit':'radian',
             'blend':{'path':blend.relative_to(ROOT).as_posix(),'sha256':file_hash(blend),'collection':collection.name},
             'provenance':{'authoring_script':'studio/tools/build_dad_rig.py','script_sha256':file_hash(__file__),'license':'project-original',
                           'dependencies':[{'path':p,'sha256':file_hash(ROOT/p)} for p in dependencies]},
             'bindings':bindings,'ik_checks':checks,'contact_probes':contacts,'fingertip_probes':fingertips}
    (output/'package.json').write_text(json.dumps(package,indent=2)+'\n')
    (output/'model-audit.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('DAD_BODY_RIG_R2',output/'package.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='studio/out/dad-rig-r2')
    args=parser.parse_args();build(safe_path(ROOT,args.output))
