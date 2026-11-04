"""Explicit 3D lock edge contours, replacing centerline-wide ribbon guesses.

Reference XZ outlines are manual design guides. Independently authored Y/depth,
closed volume, real scalp contact and native multi-view renders establish 3D.
No canonical pixels are sampled into a texture; no single crown shell exists.
"""
import numpy as np
from mom_head_surface_r2 import cubic_curve
# Outer pixel X/Y, inner pixel X/Y, outer world Y, inner world Y.
CONTOURS=[('left-continuous-wave',[
 [408,25,410,100,-.035,-.112],[350,8,411,125,.005,-.120],
 [244,24,400,180,.020,-.146],[157,97,370,245,.040,-.160],
 [118,184,324,296,.025,-.170],[93,298,258,330,.005,-.160],
 [71,384,204,385,-.020,-.146],[36,456,163,434,-.015,-.120],
 [13,516,151,501,-.015,-.110],[29,580,186,574,.005,-.105],
 [47,637,182,638,.020,-.085],[38,704,156,718,.015,-.085],
 [11,771,117,780,-.005,-.095],[8,806,68,822,-.040,-.105],
 [10,812,12,812,-.080,-.082]],.025),
 ('right-swept-fringe',[
 [412,28,414,100,-.035,-.112],[463,11,414,125,.010,-.120],
 [575,53,441,188,.035,-.150],[640,151,479,251,.035,-.166],
 [678,275,516,315,.015,-.166],[710,369,577,377,-.040,-.150],
 [725,415,641,427,-.090,-.133],[718,419,716,420,-.118,-.120]],.026),
 ('right-long-wave',[
 [465,60,470,65,.025,.020],[581,65,568,135,.070,-.040],
 [664,180,629,246,.050,-.070],[697,300,656,367,.020,-.070],
 [731,420,640,440,-.005,-.110],[741,514,650,514,-.005,-.110],
 [703,590,628,589,.010,-.095],[710,671,636,675,.010,-.090],
 [745,755,671,770,-.005,-.105],[764,808,719,825,-.050,-.110],
 [757,819,759,819,-.085,-.086]],.023)]

def guides(settings):
 m=settings['meters_per_pixel'];cx=settings['pixel_origin_x'];ey=settings['eye_y'];z=settings['eye_z_m'];out=[]
 for name,rows,depth in CONTOURS:
  rows=np.asarray(rows,float);outer=np.stack(((rows[:,0]-cx)*m,rows[:,4],z-(rows[:,1]-ey)*m),1);inner=np.stack(((rows[:,2]-cx)*m,rows[:,5],z-(rows[:,3]-ey)*m),1);out.append((name,outer,inner,depth))
 return out

def geometry(outer,inner,depth,index):
 c=(outer+inner)/2;s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(c,axis=0),axis=1))];s/=s[-1];t=np.linspace(0,1,128)
 o=np.stack([cubic_curve(t,s,outer[:,i]) for i in range(3)],1);inside=np.stack([cubic_curve(t,s,inner[:,i]) for i in range(3)],1);center=(o+inside)/2;edge=(o-inside)/2
 a=np.linspace(0,2*np.pi,64,endpoint=False);depth_profile=cubic_curve(t,[0,.08,.23,.7,.92,1],[.10,.65,1,1,.70,.025])
 rings=center[:,None,:]+edge[:,None,:]*np.cos(a)[None,:,None]
 # Physical longitudinal relief, not alternating high-contrast paint stripes.
 relief=1+.055*np.cos(14*a[None,:]+.25*np.sin(t[:,None]*5)+index*.7)
 rings[:,:,1]-=depth*depth_profile[:,None]*np.sin(a)[None,:]*relief
 vertices=rings.reshape(-1,3);faces=[];uv=[];n=len(a)
 for j in range(len(t)-1):
  for k in range(n):
   kk=(k+1)%n;faces.append((j*n+k,j*n+kk,(j+1)*n+kk,(j+1)*n+k));uv.extend([(t[j],k/n),(t[j],(k+1)/n),(t[j+1],(k+1)/n),(t[j+1],k/n)])
 faces.extend([tuple(reversed(range(n))),tuple((len(t)-1)*n+k for k in range(n))]);uv.extend([(0,k/n) for k in reversed(range(n))]+[(1,k/n) for k in range(n)])
 # Set outward winding from the actual front surface, not handedness guesses.
 f=faces[64*64+16];a0,a1,a2=vertices[list(f[:3])];normal=np.cross(a1-a0,a2-a0)
 if normal[1]>0:
  reordered=[];offset=0
  for face in faces:reordered.extend(reversed(uv[offset:offset+len(face)]));offset+=len(face)
  faces=[tuple(reversed(f)) for f in faces];uv=reordered
 return vertices,faces,uv

