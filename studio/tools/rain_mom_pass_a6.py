#!/usr/bin/env python3
"""A6: photo-guided artistic refinement, still stylized Rain, not a scan/identity fit.

PRIVATE PHOTO POLICY: this program never opens personal photos, screenshot
uploads or studio/reference. Those guide manual authoring locally only; no image
or photo hash is packed/published. Public review board uses existing canonical art.
A1-A5 evidence/recipes and all original rig rest/weights/topology are preserved.
"""
from __future__ import annotations

import math
import numpy as np
import rain_mom_pass_a5 as previous

prior=previous.prior
face=previous.face
base=previous.base
controls=previous.controls
study=previous.study
ROOT=previous.ROOT
OUT=ROOT/'studio/reviews/rain-mom-a6'


def cap_geometry(rings=28,sides=96):
    """Single coherent parted crown; intentionally open hairline, solidified in DCC.

    No intersecting legacy crown/loft root caps. Hairline higher at the front,
    lower at sides/back. A subtle center channel, not a row of separate nubs.
    """
    vertices=[(0,.008,1.6555)]
    uv=[(.5,0)]
    for ring in range(1,rings+1):
        t=ring/rings
        for column in range(sides):
            phi=2*math.pi*column/sides
            maximum=.80+.65*(1-math.cos(phi))
            theta=t*maximum
            x=.129*math.sin(theta)*math.sin(phi)
            y=.008-.137*math.sin(theta)*math.cos(phi)
            z=1.49+.168*math.cos(theta)
            z-=.0025*math.exp(-(x/.006)**2)*float(face.smoothstep(1.57,1.63,z))
            vertices.append((x,y,z));uv.append((column/sides,t))
    polygons=[]
    for col in range(sides):
        polygons.append((0,1+col,1+(col+1)%sides))
    for ring in range(rings-1):
        for col in range(sides):
            a=1+ring*sides+col;b=1+ring*sides+(col+1)%sides
            polygons.append((a,a+sides,b+sides,b))
    return vertices,polygons,uv


def face_refinement(points,head=True):
    p=np.asarray(points,dtype=np.float64);q=p.copy();x,y,z=p.T
    front=face.smoothstep(-.025,-.080,y)
    # Relax visible upper eyelid aperture, not a blanket eyeball/iris shrink.
    upper=np.exp(-(((np.abs(x)-.047)/.032)**4+((z-1.489)/.013)**4))*front
    lower=np.exp(-(((np.abs(x)-.047)/.032)**4+((z-1.458)/.010)**4))*front
    q[:,2]-=.0018*upper;q[:,2]+=.0005*lower
    if head:
        cheeks=np.exp(-((z-1.425)/.032)**2)*np.exp(-((np.abs(x)-.065)/.035)**4)*front
        q[:,0]+=.025*x*cheeks
        mouth=np.exp(-((x/.031)**6+((z-1.391)/.013)**4))*front
        q[:,2]+=.08*(z-1.391)*mouth
        nose=np.exp(-((x/.037)**6+((z-1.425)/.023)**4))*front
        q[:,0]+=.03*x*nose
    return q


def refine_face(bpy):
    records=[]
    for name in ('GEO-rain-head','GEO-rain-eyelashes'):
        obj=bpy.data.objects[name];world=obj.matrix_world.copy();inv=world.inverted()
        keys=obj.data.shape_keys
        blocks=[k.data for k in keys.key_blocks] if keys else [obj.data.vertices]
        maximum=0
        for block in blocks:
            p=base.transform_points(base.point_array(block),world)
            q=face_refinement(p,head=name=='GEO-rain-head')
            maximum=max(maximum,float(np.linalg.norm(q-p,axis=1).max()))
            block.foreach_set('co',base.transform_points(q,inv).ravel())
        if keys:
            obj.data.vertices.foreach_set('co',base.point_array(keys.key_blocks[0].data).ravel());keys.update_tag()
        obj.data.update()
        records.append({'object':name,'corrective_blocks_transported':len(blocks) if keys else 0,'maximum_additional_change_m':maximum})
    bpy.context.view_layer.update()
    return records


def revise_material(material):
    material.name='MAT-mom.hair-a6'
    nodes=material.node_tree.nodes
    for node in nodes:
        if node.type=='VALTORGB':
            node.color_ramp.elements[0].color=base.linear_color('#6D513D')
            node.color_ramp.elements[-1].color=base.linear_color('#927254')
        elif node.type=='BSDF_PRINCIPLED':
            node.inputs['Roughness'].default_value=.58
            node.inputs['Specular IOR Level'].default_value=.22
        elif node.type=='BUMP':
            node.inputs['Strength'].default_value=.045
            node.inputs['Distance'].default_value=.0004
    return material


