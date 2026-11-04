"""Reference-flow sculpted locks: independent closed meshes, not a crown cap.

Pixel points guide XZ only. Depth and volume are independently authored in 3D.
All views are rendered natively; no reference-image texture is used.
"""
import numpy as np
from mom_head_surface_r2 import cubic_curve
from mom_face_finish_r7 import linear
from mom_groom_r16 import native_curves

# Each control is (reference pixel X, pixel Y, independently authored world Y).
FRONT=[
 ('left-inner-fringe',[(406,63,-.045),(394,95,-.115),(367,150,-.161),(328,217,-.18),(276,281,-.179),(222,339,-.165),(173,401,-.14),(126,444,-.112)],.021,.012),
 ('right-inner-fringe',[(411,64,-.045),(421,99,-.12),(450,145,-.157),(503,235,-.177),(548,318,-.175),(603,382,-.155),(665,416,-.14),(710,420,-.123)],.017,.011),
 ('left-sweep',[(404,58,-.025),(353,30,-.070),(278,75,-.105),(229,174,-.15),(213,251,-.16),(163,352,-.144),(116,443,-.112),(101,529,-.105),(115,609,-.09),(102,696,-.075),(64,784,-.08),(22,808,-.09),(10,802,-.085)],.025,.011),
 ('right-feather',[(408,58,-.025),(466,39,-.075),(549,94,-.12),(601,192,-.153),(615,287,-.156),(653,371,-.15),(695,407,-.135),(722,415,-.115)],.028,.011),
 ('right-inner-wave',[(413,62,-.008),(480,67,-.08),(563,143,-.134),(624,291,-.135),(640,406,-.12),(630,501,-.115),(626,594,-.103),(656,703,-.08),(704,792,-.09),(741,818,-.095)],.019,.010),
 ('right-outer-wave',[(423,60,.015),(524,86,-.03),(611,182,-.07),(658,321,-.075),(690,430,-.065),(697,524,-.055),(683,605,-.05),(705,708,-.055),(748,796,-.075),(765,811,-.085),(756,802,-.08)],.022,.014),
 ('left-inner-wave',[(398,59,.0),(324,80,-.06),(257,171,-.11),(208,280,-.125),(160,392,-.12),(133,493,-.08),(145,574,-.06),(127,680,-.05),(90,769,-.06),(52,815,-.065)],.018,.010),
 ('left-outer-wave',[(393,58,.022),(301,92,-.025),(222,192,-.064),(173,323,-.075),(119,421,-.06),(87,518,-.05),(100,607,-.04),(76,711,-.05),(30,791,-.07),(20,811,-.075)],.021,.013),
]

def guides(settings):
 m=settings['meters_per_pixel'];cx=settings['pixel_origin_x'];z=settings['eye_z_m'];ey=settings['eye_y']
 result=[]
 for name,points,width,depth in FRONT:
  path=np.array([[(x-cx)*m,y,z-(py-ey)*m] for x,py,y in points]);result.append((name,path,width,depth))
 # Behind the independent face-framing flows: overlapping rear and side locks.
 # Not a hemisphere shell; each extends all the way to its own tapered wave tip.
 for i,a in enumerate(np.linspace(0,np.pi,11)):
  c,s=np.cos(a),np.sin(a);rootx=.0085;phase=(i%3-1)*.008
  path=np.array([[rootx,.025+(i/10)*.030,1.621],
   [.058*c,.055+.034*s,1.606],[.102*c,.052+.066*s,1.555],
   [.129*c,.030+.103*s,1.480],[.137*c,.020+.110*s,1.413],
   [.128*c,.025+.100*s,1.373],[.139*c,.020+.093*s,1.330+phase],
   [.157*c,.005+.086*s,1.289+phase],[.167*c,-.008+.074*s,1.277+phase]])
  result.append((f'rear-{i:02}',path,.024,.014))
 return result

def sample(path,count=100):
 distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))];distances/=distances[-1];t=np.linspace(0,1,count)
 return np.stack([cubic_curve(t,distances,path[:,axis]) for axis in range(3)],axis=1)

