"""R12: reuse exact R11 packed maps, never rebake paint on a reshaped mesh.

Only images are appended from the verified downloaded R11 library. No old rig,
geometry, scene or embedded scripts are loaded into the new reconstruction.
"""
import copy,hashlib,json
from pathlib import Path
import numpy as np
import mom_face_finish_r7 as prior
from mom_face_paint_r11 import render_uv,atlas_domain,paint_samples,saved_material_state,linear,smoothstep,group_sum
from mom_face_anatomy_r12 import ear_mask,finish_ears
ROOT=Path(__file__).resolve().parents[2]

def load_held_maps(bpy):
    report_path=ROOT/'studio/reviews/mom-head-form-r11/report.json'
    report=json.loads(report_path.read_text());bundle=ROOT/'.cache/r12-r11-material'
    paths=list(bundle.rglob('mom-head-form-r11.blend'))
    if len(paths)!=1:raise ValueError('Expected actual downloaded R11 material library')
    native=paths[0];digest=hashlib.sha256(native.read_bytes()).hexdigest()
    if digest!=report['native_artifact']['sha256']:raise ValueError('R11 downloaded library hash mismatch')
    archived=bundle/'studio/reviews/mom-head-form-r11/report.json'
    if archived.read_bytes()!=report_path.read_bytes():raise ValueError('R11 archived receipt differs')
    maps=report['saved_material_state']['active_original_uv_maps']
    names=[maps[socket]['image'] for socket in ('Base Color','Roughness')]
    with bpy.data.libraries.load(str(native.resolve()),link=False) as (available,loaded):
        if not all(name in available.images for name in names):raise ValueError('Packed R11 maps missing')
        loaded.images=names
    images=loaded.images
    for image,socket in zip(images,('Base Color','Roughness')):
        if image is None or not image.packed_file:raise ValueError('Appended map is not packed')
        if hashlib.sha256(bytes(image.packed_file.data)).hexdigest()!=maps[socket]['packed_file_sha256']:raise ValueError('Appended EXR bytes changed')
        if image.colorspace_settings.name!='Non-Color':raise ValueError('Appended EXR colorspace changed')
    return report,images,{'source_run':41787400559,'downloaded_binary_sha256':digest,
        'method':'Append only two exact packed images from actual published R11 blend. No geometry-dependent rebake, rig/scene import or embedded script execution.'}

def apply_palette(bpy,data,palette):
    report,images,reuse=load_held_maps(bpy)
    if palette!=report['materials']['palette_srgb']:raise ValueError('R12 is not a palette change')
    record=prior.apply_palette(bpy,data,palette)
    mesh=bpy.data.objects['GEO-rain-head'].data;uv_layer=render_uv(mesh)
    uv=np.empty(len(uv_layer.data)*2,dtype=np.float32);uv_layer.data.foreach_get('uv',uv);uv=uv.reshape(-1,2)
    domain=atlas_domain(uv);uv_sha=hashlib.sha256(uv.tobytes()).hexdigest()
    if uv_sha!=report['original_uv_sha256'] or domain!=report['materials']['uv_paint']['original_uv_domain']:raise ValueError('Held texture UV/domain mismatch')
    layout={'render_uv':uv_layer.name,'domain':domain,'layers':[{'name':l.name,'active_render':l.active_render} for l in mesh.uv_layers],
            'original_uv_sha256':uv_sha,'method':'Original UV coordinates retained; exact packed R11 maps appended, no rebake or wrapping.'}
    (ROOT/'studio/reviews/mom-head-form-r12/original-uv-layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    tree=mesh.materials[0].node_tree;shader=tree.nodes['Principled BSDF']
    uv_node=tree.nodes.new('ShaderNodeUVMap');uv_node.uv_map=uv_layer.name;uv_node.name='Mom R12 original UV'
    subtract=tree.nodes.new('ShaderNodeVectorMath');subtract.operation='SUBTRACT';subtract.inputs[1].default_value=(*domain['origin'],0)
    scale=tree.nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(1/domain['extent'],1/domain['extent'],1)
    tree.links.new(uv_node.outputs['UV'],subtract.inputs[0]);tree.links.new(subtract.outputs['Vector'],scale.inputs[0])
    for image,socket in zip(images,('Base Color','Roughness')):
        node=tree.nodes.new('ShaderNodeTexImage');node.image=image;node.name='Mom R12 held '+socket;node.interpolation='Linear';node.extension='EXTEND'
        tree.links.new(scale.outputs['Vector'],node.inputs['Vector'])
        if socket=='Base Color':tree.links.new(node.outputs['Color'],shader.inputs[socket])
        else:
            separate=tree.nodes.new('ShaderNodeSeparateColor');separate.mode='RGB'
            tree.links.new(node.outputs['Color'],separate.inputs['Color'])
            for channel,prop in (('Red','Roughness'),('Green','Coat Weight'),('Blue','Coat Roughness')):tree.links.new(separate.outputs[channel],shader.inputs[prop])
    receipt=copy.deepcopy(report['materials']['uv_paint']);receipt['reuse']=reuse
    record.update({'uv_paint':receipt,'held_material_library':reuse,'head_albedo_attribute_is_fallback':True,
                   'method':'Exact original-UV albedo/PBR bytes from downloaded R11 artifact, not a new face-color pass.'})
    return record
