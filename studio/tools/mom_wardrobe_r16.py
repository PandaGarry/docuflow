"""Original Rain shirt with added fitted sleeves and a separate open brown vest."""
import numpy as np
from mom_head_surface_r2 import vertex_normals

def material(bpy,name,color,roughness=.52):
 from rain_mom_pass import linear_color
 m=bpy.data.materials.new(name);m.use_nodes=True;t=m.node_tree;p=t.nodes['Principled BSDF'];p.inputs['Base Color'].default_value=linear_color(color);p.inputs['Roughness'].default_value=roughness;p.inputs['Sheen Weight'].default_value=.15
 noise=t.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=550;noise.inputs['Detail'].default_value=2
 bump=t.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.00012;t.links.new(noise.outputs['Fac'],bump.inputs['Height']);t.links.new(bump.outputs['Normal'],p.inputs['Normal']);return m

def bind_nearest(bpy,obj,template,rig):
 from rain_mom_pass import point_array,transform_points
 source=transform_points(point_array(template.data.vertices),template.matrix_world);p=np.asarray([v.co for v in obj.data.vertices]);groups={g.index:obj.vertex_groups.new(name=g.name) for g in template.vertex_groups}
 for start in range(0,len(p),256):
  dist=np.linalg.norm(p[start:start+256,None]-source[None],axis=2);near=np.argpartition(dist,3,axis=1)[:,:4]
  for row,indices in enumerate(near):
   weights=1/np.maximum(dist[row,indices],.0005)**2;weights/=weights.sum();combined={}
   for index,weight in zip(indices,weights):
    for g in template.data.vertices[index].groups:combined[g.group]=combined.get(g.group,0)+weight*g.weight
   for index,weight in combined.items():
    if weight>.0001:groups[index].add([start+row],float(weight),'REPLACE')
 mod=obj.modifiers.new('Original Rain garment deformation','ARMATURE');mod.object=rig;mod.use_deform_preserve_volume=True

def mesh(bpy,name,p,faces,mat,template,rig,thickness=.002):
 data=bpy.data.meshes.new(name);data.from_pydata(p,[],faces);data.update();obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj);data.materials.append(mat)
 for f in data.polygons:f.use_smooth=True
 bind_nearest(bpy,obj,template,rig)
 sub=obj.modifiers.new('Garment smooth surface','SUBSURF');sub.levels=1;sub.render_levels=2
 solid=obj.modifiers.new('Fabric thickness','SOLIDIFY');solid.thickness=thickness;solid.offset=0
 return obj

def sleeve(side):
 p=[];faces=[];rows=6;cols=32
 for i in range(rows):
  t=i/(rows-1);x=side*(.100+.126*t);radius=.050-.008*t
  for j in range(cols):
   a=2*np.pi*j/cols;p.append((x,-.019-radius*np.cos(a),1.267+radius*np.sin(a)))
 for i in range(rows-1):
  for j in range(cols):a=i*cols+j;b=i*cols+(j+1)%cols;faces.append((a,b,b+cols,a+cols))
 return p,faces

def build(bpy,rig,settings):
 from rain_mom_pass import point_array,transform_points
 top=bpy.data.objects['GEO-rain-top'];top.hide_render=False;top.hide_set(False)
 skin=material(bpy,'Mom R16 matching body skin','#E8B48F',.5)
 body=bpy.data.objects['GEO-rain-body']
 for i in range(len(body.data.materials)):body.data.materials[i]=skin
 white=material(bpy,'Mom R16 white cotton shirt',settings['shirt_srgb'],.66)
 for i in range(len(top.data.materials)):top.data.materials[i]=white
 brown=material(bpy,'Mom R16 brown vest',settings['vest_srgb'],.48);objects=[]
 for side in (-1,1):
  p,f=sleeve(side);objects.append(mesh(bpy,f'GEO-mom-R16-shirt-sleeve-{side}',p,f,white,bpy.data.objects['GEO-rain-body'],rig))
 p=transform_points(point_array(top.data.vertices),top.matrix_world);faces=[list(f.vertices) for f in top.data.polygons];normal=vertex_normals(p,faces);radial=np.column_stack([p[:,0],p[:,1],np.zeros(len(p))]);normal*=np.where(np.einsum('ij,ij->i',normal,radial)>=0,1,-1)[:,None];vest=p+normal*.014
 keep=[]
 for f in faces:
  center=vest[f].mean(0);gap=.022+.020*np.clip((center[2]-1.12)/.18,0,1)
  if center[2]<.98:continue
  if center[1]<-.018 and abs(center[0])<gap:continue
  keep.append(f)
 keep=[list(reversed(f)) for f in keep]
 objects.append(mesh(bpy,'GEO-mom-R16-open-brown-vest',vest.tolist(),keep,brown,top,rig,.004))
 # Rolled standing collar and two soft folded fronts, separately editable.
 from mom_groom_r16 import catmull
 for side in (-1,1):
  center=catmull([(side*.043,.022,1.323),(side*.058,-.025,1.324),(side*.067,-.091,1.296),(side*.051,-.123,1.229),(side*.032,-.120,1.157)],24)
  # Attach collar to the true fitted shirt/vest surface, not a detached tube.
  for i,c in enumerate(center):
   if c[2]<1.31:
    distance=np.linalg.norm(p[:,[0,2]]-c[[0,2]],axis=1);eligible=(p[:,1]<0);distance=np.where(eligible,distance,np.inf);ids=np.argsort(distance)[:6]
    weights=1/np.maximum(distance[ids],.001)**3;c[1]=float(np.average(p[ids,1],weights=weights))-.017
  pp=[]
  for i,c in enumerate(center):
   for j in range(7):
    u=j/6-.5;point=c.copy();point[0]+=side*u*.028;point[1]-=.002*np.cos(u*np.pi);point[2]+=.0015*np.cos(u*np.pi);pp.append(point.tolist())
  ff=[]
  for i in range(23):
   for j in range(6):a=i*7+j;ff.append((a,a+1,a+8,a+7))
  objects.append(mesh(bpy,f'GEO-mom-R16-folded-collar-{side}',pp,ff,brown,top,rig,.003))
 # R15 nearest-vertex piping was visibly jagged; omit rather than fake a seam.
 return {'objects':[o.name for o in objects],'shirt_source':top.name,'vest_source':'Fitted offset original shirt surface with open front and cropped hem; separate rolled collars, plackets and fitted folded fronts','binding':'Original Rain armature, nearest original garment/body weights; seams torso parented','cloth_simulation_validated':False,'wardrobe_approved':False}
