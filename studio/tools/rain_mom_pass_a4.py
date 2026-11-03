#!/usr/bin/env python3
"""A4: actual Rain A3 face + editable long, parted hair study (not approved).

This is hair authoring on the acquired Rain rig, NOT a replacement character.
All source objects survive. Stock ponytail/strand/band are hidden, not deleted.
New clumps use the existing DEF-Head and source head lattice; no dynamics claim.
"""
from __future__ import annotations

import math
import numpy as np
import rain_mom_pass_a3 as face

base=face.base
controls=face.controls
study=face.study
ROOT=face.ROOT
OUT=ROOT/'studio/reviews/rain-mom-a4'


def catmull_rom(points, samples=64):
    p=np.asarray(points,dtype=np.float64)
    extended=np.vstack([2*p[0]-p[1],p,2*p[-1]-p[-2]])
    t=np.linspace(0,len(p)-1,samples)
    segment=np.minimum(t.astype(int),len(p)-2)
    u=(t-segment)[:,None]
    a,b,c,d=[extended[segment+offset] for offset in range(4)]
    return .5*((2*b)+(-a+c)*u+(2*a-5*b+4*c-d)*u*u+(-a+3*b-3*c+d)*u*u*u)


def loft_geometry(path,widths,depths,normal,samples=64,sides=24):
    """Closed broad hair clump, not a bundle of round cylinder strands.

    Smooth closed elliptical sections carry shallow longitudinal ridges. Width
    and depth are full dimensions. Controls/UVs remain editable in native Blender.
    """
    centers=catmull_rom(path,samples)
    index=np.linspace(0,len(widths)-1,samples)
    width=np.interp(index,np.arange(len(widths)),widths)
    depth=np.interp(index,np.arange(len(depths)),depths)
    tangent=np.gradient(centers,axis=0)
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    reference=np.asarray(normal,dtype=np.float64)
    wide=np.cross(tangent,reference)
    wide/=np.linalg.norm(wide,axis=1)[:,None]
    outward=np.cross(wide,tangent)
    outward/=np.linalg.norm(outward,axis=1)[:,None]
    points=[]
    for row in range(samples):
        for column in range(sides):
            angle=2*math.pi*column/sides
            ridge=1+.055*math.cos(10*angle)
            p=centers[row]+.5*width[row]*math.cos(angle)*wide[row]+.5*depth[row]*math.sin(angle)*ridge*outward[row]
            points.append(tuple(p))
    faces=[]
    for row in range(samples-1):
        for col in range(sides):
            a=row*sides+col;b=row*sides+(col+1)%sides
            faces.append((a,a+sides,b+sides,b))
    faces.append(tuple(range(sides)))
    faces.append(tuple((samples-1)*sides+i for i in reversed(range(sides))))
    return points,faces


def hair_material(bpy):
    # Keep source textures/anisotropic graph, moderate the stark white highlights.
    material=bpy.data.materials['MAT-rain.hair'].copy();material.name='MAT-mom.hair-a4'
    for node in material.node_tree.nodes:
        if node.type!='BSDF_PRINCIPLED':continue
        for name,value in (('Specular IOR Level',.24),('Roughness',.56)):
            socket=node.inputs[name]
            for link in list(socket.links):material.node_tree.links.remove(link)
            socket.default_value=value
    return material


