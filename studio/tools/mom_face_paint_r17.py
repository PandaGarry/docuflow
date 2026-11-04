"""New original-UV skin/vermillion pigments, never the reference image as texture."""
import hashlib
from pathlib import Path
import numpy as np
from mom_face_paint_r11 import pad_islands,save_packed_map,render_uv,atlas_domain
from mom_face_finish_r7 import linear,smoothstep,group_sum

def paint_samples(points,top,bottom,palette):
    p=np.asarray(points,dtype=float);x,y,z=p.T;ax=np.abs(x)
    front=smoothstep(-.04,-.11,y)
    skin=np.tile(linear(palette['skin']),(len(p),1))
    skin[:,0]*=1.18
    temperature=.18*front
    skin=skin*(1-temperature[:,None])+linear('#F0A28C')*temperature[:,None]
    blush=.45*np.exp(-((ax-.063)/.030)**2-((z-1.430)/.027)**2)*front
    tip=.90*np.exp(-(x/.024)**2-((z-1.428)/.016)**2)*front
    warmth=np.clip(blush+tip,0,.72)
    cheek=skin*(1-blush[:,None])+linear(palette['blush'])*blush[:,None]
    skin=cheek*(1-tip[:,None])+linear(palette['nose'])*tip[:,None]
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
    # Independent surface responses packed into a linear RGB map; alpha opaque.
    rough=np.ones((len(p),4),dtype=np.float32)
    rough[:,0]=.53-(.15+.10*ratio)*lip
    rough[:,1]=(.05+.12*ratio)*lip
    rough[:,2]=.22
    return rgba,rough


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
    rough=np.ones_like(albedo);rough[:,:,0]=.47;rough[:,:,1]=0;rough[:,:,2]=.22
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


def apply(bpy,data,palette):
 mesh=bpy.data.objects['GEO-rain-head'].data;uv_layer=render_uv(mesh);uv=np.empty(len(uv_layer.data)*2,dtype=np.float32);uv_layer.data.foreach_get('uv',uv);uv=uv.reshape(-1,2)
 verts=[];loops=[]
 # Fixed original polygon fans: no geometry-dependent triangulation in painting.
 for p in mesh.polygons:
  for j in range(1,len(p.vertices)-1):verts.append([p.vertices[0],p.vertices[j],p.vertices[j+1]]);loops.append([p.loop_indices[0],p.loop_indices[j],p.loop_indices[j+1]])
 domain=atlas_domain(uv);color,rough,receipt=rasterize(data['basis_vertices'],uv,np.array(verts),np.array(loops),group_sum(data,('DEF-Lip_Top_',)),group_sum(data,('DEF-Lip_Bot_',)),palette,domain=domain)
 folder=Path(__file__).resolve().parents[2]/'.cache/r17';folder.mkdir(parents=True,exist_ok=True)
 color_image,color_sha=save_packed_map(bpy,color,'Mom R17 original UV albedo',folder/'mom-r17-albedo.exr');rough_image,rough_sha=save_packed_map(bpy,rough,'Mom R17 original UV PBR',folder/'mom-r17-pbr.exr')
 tree=mesh.materials[0].node_tree;shader=tree.nodes['Principled BSDF'];shader.inputs['Base Color'].links[0].from_node.image=color_image
 separate=shader.inputs['Roughness'].links[0].from_node;separate.inputs['Color'].links[0].from_node.image=rough_image
 shader.inputs['Specular IOR Level'].default_value=.28;shader.inputs['Subsurface Weight'].default_value=.09;shader.inputs['Subsurface Scale'].default_value=.008
 receipt.update({'original_uv_sha256':hashlib.sha256(uv.tobytes()).hexdigest(),'albedo_exr_sha256':color_sha,'pbr_exr_sha256':rough_sha,'reference_projection':False,'palette_srgb':palette,'skin_specular_ior_level':.28,'skin_sss_weight':.09,'skin_sss_scale_m':.008})
 return receipt