def bind_cap(bpy,rig,template,material):
    points,polygons,uvs=cap_geometry()
    mesh=bpy.data.meshes.new('Mom A6 coherent parted crown');mesh.from_pydata(points,[],polygons);mesh.update()
    obj=bpy.data.objects.new('GEO-mom-a6-crown',mesh);bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    layer=mesh.uv_layers.new(name='UVMap')
    for polygon in mesh.polygons:
        polygon.use_smooth=True
        for li in polygon.loop_indices:layer.data[li].uv=uvs[mesh.loops[li].vertex_index]
    group=obj.vertex_groups.new(name='DEF-Head');group.add(list(range(len(points))),1,'REPLACE')
    mod=obj.modifiers.new('Original Rain head rig','ARMATURE');mod.object=rig;mod.use_deform_preserve_volume=True
    for old in template.modifiers:
        if old.type=='LATTICE':
            mod=obj.modifiers.new(old.name,'LATTICE');mod.object=old.object;mod.strength=old.strength
    mod=obj.modifiers.new('Crown shell','SOLIDIFY');mod.thickness=.002;mod.offset=-1
    mod=obj.modifiers.new('Crown surface','SUBSURF');mod.levels=1;mod.render_levels=2
    return obj


def refine_groom(bpy,rig):
    record=previous.revise_groom(bpy,rig)
    template=bpy.data.objects['GEO-rain-hair_main']
    material=revise_material(template.data.materials[0])
    template.hide_render=True # preserved, not destroyed or presented as unified
    crown=bind_cap(bpy,rig,template,material)
    for item in record['added_clumps']:
        path=np.asarray(item['control_points'],dtype=float)
        widths=np.asarray(item['widths_m'],dtype=float)
        depths=np.asarray(item['depths_m'],dtype=float)
        if 'curtain' in item['object']:
            angle=math.atan2(path[0,0],path[0,1]-.012)
            path[0]=(.068*math.sin(angle),.008+.068*math.cos(angle),1.620)
            phase=int(item['object'].rsplit('-',1)[1])*.9
            # Modest asymmetric side flow; retain overlap instead of making gaps.
            for k in range(2,len(path)):
                offset=.005*math.sin(k*1.9+phase)
                path[k,0]+=offset*math.cos(angle);path[k,1]-=offset*math.sin(angle)
            normal=(math.sin(angle),math.cos(angle),0)
        else:
            sign=-1 if '-1' in item['object'] else 1
            path[0]=(sign*.004,-.024,1.652)
            path[1]=(sign*.032,-.124,1.595)
            path[2]=(sign*(.076 if sign<0 else .080),-.151,1.533 if sign<0 else 1.540)
            widths*=.88;depths*=.90
            # Less massive curtain bangs; taper their tips, keep eye corners clear.
            path[-2,0]*=.97 if sign<0 else 1.02
            normal=(0,-1,0)
        points,_=prior.loft_geometry(path,widths,depths,normal)
        obj=bpy.data.objects[item['object']];obj.data.vertices.foreach_set('co',np.asarray(points).ravel());obj.data.update()
        item.update({'control_points':path.tolist(),'widths_m':widths.tolist(),'depths_m':depths.tolist()})
    # Small face-framing wisps, not a solid fringe painted over the eyes.
    wisps=[]
    for sign in (-1,1):
        path=[(sign*.005,-.064,1.631),(sign*.020,-.132,1.590),(sign*.038,-.145,1.548)]
        wisps.append(prior.add_clump(bpy,rig,template,material,f'GEO-mom-a6-wisp-{sign:+}',path,
                                    [.004,.007,.0008],[.003,.004,.001],(0,-1,0)))
    bpy.context.view_layer.update()
    record.update({'legacy_crown_hidden_not_deleted':template.name,'new_coherent_crown':crown.name,
                   'wisps':wisps,'material':'Independent normal Principled BSDF; darker muted brown palette, lower bump/specular. No private image textures.',
                   'changes_since_a5':'Unified scalp/part instead of layered source crown; buried clump roots, slimmer asymmetric bangs, small wisps, softer fiber texture.'})
    return record