def tress_paths(settings):
 """Use the envelope as flow guidance, never as a wide shell surface."""
 result=[]
 for i,(name,outer,inner,depth) in enumerate(guides(settings)):
  center=(outer+inner)/2;s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(center,axis=0),axis=1))];s/=s[-1];t=np.linspace(0,1,128)
  o=np.stack([cubic_curve(t,s,outer[:,k]) for k in range(3)],1);inside=np.stack([cubic_curve(t,s,inner[:,k]) for k in range(3)],1);count=(9,9,7)[i]
  for j in range(count):
   f=(j+.5)/count;path=o*(1-f)+inside*f;path[:,1]-=depth*np.sqrt(1-(2*f-1)**2)*cubic_curve(t,[0,.1,.8,1],[.1,1,1,.03])
   tangent=np.gradient(path,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None];separation=(inside-o)/count;perp=separation-tangent*np.einsum('ij,ij->i',separation,tangent)[:,None]
   radius=np.clip(.65*np.linalg.norm(separation[:,[0,2]],axis=1),.00012,.008);radius*=cubic_curve(t,[0,.025,.08,.92,1],[.04,.65,1,1,.25]);radius*=.98+.02*np.cos(j*.9+t*3)
   result.append((name+f'-tress-{j:02}',path,radius))
 return result

def tube(path,radius):
 t=np.gradient(path,axis=0);t/=np.linalg.norm(t,axis=1)[:,None];axis=np.stack((-t[:,2],np.zeros(len(t)),t[:,0]),1);axis/=np.linalg.norm(axis,axis=1)[:,None];front=np.cross(t,axis);front/=np.linalg.norm(front,axis=1)[:,None]
 a=np.linspace(0,2*np.pi,24,endpoint=False);relief=1+.015*np.cos(8*a);rings=path[:,None,:]+radius[:,None,None]*relief[None,:,None]*(np.cos(a)[None,:,None]*axis[:,None,:]+.78*np.sin(a)[None,:,None]*front[:,None,:]);vertices=rings.reshape(-1,3);faces=[];uv=[];n=len(a)
 for j in range(len(t)-1):
  for k in range(n):
   kk=(k+1)%n;faces.append((j*n+k,j*n+kk,(j+1)*n+kk,(j+1)*n+k));uv.extend([(j/(len(t)-1),k/n),(j/(len(t)-1),(k+1)/n),((j+1)/(len(t)-1),(k+1)/n),((j+1)/(len(t)-1),k/n)])
 faces.extend([tuple(reversed(range(n))),tuple((len(t)-1)*n+k for k in range(n))]);uv.extend([(0,k/n) for k in reversed(range(n))]+[(1,k/n) for k in range(n)])
 return vertices,faces,uv,rings

def build(bpy,rig,settings,mat):
 from mathutils import Vector
 from mathutils.bvhtree import BVHTree
 from mom_groom_r16 import native_curves
 head=bpy.data.objects['GEO-rain-head'];ev=head.evaluated_get(bpy.context.evaluated_depsgraph_get());skin=ev.to_mesh();bvh=BVHTree.FromPolygons([head.matrix_world@v.co for v in skin.vertices],[list(p.vertices) for p in skin.polygons]);ev.to_mesh_clear();objects=[];paths=[];radii=[];contact=0
 for i,(name,path,radius) in enumerate(tress_paths(settings)):
  for j,point in enumerate(path):
   if point[2]<1.44:continue
   hit,normal,index,distance=bvh.ray_cast(Vector((point[0],-1,point[2])),Vector((0,1,0)),2)
   if hit is not None:
    target=hit.y-radius[j]-.004;y=point[1];f=np.clip((point[2]-1.44)/.06,0,1);f=f*f*(3-2*f);clear=.5*(y+target-np.sqrt((y-target)**2+.001**2));path[j,1]=y+f*(clear-y);contact+=int(y>target)
  p,faces,uv,rings=tube(path,radius);mesh=bpy.data.meshes.new('R17 rounded tress '+name);mesh.from_pydata(p.tolist(),[],faces);mesh.update();layer=mesh.uv_layers.new(name='Longitudinal flow');layer.data.foreach_set('uv',np.asarray(uv).ravel())
  for poly in mesh.polygons:poly.use_smooth=True
  obj=bpy.data.objects.new('HAIR-mom-R17-'+name,mesh);bpy.context.scene.collection.objects.link(obj);mesh.materials.append(mat);world=obj.matrix_world.copy();obj.parent=rig;obj.parent_type='BONE';obj.parent_bone='DEF-Head';bpy.context.view_layer.update();obj.matrix_world=world;objects.append(obj.name)
  for k in (3,6,9):
   q=rings[:,k].copy();q[:,1]-=.00004;paths.append(q);radii.append(np.minimum(radius*.012,.00004))
 fiber=native_curves(bpy,'GROOM-mom-R17-contour-surface-fibers',np.array(paths),np.array(radii),mat,rig)
 return objects,fiber.name,{'scalp_front_surface_contacts':contact,'front_tresses':len(objects),'source':'Contour-guided individually rounded volumetric tresses, independently authored depth and actual scalp clearance. NO broad shell mesh; no canonical texture projection.'}
