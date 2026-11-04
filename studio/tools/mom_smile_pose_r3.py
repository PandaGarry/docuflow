"""Limited balanced native smile pose; no mesh changes or driver replacement."""
import mom_face_controls as paired


def set_paired_key(bpy,rig,key,target,axis):
    names={s:f'ACT-Lips_Corner.{s}' for s in ('L','R')}
    original={s:rig.pose.bones[n].location.copy() for s,n in names.items()}
    keys=bpy.data.objects['GEO-rain-head'].data.shape_keys
    def update():rig.update_tag();bpy.context.view_layer.update()
    def evaluate(side,channel,value):
        bone=rig.pose.bones[names[side]];bone.location=original[side];bone.location[channel]=value;update()
        result=float(keys.key_blocks[f'{key}.{side}'].value);bone.location=original[side];update();return result
    def commit(side,channel,value):
        bone=rig.pose.bones[names[side]];bone.location=original[side];bone.location[channel]=value;update()
    return paired.calibrate_pair(evaluate,commit,lambda s:keys.key_blocks[f'{key}.{s}'].value,target,axis)


def set_warm_smile(bpy,rig,amount=1):
    if not 0<=amount<=1:raise ValueError('Pose amount outside authored range')
    up=set_paired_key(bpy,rig,'LipsUp',.3*amount,axis=1)
    smile=set_paired_key(bpy,rig,'Smile',.6*amount,axis=2)
    keys=bpy.data.objects['GEO-rain-head'].data.shape_keys
    values={f'{key}.{s}':float(keys.key_blocks[f'{key}.{s}'].value) for key in ('Smile','LipsUp','LipsWide') for s in ('L','R')}
    for key in ('Smile','LipsUp','LipsWide'):
        if abs(values[f'{key}.L']-values[f'{key}.R'])>1e-4:raise ValueError('Final bilateral responses differ')
    return {'LipsUp_policy':up,'Smile_policy':smile,'final_keys':values,
            'scope':'One authored closed-mouth smile pose, not full acting or lip-sync acceptance.'}