def review_board():
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(1800,940),'#202b36');draw=ImageDraw.Draw(canvas)
    panels=[('CANONICAL STYLE TARGET',ROOT/'studio/characters/mom/master/turnaround.png',(90,205,275,495)),
            ('PREVIOUS A5',ROOT/'studio/reviews/rain-mom-a5/candidate-face.png',(160,95,610,760)),
            ('CURRENT A6 STUDY',OUT/'candidate-face.png',(160,95,610,760))]
    for i,(label,path,crop) in enumerate(panels):
        with Image.open(path) as image:
            panel=image.crop(crop);scale=min(570/panel.width,720/panel.height)
            panel=panel.resize((round(panel.width*scale),round(panel.height*scale)),Image.Resampling.LANCZOS)
            canvas.paste(panel,(i*600+(600-panel.width)//2,70+(720-panel.height)//2))
        draw.text((i*600+24,24),label,fill='white',font_size=24)
    draw.text((24,825),'A5/A6 same native camera/light. Private photos are NOT included in this board, Git or CI.',fill='white',font_size=21)
    draw.text((24,870),'Rain Rig (CC) Blender Foundation | studio.blender.org - modified CC BY 4.0. Study, not approved.',fill='white',font_size=21)
    canvas.save(OUT/'comparison-reference.png')


def render_poses(bpy,rig,matrices,scene,camera):
    neutral=base.head_geometry(bpy);images=[];poses=[];sweep=[]
    for label in ('blink','smile'):
        controls.restore(bpy,rig,matrices)
        actuators=face.set_blink(bpy,rig,1) if label=='blink' else [controls.set_key_via_actuator(bpy,rig,f'Smile.{s}',.65,'ACT-Lips') for s in ('L','R')]
        p=base.head_geometry(bpy)
        poses.append({'pose':label,'actuators':actuators,'finite':bool(np.isfinite(p).all()),'max_displacement_m':float(np.linalg.norm(p-neutral,axis=1).max())})
        images.append(study.render(bpy,scene,camera,OUT/f'candidate-{label}.png',(0,-4,1.5),(0,0,1.45),.60))
    for value in (0,.25,.5,.75,1,.75,.5,.25,0):
        controls.restore(bpy,rig,matrices);face.set_blink(bpy,rig,value);p=base.head_geometry(bpy)
        sweep.append({'amplitude':value,'finite':bool(np.isfinite(p).all()),'max_displacement_m':float(np.linalg.norm(p-neutral,axis=1).max())})
    controls.restore(bpy,rig,matrices)
    return images,poses,sweep


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
    edits=refine_face(bpy);hair=refine_groom(bpy,rig)
    scene,camera=study.stage(bpy);neutral=base.head_geometry(bpy)
    images=[study.render(bpy,scene,camera,OUT/'candidate-face.png',(0,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-three-quarter.png',(2.2,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-profile.png',(4,0,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-full.png',(0,-4,1.05),(0,0,.85),1.95)]
    pose_images,poses,sweep=render_poses(bpy,rig,matrices,scene,camera)
    record={'revision':'rain-mom-a6','source_blend_sha256':study.sha(source),'source_url':study.URL,'archive_sha256':study.ARCHIVE_SHA,
            'scripts':{n:study.sha(ROOT/'studio/tools'/n) for n in ('rain_study.py','rain_mom_pass.py','rain_mom_pass_a2.py','rain_mom_pass_a3.py','rain_mom_pass_a4.py','rain_mom_pass_a5.py','rain_mom_pass_a6.py')},
            'canonical_style_reference_sha256':study.sha(ROOT/'studio/characters/mom/master/turnaround.png'),
            'private_reference_policy':'Personal photos guide manual authoring locally only; no private images, crops, names, paths or hashes are read/packed/published by this build.',
            'blender_version':bpy.app.version_string,'source_scripts_executed':False,
            'change_notice':'A5 Rain face/body retained; relaxed upper-lid aperture, slightly fuller lips/cheeks/ala, coherent new parted crown, slimmer asymmetric bangs/wisps, muted darker brown hair and softer fiber shading. Source crown hidden, not deleted. Stock wardrobe unchanged.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
            'face_edits':edits,'hair':hair,'images':images+pose_images,'expressions':poses,'blink_sweep':sweep,
            'original_mesh_topology_unchanged':all((len(bpy.data.objects[n].data.vertices),len(bpy.data.objects[n].data.polygons))==counts for n,counts in topology.items()),
            'rig_rest_signature_before':signature,'rig_rest_signature_after':base.rig_signature(rig),
            'source_invalid_drivers':invalid,'candidate_invalid_drivers':base.invalid_drivers(bpy),
            'neutral_head_restore_error_m':float(np.linalg.norm(base.head_geometry(bpy)-neutral,axis=1).max()),
            'art_approved':False,'production_swap_allowed':False,
            'scope':'Photo-guided manual stylized refinement + limited native expressions. No exact likeness, full animation, shoulder collision/hair dynamics or anatomical approval.'}
    record['new_invalid_drivers']=sorted(set(record['candidate_invalid_drivers'])-set(invalid))
    if not record['original_mesh_topology_unchanged'] or record['rig_rest_signature_after']!=signature:raise ValueError('Unexpected source topology/rest bone changes')
    if not all(p['finite'] for p in poses+sweep):raise ValueError('Nonfinite native head geometry')
    text=bpy.data.texts.new('DOCUFLOW_A6_CHANGES.txt');text.write(record['credit']+'\nCC BY 4.0 '+record['license_url']+'\n'+record['change_notice']+'\nExperimental. No private photo textures or exact likeness certification.\n')
    bpy.ops.file.pack_all();native=ROOT/'.cache/rain-v3/rain-mom-a6.blend';bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()),compress=True)
    record['native_artifact']={'filename':native.name,'sha256':study.sha(native),'textures_packed':True,'storage':'GitHub Actions artifact, 14 days; reconstructable from scripts.'}
    study.write(OUT/'report.json',record);review_board()


if __name__=='__main__':
    main()