def lock_geometry(path,width,depth,index):
 centers=sample(path);t=np.linspace(0,1,len(centers));tangent=np.gradient(centers,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
 axis=np.stack((-tangent[:,2],np.zeros(len(t)),tangent[:,0]),axis=1);axis/=np.linalg.norm(axis,axis=1)[:,None]
 forward=np.cross(tangent,axis);forward/=np.linalg.norm(forward,axis=1)[:,None]
 profile=cubic_curve(t,[0,.05,.18,.44,.70,.88,.97,1],[.12,.48,1,.98,.90,.50,.12,.005])
 angle=np.linspace(0,2*np.pi,32,endpoint=False);ridge=1+.015*np.cos(10*angle+index*.63)
 rings=centers[:,None,:]+profile[:,None,None]*ridge[None,:,None]*(width*np.cos(angle)[None,:,None]*axis[:,None,:]+depth*np.sin(angle)[None,:,None]*forward[:,None,:])
 verts=rings.reshape(-1,3).tolist();faces=[];uv=[];sides=len(angle)
 for j in range(len(t)-1):
  for k in range(sides):
   kk=(k+1)%sides;faces.append((j*sides+k,j*sides+kk,(j+1)*sides+kk,(j+1)*sides+k));uv.extend([(t[j],k/sides),(t[j],(k+1)/sides),(t[j+1],(k+1)/sides),(t[j+1],k/sides)])
 # Both ends closed. Side rings are tiny at tips, avoiding blunt rods.
 faces.extend([tuple(reversed(range(sides))),tuple((len(t)-1)*sides+k for k in range(sides))]);uv.extend([(0,k/sides) for k in reversed(range(sides))]+[(1,k/sides) for k in range(sides)])
 return verts,faces,uv,(centers,axis,forward,profile)

def material(bpy,color):
 m=bpy.data.materials.new('Mom R17 soft sculpted brown hair');m.use_nodes=True;tree=m.node_tree;n=tree.nodes;p=n.get('Principled BSDF');p.inputs['Base Color'].default_value=(*linear('#886242'),1);p.inputs['Roughness'].default_value=.44;p.inputs['Specular IOR Level'].default_value=.28;(p.inputs.get('Anisotropic IOR Level') or p.inputs['Anisotropic']).default_value=.40;p.inputs['Coat Weight'].default_value=.035;p.inputs['Coat Roughness'].default_value=.40
 tex=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(5,85,1);tree.links.new(tex.outputs['UV'],mapping.inputs[0]);noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1;noise.inputs['Detail'].default_value=2;noise.inputs['Roughness'].default_value=.45;tree.links.new(mapping.outputs[0],noise.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.035;bump.inputs['Distance'].default_value=.00006;tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);tree.links.new(bump.outputs[0],p.inputs['Normal']);return m

def build(bpy,rig,settings,color):
 import mom_hair_contours_r17 as contours
 mat=material(bpy,color);objects,fiber,contact=contours.build(bpy,rig,settings,mat)
 for i,(name,path,w,d) in enumerate(guides(settings)[len(FRONT):]):
  verts,faces,uv,frames=lock_geometry(path,w,d,i);mesh=bpy.data.meshes.new('R17 rear lock '+name);mesh.from_pydata(verts,[],faces);mesh.update();layer=mesh.uv_layers.new(name='Longitudinal flow');layer.data.foreach_set('uv',np.asarray(uv).ravel())
  for p in mesh.polygons:p.use_smooth=True
  obj=bpy.data.objects.new('HAIR-mom-R17-'+name,mesh);bpy.context.scene.collection.objects.link(obj);mesh.materials.append(mat);world=obj.matrix_world.copy();obj.parent=rig;obj.parent_type='BONE';obj.parent_bone='DEF-Head';bpy.context.view_layer.update();obj.matrix_world=world;objects.append(obj.name)
 return {'objects':objects,'object_vertex_counts':{n:len(bpy.data.objects[n].data.vertices) for n in objects},'surface_fiber_object':fiber,'curves':75,'locks':len(objects),'method':'Twenty-five individually rounded contour-guided front tresses and eleven rear wave locks; NO broad surface panel or crown cap, no alternating color stripes.','contact':contact,'single_crown_shell':False,'reference_texture_projection':False}
