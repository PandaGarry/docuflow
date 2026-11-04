"""Deterministic native strand groom: parted swept waves, no solid crown shell."""
import numpy as np

def catmull(points,samples=44):
 p=np.asarray(points,float);p=np.vstack([p[0],p,p[-1]]);u=np.linspace(0,len(points)-1,samples);i=np.minimum(u.astype(int),len(points)-2);t=(u-i)[:,None]
 a,b,c,d=p[i],p[i+1],p[i+2],p[i+3]
 return .5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)

def guides():
 result=[]
 for side in (-1,1):
  for j in range(8):
   y=-.055+j*.020;phase=j*.8
   result.append((f'curtain-{side}-{j}',[(side*.003,y,1.644),(side*.057,y-.032,1.626),(side*.111,y-.050,1.559),(side*.137,y-.045,1.463),(side*(.144+.007*np.sin(phase)),y-.025,1.353),(side*.123,y-.014,1.262),(side*.156,y-.019,1.193+.009*np.sin(phase))],.013))
  for j in range(6):
   result.append((f'swept-fringe-{side}-{j}',[(side*.003,-.038+j*.008,1.648),(side*.034,-.118+j*.004,1.617),(side*(.071+j*.005),-.153+j*.003,1.566-j*.003),(side*(.115+j*.006),-.139+j*.004,1.503-j*.004),(side*.149,-.108+j*.005,1.455),(side*.138,-.092+j*.004,1.34),(side*.123,-.080+j*.004,1.261),(side*.16,-.073+j*.003,1.199+j*.003)],.012))
 for j,angle in enumerate(np.linspace(.06,np.pi-.06,18)):
  x=np.cos(angle);y=np.sin(angle);side=np.sign(x)
  result.append((f'back-{j}',[(side*.003,.03+.05*y,1.641),(.063*x,.083*y,1.618),(.117*x,.130*y,1.55),(.142*x,.143*y,1.44),(.145*x,.132*y,1.34),(.13*x,.123*y,1.26),(.151*x,.13*y,1.197+.01*np.cos(j))],.014))
 # Smooth curved root envelope, not constant-height stacked root plates.
 for name,points,width in result:
  for k in (0,1):
   x,y,z=points[k];rho=(x/.137)**2+((y+.015)/.151)**2
   points[k]=(x,y,1.49+.163*np.sqrt(max(.04,1-rho)))
  if name.startswith('swept-fringe--1'):
   x,y,z=points[2];points[2]=(x*.92,y,z-.016)
  for k,(x,y,z) in enumerate(points):
   if z<1.45:points[k]=(x,y,1.45+(z-1.45)*.68)
 return result

def fibers(settings):
 rng=np.random.default_rng(settings['seed']);paths=[];radii=[];groups=[];n=settings['samples_per_strand'];t=np.linspace(0,1,n)
 for name,guide,width in guides():
  center=catmull(guide,n);tangent=np.gradient(center,axis=0);axis=np.cross(tangent,np.array([0,0,1.]));axis/=np.maximum(np.linalg.norm(axis,axis=1)[:,None],1e-8)
  # Crown tangent may be near vertical: this frame remains continuous below it.
  depth=np.cross(tangent,axis);depth/=np.maximum(np.linalg.norm(depth,axis=1)[:,None],1e-8)
  start=len(paths)
  for k in range(settings['strands_per_bundle']):
   a,b=rng.normal(0,.46,2);a=np.clip(a,-1,1);b=np.clip(b,-1,1)
   spread=width*(.25+.75*np.sin(np.pi*t)**.55)*(1-.5*t)
   offset=axis*(a*spread)[:,None]+depth*(b*spread*.58)[:,None]
   wiggle=np.sin(t*18+rng.uniform(0,6))*rng.uniform(.00015,.0005)*np.sin(np.pi*t)
   p=center+offset+axis*wiggle[:,None]
   p[-1,2]+=rng.uniform(-.008,.008);paths.append(p)
   radii.append(settings['fiber_radius_m']*rng.uniform(.8,1.2)*(.75+.25*np.sin(np.pi*t))*(1-.94*t**5))
  groups.append({'name':name,'first_curve':start,'curves':len(paths)-start})
 start=len(paths)
 for k in range(64):
  guide=guides()[int(rng.integers(0,len(guides())))][1];center=catmull(guide,n);stop=rng.uniform(.28,.6);u=t*stop
  p=np.stack([np.interp(u,t,center[:,axis]) for axis in range(3)],axis=1)
  p[:,0]+=np.sign(p[-1,0])*.0025*np.sin(np.pi*t);p[:,1]-=.0015*np.sin(np.pi*t)
  paths.append(p);radii.append(settings['fiber_radius_m']*.4*(1-.97*t**3))
 groups.append({'name':'fine crown flyaways','first_curve':start,'curves':64})
 return np.asarray(paths),np.asarray(radii),groups

def native_curves(bpy,name,paths,radii,material,rig=None):
 paths=np.asarray(paths);data=bpy.data.hair_curves.new(name);data.add_curves([paths.shape[1]]*paths.shape[0])
 data.attributes['position'].data.foreach_set('vector',paths.astype(np.float32).ravel())
 radius=data.attributes.get('radius') or data.attributes.new('radius','FLOAT','POINT');radius.data.foreach_set('value',np.asarray(radii,dtype=np.float32).ravel())
 data.materials.append(material);obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
 if rig:
  world=obj.matrix_world.copy();obj.parent=rig;obj.parent_type='BONE';obj.parent_bone='DEF-Head';bpy.context.view_layer.update();obj.matrix_world=world
 return obj

def hair_material(bpy,color):
 from rain_mom_pass import linear_color
 m=bpy.data.materials.new('Mom R15 light brown strand fiber');m.use_nodes=True;n=m.node_tree.nodes;n.clear();out=n.new('ShaderNodeOutputMaterial');hair=n.new('ShaderNodeBsdfHairPrincipled');hair.parametrization='MELANIN';hair.inputs['Melanin'].default_value=.55 if color!='#9A7856' else .42;hair.inputs['Melanin Redness'].default_value=.25;hair.inputs['Roughness'].default_value=.42
 if 'Radial Roughness' in hair.inputs:hair.inputs['Radial Roughness'].default_value=.48
 m.node_tree.links.new(hair.outputs[0],out.inputs['Surface']);return m

def build(bpy,rig,settings):
 p,r,groups=fibers(settings);material=hair_material(bpy,settings['hair_color_srgb']);obj=native_curves(bpy,'GROOM-mom-R15-parted-waves',p,r,material,rig)
 return {'object':obj.name,'type':obj.type,'curves':len(p),'points':p.shape[0]*p.shape[1],'bounds_min_m':p.reshape(-1,3).min(0).tolist(),'bounds_max_m':p.reshape(-1,3).max(0).tolist(),'guide_groups':groups,'solid_crown_cap':False,'attachment':'Original DEF-Head bone; rigid groom, shoulder dynamics not certified','method':'Native HAIR curves, swept center part, layered clumped waves and independently tapered strand tips; original Rain short hair retained hidden.'}
