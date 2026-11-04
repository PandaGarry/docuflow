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
 ('left-sweep',[(404,55,-.025),(394,32,-.055),(319,65,-.105),(253,151,-.15),(213,251,-.16),(163,352,-.144),(116,443,-.112),(101,529,-.105),(115,609,-.09),(102,696,-.075),(64,784,-.08),(35,807,-.09)],.025,.011),
 ('right-feather',[(405,55,-.025),(421,34,-.055),(511,75,-.115),(577,172,-.153),(615,287,-.156),(653,371,-.132),(695,407,-.10),(722,415,-.08)],.028,.011),
 ('right-inner-wave',[(413,62,-.008),(480,67,-.08),(563,143,-.134),(624,291,-.135),(640,406,-.12),(630,501,-.115),(626,594,-.103),(656,703,-.08),(704,792,-.09),(741,818,-.095)],.019,.010),
 ('right-outer-wave',[(423,60,.015),(524,86,-.03),(611,182,-.07),(658,321,-.075),(690,430,-.065),(697,524,-.055),(683,605,-.05),(705,708,-.055),(748,796,-.075),(754,820,-.085)],.022,.014),
 ('left-inner-wave',[(398,59,.0),(324,80,-.06),(257,171,-.11),(208,280,-.125),(160,392,-.12),(133,493,-.12),(145,574,-.102),(127,680,-.09),(90,769,-.10),(52,815,-.105)],.018,.010),
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
 profile=cubic_curve(t,[0,.05,.18,.44,.70,.88,.97,1],[.12,.48,1,.94,.82,.64,.25,.015])
 angle=np.linspace(0,2*np.pi,32,endpoint=False);ridge=1+.028*np.cos(18*angle+index*.63)
 rings=centers[:,None,:]+profile[:,None,None]*ridge[None,:,None]*(width*np.cos(angle)[None,:,None]*axis[:,None,:]+depth*np.sin(angle)[None,:,None]*forward[:,None,:])
 verts=rings.reshape(-1,3).tolist();faces=[];uv=[];sides=len(angle)
 for j in range(len(t)-1):
  for k in range(sides):
   kk=(k+1)%sides;faces.append((j*sides+k,j*sides+kk,(j+1)*sides+kk,(j+1)*sides+k));uv.extend([(t[j],k/sides),(t[j],(k+1)/sides),(t[j+1],(k+1)/sides),(t[j+1],k/sides)])
 # Both ends closed. Side rings are tiny at tips, avoiding blunt rods.
 faces.extend([tuple(reversed(range(sides))),tuple((len(t)-1)*sides+k for k in range(sides))]);uv.extend([(0,k/sides) for k in reversed(range(sides))]+[(1,k/sides) for k in range(sides)])
 return verts,faces,uv,(centers,axis,forward,profile)

def material(bpy,color):
 m=bpy.data.materials.new('Mom R17 carved light brown locks');m.use_nodes=True;tree=m.node_tree;n=tree.nodes;p=n.get('Principled BSDF');p.inputs['Base Color'].default_value=(*linear(color),1);p.inputs['Roughness'].default_value=.40;p.inputs['Anisotropic IOR Level'].default_value=.38;p.inputs['Coat Weight'].default_value=.12;p.inputs['Coat Roughness'].default_value=.34
 tex=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');tree.links.new(tex.outputs['UV'],sep.inputs[0]);mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=2*np.pi*58;tree.links.new(sep.outputs['Y'],mul.inputs[0]);wave=n.new('ShaderNodeMath');wave.operation='SINE';tree.links.new(mul.outputs[0],wave.inputs[0]);ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=-.85;ramp.color_ramp.elements[0].color=(*linear('#886344'),1);ramp.color_ramp.elements[1].position=.95;ramp.color_ramp.elements[1].color=(*linear('#AA8560'),1);tree.links.new(wave.outputs[0],ramp.inputs[0]);tree.links.new(ramp.outputs[0],p.inputs['Base Color']);bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.11;bump.inputs['Distance'].default_value=.00022;tree.links.new(wave.outputs[0],bump.inputs['Height']);tree.links.new(bump.outputs[0],p.inputs['Normal']);return m

def build(bpy,rig,settings,color):
 mat=material(bpy,color);objects=[];fiber_paths=[];fiber_radii=[]
 for i,(name,path,w,d) in enumerate(guides(settings)):
  verts,faces,uv,frames=lock_geometry(path,w,d,i);mesh=bpy.data.meshes.new('R17 lock '+name);mesh.from_pydata(verts,[],faces);mesh.update();layer=mesh.uv_layers.new(name='Longitudinal flow');layer.data.foreach_set('uv',np.asarray(uv).ravel())
  for p in mesh.polygons:p.use_smooth=True
  obj=bpy.data.objects.new('HAIR-mom-R17-'+name,mesh);bpy.context.collection.objects.link(obj);mesh.materials.append(mat);world=obj.matrix_world.copy();obj.parent=rig;obj.parent_type='BONE';obj.parent_bone='DEF-Head';bpy.context.view_layer.update();obj.matrix_world=world;objects.append(obj.name)
  centers,axis,forward,profile=frames
  for phi in np.linspace(.18,np.pi-.18,18 if i<6 else 8):
   ridge=1+.028*np.cos(18*phi+i*.63);p=centers+profile[:,None]*ridge*(w*np.cos(phi)*axis+(d+.00009)*np.sin(phi)*forward);fiber_paths.append(p);fiber_radii.append(.000045*profile+.000004)
 fiber=native_curves(bpy,'GROOM-mom-R17-surface-fibers',np.asarray(fiber_paths),np.asarray(fiber_radii),mat,rig)
 return {'objects':objects,'surface_fiber_object':fiber.name,'curves':len(fiber_paths),'locks':len(objects),'method':settings['method'],'single_crown_shell':False,'reference_texture_projection':False}
