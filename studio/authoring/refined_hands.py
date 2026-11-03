"""R5 thumb-root spatial skin field. Frozen R4 geometry is not rewritten.

An interpolated weight field on the cage need not remain smooth in *space*
after nonlinear palm/thenar sculpting. Refit thumb/hand influence to the final
rest geometry, keeping the original phalangeal distribution and probe IDs.
This is a technical correction, not anatomical or artistic acceptance.
"""
from __future__ import annotations
import math
from .lookdev import hand as hand_r4
from .refined_body import digits
from .mesh import smooth


def thumb_influence(point, sign):
    """C1 axial onset and radial falloff in the anatomical rest-thumb frame."""
    points=digits(sign)['thumb'];a,b=points[0],points[-1]
    axis=tuple(b[k]-a[k] for k in range(3));length2=sum(v*v for v in axis)
    t=sum((point[k]-a[k])*axis[k] for k in range(3))/length2
    radius=math.sqrt(sum((point[k]-a[k]-t*axis[k])**2 for k in range(3)))
    return smooth((t+.02)/.20)*(1-smooth((radius-.025)/.020))


def hand(sign):
    mesh,tips=hand_r4(sign);side='R' if sign>0 else 'L';palm=f'hand.{side}'
    for i,(point,weights) in enumerate(zip(mesh.vertices,mesh.weights)):
        # Never steal influences from another digit or from the forearm anchor.
        if any(k!=palm and not k.startswith('thumb.') for k in weights):continue
        amount=thumb_influence(point,sign)
        chain={k:v for k,v in weights.items() if k.startswith('thumb.')}
        total=sum(chain.values())
        chain={k:v/total for k,v in chain.items()} if total else {f'thumb.01.{side}':1}
        result={k:v*amount for k,v in chain.items() if v*amount>0}
        if amount<1:result[palm]=1-amount
        mesh.weights[i]=result
    return mesh,tips
