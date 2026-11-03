"""R9 high-resolution original-UV face paint and PBR maps on genuine Rain mesh.

No portrait projection, render repaint or new head geometry. Source-rest surface
coordinates and anatomical lip weights define editable material strokes, baked
onto the ORIGINAL UV layout. Pure rasterizer/paint helpers require no bpy.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import mom_face_finish_r7 as prior
import mom_face_finish_r6 as controls
from mom_face_finish_r7 import ear_mask,finish_ears,linear,smoothstep,group_sum


def paint_samples(points,top,bottom,palette):
    p=np.asarray(points,dtype=float);x,y,z=p.T;ax=np.abs(x)
    front=smoothstep(-.04,-.11,y)
    skin=np.tile(linear(palette['skin']),(len(p),1))
    temperature=.20*front
    skin=skin*(1-temperature[:,None])+linear('#ED9872')*temperature[:,None]
    blush=.58*np.exp(-((ax-.063)/.030)**2-((z-1.430)/.027)**2)*front
    tip=.30*np.exp(-(x/.024)**2-((z-1.430)/.020)**2)*front
    warmth=np.clip(blush+tip,0,.60)
    skin=skin*(1-warmth[:,None])+linear(palette['blush'])*warmth[:,None]
    upper_z=np.interp(ax,[0,.0048,.009483,.014325,.018822,.022911,.026847,.029552],
                          [1.402812,1.40335,1.403628,1.402544,1.401069,1.399422,1.397636,1.393051])
    upper_z-=.0014*(1-smoothstep(.020,.030,ax))
    upper_boundary=smoothstep(upper_z+.00045,upper_z-.00045,z)
    lip=smoothstep(.20,.60,np.clip(top+bottom,0,1))*smoothstep(-.115,-.145,y)*upper_boundary
    lip*=1-smoothstep(.030,.033,ax)
    # Do NOT clip lower vermilion using R6's too-high lower chart. Original
    # anatomical lip weights feather it into chin skin without rectangular paint.
    ratio=smoothstep(1.3930,1.3885,z)
    pigment=(1-ratio[:,None])*linear(palette['upper_lip'])+ratio[:,None]*linear(palette['lower_lip'])
    rgba=np.ones((len(p),4),dtype=np.float32)
    rgba[:,:3]=skin*(1-lip[:,None])+pigment*lip[:,None]
    rough=np.ones((len(p),4),dtype=np.float32);rough[:,:3]=(.47-(.07+.06*ratio)*lip)[:,None]
    return rgba,rough


def pad_islands(image,coverage,steps=6):
    """Copy nearest available island edge outward; never wrap opposite borders."""
    result=image.copy();known=coverage.copy()
    for _ in range(steps):
        filled=known.copy()
        for axis,shift in ((0,1),(0,-1),(1,1),(1,-1)):
            neighbors=np.roll(known,shift,axis=axis)
            if axis==0:neighbors[0 if shift==1 else -1,:]=False
            else:neighbors[:,0 if shift==1 else -1]=False
            take=neighbors&~filled
            if take.any():result[take]=np.roll(result,shift,axis=axis)[take]
            filled|=take
        known=filled
    return result


def rasterize(positions,uv,vertices,loop_indices,top,bottom,palette,resolution=2048,domain=None):
    """Paint source-rest attributes at texel centers of original UV triangles.

    Image origin is bottom-left, matching Blender pixels, not PNG display order.
    An explicit bounded square source domain supports original layouts outside
    0-1 without clipping, wrapping or changing any original UV coordinates.
    """
    uv=np.asarray(uv,dtype=float);positions=np.asarray(positions,dtype=float)
    if resolution<8 or resolution>4096:raise ValueError('Unbounded texture resolution')
    if not np.isfinite(uv).all():raise ValueError('Nonfinite original UVs')
    if domain is not None:
        origin=np.asarray(domain['origin'],dtype=float);extent=float(domain['extent'])
        if origin.shape!=(2,) or not np.isfinite(origin).all() or not .01<=extent<=16:raise ValueError('Unbounded UV domain')
        uv=(uv-origin)/extent
    if uv.min() < -1e-5 or uv.max()>1+1e-5:raise ValueError('UVs outside explicit atlas domain')
    albedo=np.ones((resolution,resolution,4),dtype=np.float32)
    albedo[:,:,:3]=linear(palette['skin'])
    rough=np.ones_like(albedo);rough[:,:,:3]=.47
    coverage=np.zeros((resolution,resolution),dtype=bool);painted=0
    for ids,loops in zip(vertices,loop_indices):
        tri=uv[loops]*resolution-.5;a,b,c=tri
        e0=b-a;e1=c-a;den=e0[0]*e1[1]-e0[1]*e1[0]
        if abs(den)<1e-10:continue
        low=np.maximum(np.floor(tri.min(0)).astype(int),0)
        high=np.minimum(np.ceil(tri.max(0)).astype(int),resolution-1)
        if (high<low).any():continue
        gx,gy=np.meshgrid(np.arange(low[0],high[0]+1),np.arange(low[1],high[1]+1))
        dx=gx-a[0];dy=gy-a[1]
        u=(dx*e1[1]-dy*e1[0])/den;v=(e0[0]*dy-e0[1]*dx)/den
        inside=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)
        if not inside.any():continue
        bary=np.stack((1-u[inside]-v[inside],u[inside],v[inside]),axis=1)
        samples=bary@positions[ids]
        color,r=paint_samples(samples,bary@top[ids],bary@bottom[ids],palette)
        yy=gy[inside];xx=gx[inside]
        albedo[yy,xx]=color;rough[yy,xx]=r;coverage[yy,xx]=True;painted+=1
    if not coverage.any():raise ValueError('No original UV face surface rasterized')
    return pad_islands(albedo,coverage),pad_islands(rough,coverage),{
        'resolution':resolution,'covered_texels':int(coverage.sum()),'rasterized_triangles':painted,
        'coverage_fraction':float(coverage.mean()),'padding_texels':6,'original_uv_domain':domain or {'origin':[0,0],'extent':1},
        'method':'Original UV triangle rasterization, source-rest anatomical strokes. No reference-image projection or output-frame retouch.'}


def save_packed_map(bpy,pixels,name,path):
    size=pixels.shape[0]
    image=bpy.data.images.new(name,width=size,height=size,alpha=True,float_buffer=True)
    image.colorspace_settings.name='Non-Color'
    image.pixels.foreach_set(pixels.ravel())
    image.file_format='OPEN_EXR';image.filepath_raw=str(path.resolve());image.save()
    bpy.data.images.remove(image)
    # Load the actual saved EXR before packing: persisted texel bytes, not only
    # a generated in-memory buffer, become the material's real dependency.
    actual=bpy.data.images.load(str(path.resolve()),check_existing=False)
    actual.name=name;actual.colorspace_settings.name='Non-Color';actual.pack()
    return actual,hashlib.sha256(path.read_bytes()).hexdigest()


def render_uv(mesh):
    layer=next((layer for layer in mesh.uv_layers if layer.active_render),None)
    if layer is None:raise ValueError('No original render UV layer')
    return layer


def atlas_domain(uv):
    uv=np.asarray(uv,dtype=float)
    if uv.ndim!=2 or uv.shape[1]!=2 or not np.isfinite(uv).all():raise ValueError('Invalid UV layout')
    low=uv.min(0);high=uv.max(0);extent=float(max(high-low))
    if extent<.01 or extent>15.9:raise ValueError('Unbounded original UV span')
    # Uniform domain scale preserves island proportions and original UV data.
    margin=extent*.004
    return {'origin':(low-margin).tolist(),'extent':extent+2*margin,'original_min':low.tolist(),'original_max':high.tolist()}


def apply_palette(bpy,data,palette):
    record=prior.apply_palette(bpy,data,palette)
    mesh=bpy.data.objects['GEO-rain-head'].data;mesh.calc_loop_triangles()
    if not mesh.uv_layers.active:raise ValueError('No original UV layout')
    uv_layer=render_uv(mesh);uv=np.empty(len(uv_layer.data)*2,dtype=np.float32)
    uv_layer.data.foreach_get('uv',uv);uv=uv.reshape(-1,2)
    verts=np.array([list(t.vertices) for t in mesh.loop_triangles])
    loops=np.array([list(t.loops) for t in mesh.loop_triangles])
    top=group_sum(data,('DEF-Lip_Top_',));bottom=group_sum(data,('DEF-Lip_Bot_',))
    domain=atlas_domain(uv)
    output=Path(__file__).resolve().parents[2]/'studio/reviews/mom-head-form-r9'
    layout={'render_uv':uv_layer.name,'domain':domain,'layers':[{'name':layer.name,'active_render':layer.active_render} for layer in mesh.uv_layers],
            'original_uv_sha256':hashlib.sha256(uv.tobytes()).hexdigest(),'method':'Original UV coordinates retained; explicit uniform domain transform in shader, no clipping/repeating.'}
    (output/'original-uv-layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    color,rough,receipt=rasterize(data['basis_vertices'],uv,verts,loops,top,bottom,palette,domain=domain)
    directory=Path(__file__).resolve().parents[2]/'.cache/rain-v3';directory.mkdir(parents=True,exist_ok=True)
    color_image,color_sha=save_packed_map(bpy,color,'Mom R9 original UV albedo',directory/'mom-r9-albedo.exr')
    rough_image,rough_sha=save_packed_map(bpy,rough,'Mom R9 original UV roughness',directory/'mom-r9-roughness.exr')
    mat=mesh.materials[0];tree=mat.node_tree;shader=tree.nodes['Principled BSDF']
    uv_node=tree.nodes.new('ShaderNodeUVMap');uv_node.uv_map=uv_layer.name;uv_node.name='Mom R9 original UV layout'
    subtract=tree.nodes.new('ShaderNodeVectorMath');subtract.operation='SUBTRACT';subtract.name='Mom R9 source UV domain origin'
    subtract.inputs[1].default_value=(*domain['origin'],0)
    scale=tree.nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.name='Mom R9 uniform UV atlas scale'
    scale.inputs[1].default_value=(1/domain['extent'],1/domain['extent'],1)
    tree.links.new(uv_node.outputs['UV'],subtract.inputs[0]);tree.links.new(subtract.outputs['Vector'],scale.inputs[0])
    for image,label,socket in ((color_image,'Mom R9 active UV albedo','Base Color'),(rough_image,'Mom R9 active UV roughness','Roughness')):
        node=tree.nodes.new('ShaderNodeTexImage');node.image=image;node.name=label;node.interpolation='Linear';node.extension='EXTEND'
        tree.links.new(scale.outputs['Vector'],node.inputs['Vector']);tree.links.new(node.outputs['Color'],shader.inputs[socket])
    receipt.update({'uv_layer':uv_layer.name,'original_uv_sha256':hashlib.sha256(uv.tobytes()).hexdigest(),
                    'albedo_exr_sha256':color_sha,'roughness_exr_sha256':rough_sha,
                    'color_space':'Packed floating-point EXR contains linear data, Non-Color input; no sRGB double transform.',
                    'active_material_source':'original-UV image textures; R7 vertex albedo/roughness retained only as fallback data'})
    record.update({'uv_paint':receipt,'method':'Editable 2048px original-UV albedo and separate roughness maps on original rigged head.',
                   'head_albedo_attribute_is_fallback':True})
    return record


def saved_material_state(bpy):
    state=controls.saved_material_state(bpy)
    head=bpy.data.objects['GEO-rain-head'];mesh=head.data;uv=render_uv(mesh)
    coords=np.empty(len(uv.data)*2,dtype=np.float32);uv.data.foreach_get('uv',coords)
    state['original_uv_sha256']=hashlib.sha256(coords.tobytes()).hexdigest()
    tree=mesh.materials[0].node_tree;shader=tree.nodes['Principled BSDF'];maps={}
    for socket in ('Base Color','Roughness'):
        node=shader.inputs[socket].links[0].from_node
        if node.type!='TEX_IMAGE' or not node.image.packed_file:raise ValueError('Active material is not a packed texture')
        scale=node.inputs['Vector'].links[0].from_node
        subtract=scale.inputs[0].links[0].from_node
        uv_node=subtract.inputs[0].links[0].from_node
        if scale.type!='VECT_MATH' or scale.operation!='MULTIPLY' or subtract.operation!='SUBTRACT' or uv_node.type!='UVMAP' or uv_node.uv_map!=uv.name:raise ValueError('Wrong material UV/domain binding')
        maps[socket]={'image':node.image.name,'size':list(node.image.size),'colorspace':node.image.colorspace_settings.name,
                      'packed_file_sha256':hashlib.sha256(bytes(node.image.packed_file.data)).hexdigest(),'uv_map':uv_node.uv_map,
                      'domain_origin':list(subtract.inputs[1].default_value),'uniform_domain_scale':list(scale.inputs[1].default_value)}
    state['active_original_uv_maps']=maps
    return state
