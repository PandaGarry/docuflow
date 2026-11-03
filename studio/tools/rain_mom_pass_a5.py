#!/usr/bin/env python3
"""A5: repair failed A4 hair shading, fill curtain gaps, improve part/curl shape.

A4's black-hair failure remains published, not silently overwritten. Actual Rain
face/body/rig retained. Independent new groom shader avoids source-object shader
attributes that are not valid on newly authored clumps. No embedded Python runs.
"""
from __future__ import annotations

import math
import numpy as np
import rain_mom_pass_a4 as prior

face=prior.face
base=prior.base
controls=prior.controls
study=prior.study
ROOT=prior.ROOT
OUT=ROOT/'studio/reviews/rain-mom-a5'


def groom_material(bpy):
    mat=bpy.data.materials.new('MAT-mom.hair-a5');mat.use_nodes=True
    tree=mat.node_tree;nodes=tree.nodes
    shader=nodes.get('Principled BSDF')
    shader.inputs['Weight'].default_value=1
    shader.inputs['Roughness'].default_value=.50
    shader.inputs['Specular IOR Level'].default_value=.28
    shader.inputs['Anisotropic'].default_value=.35
    shader.inputs['IOR'].default_value=1.45
    uv=nodes.new('ShaderNodeTexCoord')
    mapping=nodes.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(36,2,1)
    tree.links.new(uv.outputs['UV'],mapping.inputs[0])
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=4;noise.inputs['Detail'].default_value=2
    tree.links.new(mapping.outputs[0],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.15;ramp.color_ramp.elements[0].color=base.linear_color('#876343')
    ramp.color_ramp.elements[1].position=.85;ramp.color_ramp.elements[1].color=base.linear_color('#B48D61')
    tree.links.new(noise.outputs['Fac'],ramp.inputs['Fac']);tree.links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16;bump.inputs['Distance'].default_value=.0010
    tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);tree.links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    return mat


def revise_groom(bpy,rig):
    record=prior.author_hair(bpy,rig)
    material=groom_material(bpy)
    crown=bpy.data.objects['GEO-rain-hair_main']
    # Lift the source widow's-peak tip into the new center part, all hair keys.
    blocks=[k.data for k in crown.data.shape_keys.key_blocks] if crown.data.shape_keys else [crown.data.vertices]
    for block in blocks:
        p=base.transform_points(base.point_array(block),crown.matrix_world)
        x,y,z=p.T
        peak=np.exp(-((x/.032)**2+((y+.115)/.045)**2+((z-1.585)/.040)**2))
        p[:,2]+=.026*peak;p[:,1]+=.006*peak
        block.foreach_set('co',base.transform_points(p,crown.matrix_world.inverted()).ravel())
    if crown.data.shape_keys:
        crown.data.vertices.foreach_set('co',base.point_array(crown.data.shape_keys.key_blocks[0].data).ravel());crown.data.shape_keys.update_tag()
    crown.data.update()
    crown.data.materials.clear();crown.data.materials.append(material)
    for item in record['added_clumps']:
        obj=bpy.data.objects[item['object']]
        path=np.array(item['control_points'],dtype=float)
        if 'curtain' in item['object']:
            factors=np.array([1.10,1.15,1.15,1.10,1.05,1.04,1.05])
            path[:,0]*=factors;path[:,1]=.012+(path[:,1]-.012)*factors
            # Greater gentle lateral wave; overlap adjacent locks instead of gaps.
            angle=math.atan2(path[3,0],path[3,1]-.012)
            phase=int(item['object'].rsplit('-',1)[1])*.9
            for i in range(2,len(path)):
                wave=.0045*math.sin(i*1.9+phase)
                path[i,0]+=wave*math.cos(angle);path[i,1]-=wave*math.sin(angle)
            widths=np.array(item['widths_m'])*np.array([1.15,1.32,1.32,1.32,1.32,1.25,2])
            depths=np.array(item['depths_m'])*1.20
            normal=(math.sin(angle),math.cos(angle),0)
        else:
            sign=-1 if '-1' in item['object'] else 1
            path[:,0]=sign*np.array([.005,.034,.079,.116,.139,.145,.126,.160])
            widths=np.array(item['widths_m'])*np.array([1.2,1.05,1.08,1.12,1.12,1.10,1.10,2])
            depths=np.array(item['depths_m'])*1.12
            normal=(0,-1,0)
        points,_=prior.loft_geometry(path,widths,depths,normal)
        obj.data.vertices.foreach_set('co',np.asarray(points).ravel());obj.data.update()
        obj.data.materials.clear();obj.data.materials.append(material)
        item.update({'control_points':path.tolist(),'widths_m':widths.tolist(),'depths_m':depths.tolist()})
    bpy.context.view_layer.update()
    record['material']='Independent Principled shader, Weight=1, no inherited source-object attributes; #876343 to #B48D61 subtle fiber variation.'
    record['changes_since_a4']='Overlap curtain widths, fuller side coverage, larger face-framing waves, lifted source widow peak, matte warm brown groom shader.'
    return record


def render_poses(bpy,rig,matrices,scene,camera):
    neutral=base.head_geometry(bpy);images=[];poses=[];sweep=[]
    for label in ('blink','smile'):
        controls.restore(bpy,rig,matrices)
        actuators=face.set_blink(bpy,rig,1) if label=='blink' else [controls.set_key_via_actuator(bpy,rig,f'Smile.{s}',.65,'ACT-Lips') for s in ('L','R')]
        p=base.head_geometry(bpy)
        poses.append({'pose':label,'actuators':actuators,'finite':bool(np.isfinite(p).all()),'max_displacement_m':float(np.linalg.norm(p-neutral,axis=1).max())})
        images.append(study.render(bpy,scene,camera,OUT/f'candidate-{label}.png',(0,-4,1.5),(0,0,1.45),.60))
    for value in (0,.25,.5,.75,1,.75,.5,.25,0):
        controls.restore(bpy,rig,matrices);face.set_blink(bpy,rig,value)
        p=base.head_geometry(bpy)
        sweep.append({'amplitude':value,'finite':bool(np.isfinite(p).all()),'max_displacement_m':float(np.linalg.norm(p-neutral,axis=1).max())})
    controls.restore(bpy,rig,matrices)
    return images,poses,sweep


