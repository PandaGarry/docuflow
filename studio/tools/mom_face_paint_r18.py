"""Lower actual linear albedo energy under the held R17 light, not image grading."""
import hashlib
from pathlib import Path
import numpy as np
import mom_face_paint_r17 as previous
from mom_face_finish_r7 import group_sum

def rasterize(*args,energy_scale=.72,**kwargs):
 color,pbr,receipt=previous.rasterize(*args,**kwargs)
 if not .5<=energy_scale<=1:raise ValueError('Unbounded physical albedo scaling')
 color[:,:,:3]*=energy_scale
 receipt.update({'linear_albedo_energy_scale':energy_scale,'method':'Actual EXR pigment energy changed before rendering, held illumination. No beauty-image adjustment.'})
 return color,pbr,receipt

def apply(bpy,data,palette,energy_scale):
 mesh=bpy.data.objects['GEO-rain-head'].data;layer=previous.render_uv(mesh);uv=np.empty(len(layer.data)*2,np.float32);layer.data.foreach_get('uv',uv);uv=uv.reshape(-1,2);tri=[];loops=[]
 for p in mesh.polygons:
  for j in range(1,len(p.vertices)-1):tri.append([p.vertices[0],p.vertices[j],p.vertices[j+1]]);loops.append([p.loop_indices[0],p.loop_indices[j],p.loop_indices[j+1]])
 color,pbr,receipt=rasterize(data['basis_vertices'],uv,np.array(tri),np.array(loops),group_sum(data,('DEF-Lip_Top_',)),group_sum(data,('DEF-Lip_Bot_',)),palette,energy_scale=energy_scale,domain=previous.atlas_domain(uv));folder=Path(__file__).resolve().parents[2]/'.cache/r18';folder.mkdir(parents=True,exist_ok=True)
 albedo,a_sha=previous.save_packed_map(bpy,color,'Mom R18 original UV albedo',folder/'mom-r18-albedo.exr');response,r_sha=previous.save_packed_map(bpy,pbr,'Mom R18 original UV PBR',folder/'mom-r18-pbr.exr');tree=mesh.materials[0].node_tree;shader=tree.nodes['Principled BSDF'];shader.inputs['Base Color'].links[0].from_node.image=albedo;separate=shader.inputs['Roughness'].links[0].from_node;separate.inputs['Color'].links[0].from_node.image=response
 # Matching constant pigment at the body/neck continuation, not a pale patch.
 body=bpy.data.objects['GEO-rain-body'];body_mat=body.data.materials[0];old=body_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value[:];neutral,_=previous.paint_samples(np.array([[0,-.04,1.32]]),np.zeros(1),np.zeros(1),palette);body_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*neutral[0,:3]*energy_scale,1)
 receipt.update({'albedo_exr_sha256':a_sha,'pbr_exr_sha256':r_sha,'original_uv_sha256':hashlib.sha256(uv.tobytes()).hexdigest(),'reference_projection':False,'palette_srgb':palette,'matching_body_skin_before':list(old),'matching_body_skin_after':list(body_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)})
 return receipt
