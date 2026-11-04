"""Explicit native actuator policies. A key value is NOT the whole rig pose.

Historical solver could select Z on one mouth corner and Y on the other because
both axes feed Smile. Those axes also produce different skeletal motion. Keep
historical receipts unchanged and calibrate a COMMON authored axis on both sides.
"""
import rain_mom_pass_a2 as legacy


def calibrate_pair(evaluate,commit,readback,target,axis=2):
    if axis not in (0,1,2):raise ValueError('Invalid actuator axis')
    solutions={side:legacy.solve_control(lambda value: evaluate(side,axis,value),target) for side in ('L','R')}
    for side,result in solutions.items():commit(side,axis,result['input'])
    actual={side:float(readback(side)) for side in ('L','R')}
    if any(abs(value-target)>1e-4 for value in actual.values()):raise ValueError('Paired final key readback differs; do not report a symmetric pose')
    return {'policy':'Same native actuator axis on both sides, all other channels retained at neutral; final readback after BOTH commits.',
            'axis':axis,'target':target,'solutions':solutions,'final_key_values':actual,
            'scope':'Consistent actuator selection, not proof of geometric or artistic symmetry.'}


def set_symmetric_smile(bpy,rig,target):
    names={s:f'ACT-Lips_Corner.{s}' for s in ('L','R')}
    originals={s:rig.pose.bones[name].location.copy() for s,name in names.items()}
    keys=bpy.data.objects['GEO-rain-head'].data.shape_keys
    def update():rig.update_tag();bpy.context.view_layer.update()
    def evaluate(side,axis,value):
        bone=rig.pose.bones[names[side]];bone.location=originals[side];bone.location[axis]=value;update()
        response=float(keys.key_blocks[f'Smile.{side}'].value)
        bone.location=originals[side];update();return response
    def commit(side,axis,value):
        bone=rig.pose.bones[names[side]];bone.location=originals[side];bone.location[axis]=value;update()
    def readback(side):return keys.key_blocks[f'Smile.{side}'].value
    result=calibrate_pair(evaluate,commit,readback,target,axis=2)
    result['bones']=names
    result['final_locations']={s:list(rig.pose.bones[name].location) for s,name in names.items()}
    return result
