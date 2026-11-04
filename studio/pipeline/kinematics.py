"""Geometry-based stance and finger probes. These are not an artistic/gait judge."""
from __future__ import annotations
import math
from .contracts import ContractError


def contact_audit(rows, contacts, probes, frame_range):
    start,end=frame_range
    if [r['frame'] for r in rows] != list(range(start,end)):
        raise ContractError('kinematic measurement coverage mismatch')
    ground={p['id']:p['ground_z'] for p in probes}
    worst_slip=worst_height=penetration=0.0
    for row in rows:
        for name,z in ground.items():
            points=row['contact_points_world'].get(name)
            if not points or any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in points):
                raise ContractError('invalid/missing evaluated sole points')
            penetration=max(penetration,max(z-p[2] for p in points))
    covered=set()
    for interval in contacts:
        name=interval['probe'];a,b=interval['frame_range']
        if name not in ground or not start<=a<b<=end:
            raise ContractError('invalid stance interval')
        selected=rows[a-start:b-start]
        anchor=selected[0]['contact_points_world'][name]
        for row in selected:
            key=(name,row['frame'])
            if key in covered:raise ContractError('overlapping stance intervals')
            covered.add(key)
            points=row['contact_points_world'][name]
            if len(points)!=len(anchor):raise ContractError('sole probe point count changed')
            worst_slip=max(worst_slip,max(math.dist(p[:2],a[:2]) for p,a in zip(points,anchor)))
            worst_height=max(worst_height,max(abs(p[2]-ground[name]) for p in points))
    if not covered:raise ContractError('no stance measurements requested')
    return {'passed':worst_slip<=.005 and worst_height<=.003 and penetration<=.002,
            'stance_slip_m':worst_slip,'stance_ground_error_m':worst_height,
            'sole_penetration_m':max(0,penetration),'stance_samples':len(covered),
            'limits_m':{'stance_slip':.005,'ground_error':.003,'penetration':.002}}


def finger_audit(rows, checks):
    result={}
    for check in checks:
        name=check['probe']
        try:points=[r['fingertips_local'][name] for r in rows]
        except KeyError as exc:raise ContractError('missing evaluated fingertip') from exc
        if not points or any(len(p)!=3 or any(not math.isfinite(v) for v in p) for p in points):
            raise ContractError('invalid fingertip measurement')
        span=max(math.dist(a,b) for a in points for b in points)
        result[name]={'span_m':span,'min_span_m':check['min_span_m'],'passed':span>=check['min_span_m']}
    return {'passed':bool(result) and all(r['passed'] for r in result.values()),'fingers':result}
