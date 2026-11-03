#!/usr/bin/env python3
"""R4 native still look-development. No approval or production facial rig implied."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from studio.authoring import lookdev as forms
from studio.authoring.mesh import topology
from studio.pipeline.contracts import file_hash,safe_path
from studio.tools.build_dad_refined import build as build_r3


def build(output):
    import bpy
    import bmesh
    build_r3(output/'_r3')
    bpy.context.preferences.filepaths.save_version=0
    collection=bpy.data.collections['DadBodyRefined'];collection.name='DadLookdevR4'
    rig=bpy.data.objects['DadRig']
    package=json.loads((output/'_r3/package.json').read_text())
    for obj in list(collection.objects):
        if obj.name.startswith(('DadHead','DadEye','DadEar','DadInnerEar','DadBeard','DadMouth','DadMoustache','DadNose','DadBrow','DadHair','DadScalp','DadHandR3')):
            bpy.data.objects.remove(obj,do_unlink=True)
    # Do not preserve the previous flatten-the-eyeball "blink" as a facial rig.
    removed_controls=[k for k,v in package['bindings'].items() if bpy.data.objects.get(v['object']) is None]
    package['bindings']={k:v for k,v in package['bindings'].items() if k not in removed_controls}

    def material(name,color,roughness=.45,skin=False,coat=0):
        mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=(*color,1)
        tree=mat.node_tree;bsdf=tree.nodes['Principled BSDF']
        bsdf.inputs['Base Color'].default_value=(*color,1);bsdf.inputs['Roughness'].default_value=roughness
        bsdf.inputs['IOR'].default_value=1.45
        bsdf.inputs['Coat Weight'].default_value=coat;bsdf.inputs['Coat Roughness'].default_value=.16
        if skin:
            attr=tree.nodes.new('ShaderNodeVertexColor');attr.layer_name='SurfaceColor';tree.links.new(attr.outputs['Color'],bsdf.inputs['Base Color'])
            bsdf.inputs['Subsurface Weight'].default_value=.09
            bsdf.inputs['Subsurface Radius'].default_value=(.12,.06,.03);bsdf.inputs['Subsurface Scale'].default_value=.025
        return mat

    skin=material('R4 Skin and beard vertex tint',forms.SKIN,.50,True)
    hair=material('R4 Warm brown sculpted hair',forms.HAIR,.43)
    white=material('R4 Ivory sclera',(.72,.69,.63),.23,coat=.25)
    iris=material('R4 Brown radial iris',(.155,.070,.027),.25,True,coat=.30)
    iris.node_tree.nodes['Principled BSDF'].inputs['Subsurface Weight'].default_value=0
    dark=material('R4 Recess warm dark',(.018,.006,.004),.40)
    pupil=material('R4 Pupil',(.003,.002,.001),.20,coat=.25)
    lip=material('R4 Lower lip',(.48,.225,.16),.47)
    # Fine procedural fiber relief is subtle; silhouette comes from geometry.
    for mat,scale,distance,strength in [(hair,260,.0008,.18),(skin,190,.00025,.12)]:
        tree=mat.node_tree;noise=tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale
        noise.inputs['Detail'].default_value=2
        bump=tree.nodes.new('ShaderNodeBump');bump.inputs['Distance'].default_value=distance;bump.inputs['Strength'].default_value=strength
        tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);tree.links.new(bump.outputs['Normal'],tree.nodes['Principled BSDF'].inputs['Normal'])
    # Beard roughness/fiber relief differs from skin; no uniform plastic bowl.
    tree=skin.node_tree;bsdf=tree.nodes['Principled BSDF']
    tint=next(n for n in tree.nodes if n.type=='VERTEX_COLOR')
    gray=tree.nodes.new('ShaderNodeRGBToBW');tree.links.new(tint.outputs['Color'],gray.inputs[0])
    mask=tree.nodes.new('ShaderNodeMapRange');mask.inputs['From Min'].default_value=.12;mask.inputs['From Max'].default_value=.40
    mask.inputs['To Min'].default_value=1;mask.inputs['To Max'].default_value=0;tree.links.new(gray.outputs[0],mask.inputs['Value'])
    rough=tree.nodes.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.48;rough.inputs['To Max'].default_value=.66
    tree.links.new(mask.outputs[0],rough.inputs['Value']);tree.links.new(rough.outputs[0],bsdf.inputs['Roughness'])
    sss=tree.nodes.new('ShaderNodeMapRange');sss.inputs['To Min'].default_value=.09;sss.inputs['To Max'].default_value=0
    tree.links.new(mask.outputs[0],sss.inputs['Value']);tree.links.new(sss.outputs[0],bsdf.inputs['Subsurface Weight'])
    coord=tree.nodes.new('ShaderNodeTexCoord');stretch=tree.nodes.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(2,2,.14)
    tree.links.new(coord.outputs['Generated'],stretch.inputs[0])
    fiber=tree.nodes.new('ShaderNodeTexNoise');fiber.inputs['Scale'].default_value=250;tree.links.new(stretch.outputs[0],fiber.inputs['Vector'])
    bump=tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.32;bump.inputs['Distance'].default_value=.0010
    tree.links.new(fiber.outputs['Fac'],bump.inputs['Height'])
    old_bump=next(n for n in tree.nodes if n.type=='BUMP' and n!=bump)
    tree.links.new(old_bump.outputs['Normal'],bump.inputs['Normal'])
    strength=tree.nodes.new('ShaderNodeMath');strength.operation='MULTIPLY';strength.inputs[1].default_value=.32
    tree.links.new(mask.outputs[0],strength.inputs[0]);tree.links.new(strength.outputs[0],bump.inputs['Strength']);tree.links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    receipt={'revision':'r4','scope':'static form/material review, not a deformation-ready face or approval','removed_legacy_face_controls':removed_controls,'meshes':{}}

    def add(name,mesh,mat,colors=None,subdivision=0):
        data=bpy.data.meshes.new(name+'Mesh');data.from_pydata(mesh.vertices,[],mesh.faces);data.update()
        bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
        obj=bpy.data.objects.new(name,data);collection.objects.link(obj);obj.parent=rig;data.materials.append(mat)
        for poly in data.polygons:poly.use_smooth=True
        groups={b:obj.vertex_groups.new(name=b) for b in sorted({b for w in mesh.weights for b in w})}
        for i,weights in enumerate(mesh.weights):
            for bone,w in weights.items():groups[bone].add([i],w,'REPLACE')
        mod=obj.modifiers.new('Rig skin','ARMATURE');mod.object=rig;mod.use_deform_preserve_volume=True
        if subdivision:
            sub=obj.modifiers.new('Authored surface finish','SUBSURF');sub.levels=subdivision;sub.render_levels=subdivision
        attribute=data.color_attributes.new(name='SurfaceColor',type='FLOAT_COLOR',domain='POINT')
        colors=colors if colors is not None else [forms.SKIN]*len(mesh.vertices)
        if len(colors)!=len(mesh.vertices):raise ValueError('color/vertex correspondence lost')
        for entry,color in zip(attribute.data,colors):entry.color=(*color,1)
        receipt['meshes'][name]=topology(mesh.vertices,mesh.faces)
        return obj

    mesh,colors,masks=forms.head();add('DadHeadR4',mesh,skin,colors,1)
    add('DadHairR4',forms.hair(),hair,subdivision=1)
    fibers=material('R4 Fine groom fibers',forms.HAIR,.42)
    fiber_color=fibers.node_tree.nodes.new('ShaderNodeVertexColor');fiber_color.layer_name='SurfaceColor'
    fibers.node_tree.links.new(fiber_color.outputs['Color'],fibers.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    mesh,colors=forms.hair_fibers();add('DadGroomR4',mesh,fibers,colors)
    mesh,colors=forms.beard_fibers();add('DadBeardGroomR4',mesh,fibers,colors)
    for sign,side in [(1,'R'),(-1,'L')]:
        mesh,colors=forms.ear(sign);add(f'DadEarR4{side}',mesh,skin,colors)
        cx=sign*.135
        add(f'DadScleraR4{side}',forms.eye_white(cx),white)
        mesh,colors=forms.lids(cx);add(f'DadLidsR4{side}',mesh,skin,colors)
        mesh,colors=forms.iris(cx);add(f'DadIrisR4{side}',mesh,iris,colors)
        add(f'DadPupilR4{side}',forms.pupil(cx),pupil)
        add(f'DadBrowR4{side}',forms.eyebrow(sign),hair)
        add(f'DadMoustacheR4{side}',forms.moustache(sign),hair)
        mesh,tips=forms.hand(sign);obj=add(f'DadHandR4{side}',mesh,skin)
        for probe in package['fingertip_probes']:
            if probe['id'].startswith(f'finger.{side}.'):
                probe['object']=obj.name;probe['vertex_indices']=tips[probe['id'].split('.')[-1]]
    add('DadMouthLineR4',forms.mouth_line(),dark)
    add('DadLipR4',forms.lower_lip(),lip)
    receipt['bone_count']=len(rig.data.bones)
    receipt['head_scale_xyz']=forms.HEAD_SCALE
    receipt['unweighted_vertices']=sum(not v.groups for o in collection.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers) for v in o.data.vertices)
    receipt['limitations']=['No approved likeness or feature-film quality claim.','No mouth cavity, teeth/tongue, eyelid blink/face rig or lip sync.','Surface QA and static silhouette review do not prove anatomy in all poses.']
    if receipt['unweighted_vertices']:raise ValueError('unweighted skin vertices')
    bpy.context.view_layer.update();blend=output/'dad-lookdev.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),check_existing=False)
    dependencies=['studio/tools/build_dad_blockout.py','studio/tools/build_dad_rig.py','studio/tools/build_dad_refined.py',
                  'studio/authoring/mesh.py','studio/authoring/refined_body.py','studio/authoring/lookdev.py']
    package.update(revision='r4',blend={'path':blend.relative_to(ROOT).as_posix(),'sha256':file_hash(blend),'collection':collection.name})
    package['provenance']={'authoring_script':'studio/tools/build_dad_lookdev.py','script_sha256':file_hash(__file__),'license':'project-original',
                           'dependencies':[{'path':p,'sha256':file_hash(ROOT/p)} for p in dependencies]}
    (output/'package.json').write_text(json.dumps(package,indent=2)+'\n')
    (output/'model-audit.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('DAD_LOOKDEV_R4',output/'package.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='studio/out/dad-lookdev-r4')
    args=parser.parse_args();build(safe_path(ROOT,args.output))
