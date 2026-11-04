"""Inspect actual downloaded R13, never rebuild/replace its original Rain head."""
import hashlib,json
from pathlib import Path
import numpy as np
import mom_head_form_r13 as prior
ROOT=prior.ROOT;OUT=ROOT/'studio/reviews/mom-character-r14'
def load(bpy):
 r=json.loads((ROOT/'studio/reviews/mom-head-form-r13/report.json').read_text());bundle=ROOT/'.cache/r14-r13-source'
 files=list(bundle.rglob('mom-head-form-r13.blend'))
 if len(files)!=1:raise ValueError('Expected actual R13 native artifact')
 native=files[0]
 if prior.study.sha(native)!=r['native_artifact']['sha256']:raise ValueError('R13 binary hash mismatch')
 if (bundle/'studio/reviews/mom-head-form-r13/report.json').read_bytes()!=(ROOT/'studio/reviews/mom-head-form-r13/report.json').read_bytes():raise ValueError('Archived R13 report differs')
 bpy.context.preferences.filepaths.use_scripts_auto_execute=False
 bpy.ops.wm.open_mainfile(filepath=str(native.resolve()),use_scripts=False);bpy.context.view_layer.update()
 if prior.finish.saved_material_state(bpy)!=r['saved_material_state']:raise ValueError('Downloaded R13 material state differs')
 return r,native

def main():
 import bpy
 r,native=load(bpy);objects=[]
 for obj in bpy.data.objects:
  if obj.type!='MESH':continue
  p=prior.base.transform_points(prior.base.point_array(obj.data.vertices),obj.matrix_world)
  sub=[(m,m.show_viewport) for m in obj.modifiers if m.type=='SUBSURF']
  for m,_ in sub:m.show_viewport=False
  bpy.context.view_layer.update();ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
  q=prior.base.transform_points(prior.base.point_array(mesh.vertices),ev.matrix_world);ev.to_mesh_clear()
  for m,state in sub:m.show_viewport=state
  item={'name':obj.name,'vertices':len(p),'basis_min':p.min(0).tolist(),'basis_max':p.max(0).tolist(),'evaluated_min':q.min(0).tolist(),'evaluated_max':q.max(0).tolist(),'materials':[m.name for m in obj.data.materials if m],'modifiers':[m.type for m in obj.modifiers]}
  if obj.name in ('GEO-rain-eyes','GEO-rain-eye_cornea','GEO-rain-top','GEO-rain-body'):
   item['basis_vertices']=p.round(7).tolist();item['evaluated_vertices']=q.round(7).tolist()
   item['polygons']=[list(f.vertices) for f in obj.data.polygons]
   item['uv_layers']={l.name:[[round(v,7) for v in loop.uv] for loop in l.data] for l in obj.data.uv_layers}
  objects.append(item)
 eye=bpy.data.materials['MAT-rain.eyes'];nodes=[]
 for n in eye.node_tree.nodes:nodes.append({'name':n.name,'type':n.type,'image':n.image.name if n.type=='TEX_IMAGE' and n.image else None,'inputs':[{'name':i.name,'linked':i.is_linked} for i in n.inputs]})
 record={'source_run':41807469868,'downloaded_binary_sha256':prior.study.sha(native),'script_sha256':prior.study.sha(__file__),'objects':objects,'eye_nodes':nodes,'eye_links':[(l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name) for l in eye.node_tree.links], 'head_bones':[b.name for b in bpy.data.objects['RIG-rain'].data.bones if 'Head' in b.name or 'Neck' in b.name],'hair_api':str(bpy.data.hair_curves.new.__doc__),'art_approved':False,'user_approved':False,'production_swap_allowed':False}
 OUT.mkdir(parents=True,exist_ok=True);prior.study.write(OUT/'inspection.json',record)
if __name__=='__main__':main()