def board():
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(1800,940),'#202b36');draw=ImageDraw.Draw(canvas)
    panels=[('REFERENCE MOM',ROOT/'studio/characters/mom/master/turnaround.png',(90,205,275,495)),
            ('START OF THIS PASS: A2',ROOT/'studio/reviews/rain-mom-a2/candidate-face.png',(160,95,610,760)),
            ('CURRENT STUDY A5',OUT/'candidate-face.png',(160,95,610,760))]
    for i,(label,path,crop) in enumerate(panels):
        with Image.open(path) as image:
            panel=image.crop(crop);scale=min(570/panel.width,720/panel.height)
            panel=panel.resize((round(panel.width*scale),round(panel.height*scale)),Image.Resampling.LANCZOS)
            canvas.paste(panel,(i*600+(600-panel.width)//2,70+(720-panel.height)//2))
        draw.text((i*600+24,24),label,fill='white',font_size=25)
    draw.text((24,825),'Actual Rain model + authored hair. Same A2/A5 camera/light. Reference is 2D art, not a matched render.',fill='white',font_size=21)
    draw.text((24,870),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. Study, not approved.',fill='white',font_size=21)
    canvas.save(OUT/'comparison-reference.png')


def main():
    import bpy
    OUT.mkdir(parents=True,exist_ok=True)
    source=study.acquire(ROOT/'.cache/rain-v3')
    bpy.context.preferences.filepaths.use_scripts_auto_execute=False
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()),use_scripts=False);bpy.context.view_layer.update()
    rig=bpy.data.objects['RIG-rain'];signature=base.rig_signature(rig)
    matrices={b.name:b.matrix_basis.copy() for b in rig.pose.bones}
    topology={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in bpy.data.objects if o.type=='MESH'}
    invalid=base.invalid_drivers(bpy)
    base.change_meshes(bpy);base.change_materials(bpy);face.change_face(bpy);face.complexion(bpy);prior.refine_nasal_base(bpy)
    hair=revise_groom(bpy,rig)
    scene,camera=study.stage(bpy);neutral=base.head_geometry(bpy)
    images=[study.render(bpy,scene,camera,OUT/'candidate-face.png',(0,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-three-quarter.png',(2.2,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-profile.png',(4,0,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-full.png',(0,-4,1.05),(0,0,.85),1.95)]
    pose_images,poses,sweep=render_poses(bpy,rig,matrices,scene,camera)
    record={'revision':'rain-mom-a5','source_blend_sha256':study.sha(source),'source_url':study.URL,'archive_sha256':study.ARCHIVE_SHA,
            'scripts':{n:study.sha(ROOT/'studio/tools'/n) for n in ('rain_study.py','rain_mom_pass.py','rain_mom_pass_a2.py','rain_mom_pass_a3.py','rain_mom_pass_a4.py','rain_mom_pass_a5.py')},
            'reference_sha256':study.sha(ROOT/'studio/characters/mom/master/turnaround.png'),
            'blender_version':bpy.app.version_string,'source_scripts_executed':False,
            'change_notice':'A3 face/body/palette + narrower nasal base + new parted bangs/long wavy hair on original head rig. A5 fixes A4 black shader failure, widens overlapping locks, improves side coverage and waves, lifts widow peak. Stock wardrobe unchanged.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
            'hair':hair,'images':images+pose_images,'expressions':poses,'blink_sweep':sweep,
            'original_mesh_topology_unchanged':all((len(bpy.data.objects[n].data.vertices),len(bpy.data.objects[n].data.polygons))==counts for n,counts in topology.items()),
            'rig_rest_signature_before':signature,'rig_rest_signature_after':base.rig_signature(rig),
            'source_invalid_drivers':invalid,'candidate_invalid_drivers':base.invalid_drivers(bpy),
            'neutral_head_restore_error_m':float(np.linalg.norm(base.head_geometry(bpy)-neutral,axis=1).max()),
            'art_approved':False,'production_swap_allowed':False,
            'scope':'Editable face/hair study and limited blink sweep. Not full animation, hair dynamics/collision, anatomical or likeness acceptance.'}
    record['new_invalid_drivers']=sorted(set(record['candidate_invalid_drivers'])-set(invalid))
    if not record['original_mesh_topology_unchanged'] or record['rig_rest_signature_after']!=signature:raise ValueError('Unexpected source topology/rest bone changes')
    if not all(p['finite'] for p in poses+sweep):raise ValueError('Nonfinite native head geometry')
    text=bpy.data.texts.new('DOCUFLOW_A5_CHANGES.txt');text.write(record['credit']+'\nCC BY 4.0 '+record['license_url']+'\n'+record['change_notice']+'\nExperimental; hair collision/dynamics NOT accepted.\n')
    bpy.ops.file.pack_all();native=ROOT/'.cache/rain-v3/rain-mom-a5.blend';bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()),compress=True)
    record['native_artifact']={'filename':native.name,'sha256':study.sha(native),'textures_packed':True,'storage':'GitHub Actions artifact, 14 days; reconstructable from scripts.'}
    study.write(OUT/'report.json',record);board()


if __name__=='__main__':
    main()
