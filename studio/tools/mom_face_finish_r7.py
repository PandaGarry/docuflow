"""Final current color correction: retain R6 upper border, restore lower vermilion.

R6 actual frame under-colors the lower lip. Use the original attached lip weights
there, retaining the explicit upper boundary. Roughness gets a separate FLOAT
attribute; color alpha stays one. No render repaint or geometry replacement.
"""
import hashlib
import numpy as np
import mom_face_finish_r5 as original_color
import mom_face_finish_r6 as prior
from mom_face_finish_r6 import smoothstep,group_sum,ear_mask,finish_ears,linear


def complexion_colors(data,palette):
    colors,lip=prior.complexion_colors(data,palette)
    _,original=original_color.complexion_colors(data,palette)
    p=np.asarray(data['basis_vertices']);z=p[:,2]
    lower=smoothstep(1.3930,1.3870,z)*original
    colors[:,:3]=colors[:,:3]*(1-lower[:,None])+linear(palette['lower_lip'])*lower[:,None]
    lip=np.maximum(lip,lower)
    colors[:,3]=1
    return colors,lip


def apply_palette(bpy,data,palette):
    record=prior.apply_palette(bpy,data,palette)
    mesh=bpy.data.objects['GEO-rain-head'].data
    colors,lip=complexion_colors(data,palette)
    attr=mesh.color_attributes['Mom R6 attached albedo'];attr.data.foreach_set('color',colors.ravel())
    roughness=np.asarray(.47-.08*lip,dtype=np.float32)
    rough=mesh.attributes.new(name='Mom R7 roughness',type='FLOAT',domain='POINT')
    rough.data.foreach_set('value',roughness)
    mat=mesh.materials[0];tree=mat.node_tree
    node=tree.nodes.new('ShaderNodeAttribute');node.attribute_name=rough.name;node.name='Mom R7 separate lip roughness'
    tree.links.new(node.outputs['Fac'],tree.nodes['Principled BSDF'].inputs['Roughness'])
    record.update({'head_albedo_sha256':hashlib.sha256(colors.tobytes()).hexdigest(),
                   'attribute_alpha_usage':'one/opaque; roughness is a separate FLOAT mesh attribute',
                   'roughness_attribute':rough.name,'roughness_sha256':hashlib.sha256(roughness.tobytes()).hexdigest(),
                   'lip_mask_nonzero_vertices':int((lip>.01).sum()),
                   'review_correction':'Retain R6 explicit upper lip boundary; restore lower lip color with original deform-weight mask below seam. Separate lip roughness .39 from skin .47, no color-alpha reuse.'})
    return record


def saved_material_state(bpy):
    state=prior.saved_material_state(bpy)
    data=bpy.data.objects['GEO-rain-head'].data.attributes['Mom R7 roughness'].data
    rough=np.empty(len(data),dtype=np.float32);data.foreach_get('value',rough)
    state['roughness_attribute_sha256']=hashlib.sha256(rough.tobytes()).hexdigest()
    state['roughness_attribute_points']=len(data)
    shader=bpy.data.objects['GEO-rain-head'].data.materials[0].node_tree.nodes['Principled BSDF']
    link=shader.inputs['Roughness'].links[0]
    state['roughness_link_attribute']=link.from_node.attribute_name
    return state
