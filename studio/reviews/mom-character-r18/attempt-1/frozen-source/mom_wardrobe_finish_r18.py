"""Replace folded box-like collar coordinates with a wider soft standing fold.

Existing garment topology, original assigned weights/modifiers are retained.
Not a cloth simulation or a full wardrobe acceptance claim.
"""
import numpy as np
from mom_groom_r16 import catmull

def apply(bpy):
 records=[]
 for side in (-1,1):
  obj=bpy.data.objects[f'GEO-mom-R16-folded-collar-{side}'];center=catmull([(side*.050,.018,1.337),(side*.075,-.025,1.342),(side*.080,-.082,1.306),(side*.063,-.105,1.256),(side*.040,-.115,1.205)],24);p=[]
  for i,c in enumerate(center):
   for j in range(7):
    u=j/6-.5;point=c.copy();point[0]+=side*u*.050;point[1]-=.006*np.cos(u*np.pi);point[2]+=.008*np.cos(u*np.pi);p.append(point)
  if len(obj.data.vertices)!=len(p):raise ValueError('Expected preserved collar control grid')
  obj.data.vertices.foreach_set('co',np.array(p).ravel());obj.data.update();records.append({'object':obj.name,'vertices':len(p),'topology_weights_modifiers_retained':True,'width_m':.050})
 return {'objects':records,'method':'Wider explicit continuous standing fold, no discontinuous nearest-surface Y jumps. Existing original-rig binding retained.','wardrobe_approved':False,'cloth_simulation_validated':False}