def add_clump(bpy,rig,template,material,name,path,widths,depths,normal):
    points,faces=loft_geometry(path,widths,depths,normal)
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(points,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    uv=mesh.uv_layers.new(name='UVMap')
    sides=24;samples=64
    for polygon in mesh.polygons:
        polygon.use_smooth=True
        for loop_index in polygon.loop_indices:
            vertex=mesh.loops[loop_index].vertex_index
            uv.data[loop_index].uv=((vertex%sides)/sides,(vertex//sides)/(samples-1))
    # Preserve any named source color attributes used by the reused hair shader.
    for attribute in template.data.color_attributes:
        if attribute.domain not in ('CORNER','POINT') or attribute.data_type not in ('FLOAT_COLOR','BYTE_COLOR'):continue
        values=np.empty(len(attribute.data)*4,dtype=np.float32);attribute.data.foreach_get('color',values)
        average=values.reshape(-1,4).mean(axis=0)
        target=mesh.color_attributes.new(name=attribute.name,type='FLOAT_COLOR',domain='CORNER')
        target.data.foreach_set('color',np.tile(average,(len(mesh.loops),1)).ravel())
    group=obj.vertex_groups.new(name='DEF-Head');group.add(list(range(len(points))),1,'REPLACE')
    arm=obj.modifiers.new('Original Rain head rig','ARMATURE');arm.object=rig;arm.use_deform_preserve_volume=True
    for source in template.modifiers:
        if source.type=='LATTICE':
            mod=obj.modifiers.new(source.name,'LATTICE');mod.object=source.object;mod.strength=source.strength
    subdiv=obj.modifiers.new('Hair surface','SUBSURF');subdiv.levels=1;subdiv.render_levels=2
    return {'object':name,'vertices':len(points),'polygons':len(faces),'bone':'DEF-Head','control_points':path,'widths_m':widths,'depths_m':depths}


def author_hair(bpy,rig):
    template=bpy.data.objects['GEO-rain-hair_main']
    material=hair_material(bpy)
    template.data.materials.clear();template.data.materials.append(material)
    hidden=[]
    for name in ('GEO-rain-hair_ponytail','GEO-rain-hair_strand','GEO-rain-hairband'):
        bpy.data.objects[name].hide_render=True;hidden.append(name)
    records=[]
    # Back/side curtain: overlapping sculptural locks, shoulder-length soft waves.
    for i,angle in enumerate(np.linspace(-110,110,9)):
        radians=math.radians(float(angle))
        heights=[1.605,1.55,1.47,1.38,1.29,1.205,1.175]
        radii=[.078,.108,.125,.132,.143,.149,.128]
        phase=i*.9
        path=[]
        for k,(z,radius) in enumerate(zip(heights,radii)):
            ripple=.008*math.sin(k*1.9+phase)*min(k/2,1)
            a=radians+.045*math.sin(k*1.7+phase)
            path.append(((radius+ripple)*math.sin(a),.012+(radius+ripple)*math.cos(a),z+.004*math.sin(phase)*min(k/3,1)))
        records.append(add_clump(bpy,rig,template,material,f'GEO-mom-a4-curtain-{i:02}',path,
                                 [.045,.058,.062,.064,.060,.045,.003],
                                 [.014,.023,.025,.026,.025,.020,.003],
                                 (math.sin(radians),math.cos(radians),0)))
    # Two center-parted sweeping bangs continuing into face-framing waves.
    for sign in (-1,1):
        path=[(sign*.005,-.081,1.640),(sign*.034,-.139,1.601),(sign*.079,-.155,1.553),
              (sign*.116,-.128,1.486),(sign*.131,-.088,1.408),(sign*.141,-.067,1.327),
              (sign*.133,-.049,1.254),(sign*.153,-.020,1.204)]
        records.append(add_clump(bpy,rig,template,material,f'GEO-mom-a4-bang-{sign:+}',path,
                                 [.009,.035,.046,.042,.043,.046,.033,.003],
                                 [.010,.021,.022,.023,.026,.026,.020,.003],(0,-1,0)))
    bpy.context.view_layer.update()
    return {'added_clumps':records,'hidden_not_deleted':hidden,'stock_crown_retained':template.name,
            'binding':'Existing DEF-Head + source lattice. Rigid head-follow, not shoulder collision/dynamics certification.'}


def refine_nasal_base(bpy):
    obj=bpy.data.objects['GEO-rain-head'];world=obj.matrix_world.copy();inv=world.inverted()
    for key in obj.data.shape_keys.key_blocks:
        p=base.transform_points(base.point_array(key.data),world)
        x,y,z=p.T
        mask=np.exp(-((x/.050)**6+((z-1.424)/.028)**4))*face.smoothstep(-.025,-.080,y)
        p[:,0]-=.16*x*mask
        key.data.foreach_set('co',base.transform_points(p,inv).ravel())
    obj.data.vertices.foreach_set('co',base.point_array(obj.data.shape_keys.key_blocks[0].data).ravel())
    obj.data.shape_keys.update_tag();obj.data.update();bpy.context.view_layer.update()


def render_poses(bpy,rig,matrices,scene,camera):
    neutral=base.head_geometry(bpy);images=[];poses=[]
    for label in ('blink','smile'):
        controls.restore(bpy,rig,matrices)
        actuators=face.set_blink(bpy,rig,1) if label=='blink' else [controls.set_key_via_actuator(bpy,rig,f'Smile.{s}',.65,'ACT-Lips') for s in ('L','R')]
        p=base.head_geometry(bpy)
        poses.append({'pose':label,'actuators':actuators,'finite':bool(np.isfinite(p).all()),'max_displacement_m':float(np.linalg.norm(p-neutral,axis=1).max())})
        images.append(study.render(bpy,scene,camera,OUT/f'candidate-{label}.png',(0,-4,1.5),(0,0,1.45),.60))
    controls.restore(bpy,rig,matrices)
    return images,poses


def board():
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(1800,940),'#202b36');draw=ImageDraw.Draw(canvas)
    panels=[('REFERENCE MOM',ROOT/'studio/characters/mom/master/turnaround.png',(90,205,275,495)),
            ('PREVIOUS A3',ROOT/'studio/reviews/rain-mom-a3/candidate-face.png',(160,95,610,760)),
            ('CANDIDATE A4',OUT/'candidate-face.png',(160,95,610,760))]
    for i,(label,path,crop) in enumerate(panels):
        with Image.open(path) as image:
            panel=image.crop(crop);scale=min(570/panel.width,720/panel.height)
            panel=panel.resize((round(panel.width*scale),round(panel.height*scale)),Image.Resampling.LANCZOS)
            canvas.paste(panel,(i*600+(600-panel.width)//2,70+(720-panel.height)//2))
        draw.text((i*600+24,24),label,fill='white',font_size=26)
    draw.text((24,825),'Actual Rain model + authored hair. Same A3/A4 camera/light. Reference is 2D art, not a matched render.',fill='white',font_size=21)
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
    base.change_meshes(bpy);base.change_materials(bpy);face.change_face(bpy);face.complexion(bpy)
    refine_nasal_base(bpy)
    hair=author_hair(bpy,rig)
    scene,camera=study.stage(bpy);neutral=base.head_geometry(bpy)
    images=[study.render(bpy,scene,camera,OUT/'candidate-face.png',(0,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-three-quarter.png',(2.2,-4,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-profile.png',(4,0,1.5),(0,0,1.45),.60),
            study.render(bpy,scene,camera,OUT/'candidate-full.png',(0,-4,1.05),(0,0,.85),1.95)]
    pose_images,poses=render_poses(bpy,rig,matrices,scene,camera)
    record={'revision':'rain-mom-a4','source_blend_sha256':study.sha(source),'source_url':study.URL,'archive_sha256':study.ARCHIVE_SHA,
            'scripts':{n:study.sha(ROOT/'studio/tools'/n) for n in ('rain_study.py','rain_mom_pass.py','rain_mom_pass_a2.py','rain_mom_pass_a3.py','rain_mom_pass_a4.py')},
            'reference_sha256':study.sha(ROOT/'studio/characters/mom/master/turnaround.png'),
            'blender_version':bpy.app.version_string,'source_scripts_executed':False,
            'change_notice':'A3 face/body/palette + narrower nasal base + new parted bangs/long wavy hair clumps bound to original Rain head rig; original crown retained, ponytail/strand/band hidden, original wardrobe unchanged.',
            'credit':'Rain Rig (CC) Blender Foundation | studio.blender.org','license':'CC-BY-4.0','license_url':'https://creativecommons.org/licenses/by/4.0/',
            'hair':hair,'images':images+pose_images,'expressions':poses,
            'original_mesh_topology_unchanged':all((len(bpy.data.objects[n].data.vertices),len(bpy.data.objects[n].data.polygons))==counts for n,counts in topology.items()),
            'rig_rest_signature_before':signature,'rig_rest_signature_after':base.rig_signature(rig),
            'source_invalid_drivers':invalid,'candidate_invalid_drivers':base.invalid_drivers(bpy),
            'neutral_head_restore_error_m':float(np.linalg.norm(base.head_geometry(bpy)-neutral,axis=1).max()),
            'art_approved':False,'production_swap_allowed':False,
            'scope':'Editable face/hair look study; no full animation, hair dynamics, collision, anatomical or likeness acceptance.'}
    record['new_invalid_drivers']=sorted(set(record['candidate_invalid_drivers'])-set(invalid))
    if not record['original_mesh_topology_unchanged'] or record['rig_rest_signature_after']!=signature:
        raise ValueError('Unexpected source topology/rest bone changes')
    if not all(p['finite'] for p in poses):raise ValueError('Nonfinite native head geometry')
    text=bpy.data.texts.new('DOCUFLOW_A4_CHANGES.txt');text.write(record['credit']+'\nCC BY 4.0 '+record['license_url']+'\n'+record['change_notice']+'\nExperimental. Hair follows head; no dynamics/collision acceptance.\n')
    bpy.ops.file.pack_all();native=ROOT/'.cache/rain-v3/rain-mom-a4.blend';bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()),compress=True)
    record['native_artifact']={'filename':native.name,'sha256':study.sha(native),'textures_packed':True,'storage':'GitHub Actions artifact, 14 days; reconstructable from scripts.'}
    study.write(OUT/'report.json',record);board()


if __name__=='__main__':
    main()
