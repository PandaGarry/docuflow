"""R5: smooth the inherited thumb-root weights on final R4 rest geometry.

Inverse-square edge conductance follows actual final vertex spacing, unlike
interpolation on an earlier cage. Full-hand/full-thumb anchors and phalangeal
ratios stay fixed. Geometry, topology and probe indices are unchanged.
Not an anatomy/beauty/collision or complete corrective-rig implementation.
"""
from __future__ import annotations
from .lookdev import hand as hand_r4


def smooth_thumb_weights(mesh,side,iterations=48):
    if side not in ('R','L'):raise ValueError('invalid hand side')
    if type(iterations) is not int or not 0<=iterations<=200:raise ValueError('invalid iteration count')
    palm=f'hand.{side}';values=[];active=[];adj=[set() for _ in mesh.vertices]
    for weights in mesh.weights:
        total=sum(v for k,v in weights.items() if k.startswith('thumb.'))
        values.append(total)
        active.append(0<total<1 and weights.get(palm,0)>0 and all(k==palm or k.startswith('thumb.') for k in weights))
    for face in mesh.faces:
        for a,b in zip(face,face[1:]+face[:1]):adj[a].add(b);adj[b].add(a)
    conductance={}
    for i,enabled in enumerate(active):
        if not enabled:continue
        row=[(j,1/max(1e-16,sum((a-b)**2 for a,b in zip(mesh.vertices[i],mesh.vertices[j])))) for j in sorted(adj[i])]
        total=sum(v for j,v in row);conductance[i]=[(j,v/total) for j,v in row]
    for _ in range(iterations):
        updated=values.copy()
        for i,row in conductance.items():updated[i]=.5*values[i]+.5*sum(w*values[j] for j,w in row)
        values=updated
    for i in conductance:
        old=mesh.weights[i];chain={k:v for k,v in old.items() if k.startswith('thumb.')};total=sum(chain.values())
        amount=values[i];result={k:v/total*amount for k,v in chain.items()}
        result[palm]=1-amount
        mesh.weights[i]=result
    return mesh


def hand(sign):
    mesh,tips=hand_r4(sign)
    smooth_thumb_weights(mesh,'R' if sign>0 else 'L')
    return mesh,tips
