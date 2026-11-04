"""R5 original-mesh ear adjustment and attached canonical palette (not image paint).

Pure numpy helpers are independently testable. Ear mask is frozen on original
indexed anatomy; the same affine/weight map is applied to all original keys.
"""
import hashlib
import numpy as np


def smoothstep(low,high,x):
    t=np.clip((np.asarray(x)-low)/(high-low),0,1)
    return t*t*(3-2*t)


def group_sum(data,prefixes):
    names=data['vertex_group_names']
    return np.array([sum(weight for index,weight in row if any(names[index].startswith(p) for p in prefixes)) for row in data['vertex_weights']])


def ear_mask(data):
    p=np.asarray(data['basis_vertices']);ear=group_sum(data,('DEF-Ear_',))
    # Source ear weights extend onto skull: lateral gate protects that region.
    return np.clip(ear,0,1)*smoothstep(.091,.113,np.abs(p[:,0]))


def finish_ears(points,data,settings):
    p=np.asarray(points,dtype=float);q=p.copy();w=ear_mask(data)
    pivot=np.array(settings['pivot_m'],dtype=float)
    pivots=np.tile(pivot,(len(p),1));pivots[:,0]*=np.sign(np.asarray(data['basis_vertices'])[:,0])
    scaled=pivots+(p-pivots)*np.array(settings['scale_xyz'])
    scaled[:,0]-=np.sign(pivots[:,0])*settings['lateral_tuck_m']
    scaled[:,1]+=settings['posterior_tuck_m']
    return p+w[:,None]*(scaled-p)


def linear(hex_value):
    c=np.array([int(hex_value[i:i+2],16)/255 for i in (1,3,5)])
    return np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)


def complexion_colors(data,palette):
    p=np.asarray(data['basis_vertices']);x,y,z=p.T
    top=group_sum(data,('DEF-Lip_Top_',));bottom=group_sum(data,('DEF-Lip_Bot_',))
    # Actual lip deform weights, not a rectangular lipstick patch. Lip border
    # vertices blend to skin. Immutable source attribute follows posed topology.
    lip=smoothstep(.30,.88,np.clip(top+bottom,0,1))*smoothstep(-.115,-.145,y)
    ratio=bottom/np.maximum(top+bottom,1e-12)
    lip_color=(1-ratio[:,None])*linear(palette['upper_lip'])+ratio[:,None]*linear(palette['lower_lip'])
    front=smoothstep(-.04,-.11,y)
    blush=.23*np.exp(-((np.abs(x)-.063)/.030)**2-((z-1.430)/.027)**2)*front
    nose=.13*np.exp(-(x/.024)**2-((z-1.430)/.020)**2)*front
    warmth=np.clip(blush+nose,0,.3)
    color=np.tile(linear(palette['skin']),(len(p),1))
    color=color*(1-warmth[:,None])+linear(palette['blush'])*warmth[:,None]
    color=color*(1-lip[:,None])+lip_color*lip[:,None]
    result=np.ones((len(p),4),dtype=np.float32);result[:,:3]=color
    return result,lip


def principled(bpy,name,color,roughness):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*linear(color),1)
    shader.inputs['Roughness'].default_value=roughness
    shader.inputs['Specular IOR Level'].default_value=.28
    return mat,shader


def apply_palette(bpy,data,palette):
    head=bpy.data.objects['GEO-rain-head'];mesh=head.data
    colors,lip=complexion_colors(data,palette)
    attr=mesh.color_attributes.new(name='Mom R5 attached albedo',type='FLOAT_COLOR',domain='POINT')
    attr.data.foreach_set('color',colors.ravel())
    skin,shader=principled(bpy,'Mom R5 skin and lips',palette['skin'],.47)
    shader.inputs['Subsurface Weight'].default_value=.055
    shader.inputs['Subsurface Radius'].default_value=(1,.45,.25)
    shader.inputs['Subsurface Scale'].default_value=.012
    vertex=skin.node_tree.nodes.new('ShaderNodeVertexColor');vertex.layer_name=attr.name
    skin.node_tree.links.new(vertex.outputs['Color'],shader.inputs['Base Color'])
    for i in range(len(mesh.materials)):mesh.materials[i]=skin
    for obj_name,name,color,rough in [('GEO-rain-eyebrows','Mom R5 brows',palette['brows'],.58),('GEO-rain-eyelashes','Mom R5 lashes',palette['lashes'],.50)]:
        mat,_=principled(bpy,name,color,rough)
        obj=bpy.data.objects[obj_name]
        for i in range(len(obj.data.materials)):obj.data.materials[i]=mat
    # Keep original eye texture, UVs, sclera, pupil and radial iris detail.
    # Map texture luminance to a gray-blue ramp; white/black endpoints stay neutral.
    tree=bpy.data.materials['MAT-rain.eyes'].node_tree
    socket=tree.nodes['Principled BSDF'].inputs['Base Color']
    if len(socket.links)!=1:raise ValueError('Unexpected eye material input')
    source=socket.links[0].from_socket
    bw=tree.nodes.new('ShaderNodeRGBToBW');bw.name='Mom R5 native eye luminance'
    tree.links.new(source,bw.inputs[0])
    ramp=tree.nodes.new('ShaderNodeValToRGB');ramp.name='Mom R5 gray blue iris'
    stops=[(0.,'#0D1115'),(.12,'#35434B'),(.38,palette['iris']),(.68,'#AFBFC6'),(.90,'#EEEAE3'),(1.,'#FFFFFF')]
    elements=ramp.color_ramp.elements
    elements.remove(elements[1]);elements[0].position=0;elements[0].color=(*linear(stops[0][1]),1)
    for position,color in stops[1:]:elements.new(position).color=(*linear(color),1)
    tree.links.new(bw.outputs[0],ramp.inputs[0]);tree.links.new(ramp.outputs['Color'],socket)
    return {'palette_srgb':palette,'head_albedo_attribute':attr.name,'head_albedo_sha256':hashlib.sha256(colors.tobytes()).hexdigest(),
            'lip_mask_max':float(lip.max()),'lip_mask_nonzero_vertices':int((lip>.01).sum()),
            'method':'Original indexed POINT albedo follows actual rigged mesh; lip weights define feathered borders. Canonical-inspired palette in linear shader space, not a promise of exact displayed pixel color.',
            'iris_method':'Original texture luminance mapped to gray-blue ramp, preserving texture/UVs; pupil and sclera endpoints neutral.'}


def saved_material_state(bpy):
    head=bpy.data.objects['GEO-rain-head'];attr=head.data.color_attributes['Mom R5 attached albedo']
    colors=np.empty(len(attr.data)*4,dtype=np.float32);attr.data.foreach_get('color',colors)
    ramp=bpy.data.materials['MAT-rain.eyes'].node_tree.nodes['Mom R5 gray blue iris'].color_ramp
    return {'head_attribute_sha256':hashlib.sha256(colors.tobytes()).hexdigest(),
            'attribute_domain':attr.domain,'attribute_points':len(attr.data),
            'materials':{n:[m.name for m in bpy.data.objects[n].data.materials] for n in ('GEO-rain-head','GEO-rain-eyebrows','GEO-rain-eyelashes')},
            'eye_ramp_stops':[{'position':float(e.position),'color':list(e.color)} for e in ramp.elements]}
