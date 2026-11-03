"""Deterministic indexed lofts; no Blender dependency. Not an auto-retopology tool."""
from __future__ import annotations
import math
from collections import Counter, defaultdict


class Mesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.weights = []

    def vertex(self, xyz, weights):
        if len(xyz) != 3 or any(not math.isfinite(v) for v in xyz):
            raise ValueError('non-finite vertex')
        if any(not math.isfinite(v) or v < 0 for v in weights.values()):
            raise ValueError('invalid vertex weights')
        total = sum(weights.values())
        if total <= 0:
            raise ValueError('unweighted vertex')
        self.vertices.append(tuple(xyz))
        self.weights.append({name: value/total for name, value in weights.items() if value > 0})
        return len(self.vertices)-1

    def bridge(self, a, b):
        if len(a) != len(b):
            raise ValueError('ring size mismatch')
        for j in range(len(a)):
            k = (j+1) % len(a)
            self.faces.append((a[j], a[k], b[k], b[j]))

    def compact(self):
        used=sorted({v for face in self.faces for v in face})
        mapping={old:new for new,old in enumerate(used)}
        self.vertices=[self.vertices[i] for i in used]
        self.weights=[self.weights[i] for i in used]
        self.faces=[tuple(mapping[i] for i in face) for face in self.faces]

    def cap(self, ring):
        self.faces.append(tuple(reversed(ring)))


def topology(vertices, faces):
    edges = Counter()
    graph = defaultdict(set)
    for face in faces:
        if len(set(face)) != len(face) or len(face) < 3:
            raise ValueError('degenerate face')
        for a, b in zip(face, face[1:]+face[:1]):
            if not 0 <= a < len(vertices) or not 0 <= b < len(vertices):
                raise ValueError('face index outside mesh')
            edge = tuple(sorted((a, b)))
            edges[edge] += 1
            graph[a].add(b)
            graph[b].add(a)
    remaining = set(range(len(vertices)))
    components = 0
    while remaining:
        stack = [remaining.pop()]
        components += 1
        while stack:
            v = stack.pop()
            neighbors = graph[v].intersection(remaining)
            remaining.difference_update(neighbors)
            stack.extend(neighbors)
    return {'vertices': len(vertices), 'faces': len(faces), 'components': components,
            'boundary_edges': sum(n == 1 for n in edges.values()),
            'nonmanifold_edges': sum(n != 2 for n in edges.values()),
            'quad_fraction': sum(len(f) == 4 for f in faces)/len(faces) if faces else 0}


def smooth(value):
    t = min(1.0, max(0.0, value))
    return t*t*(3-2*t)


def sweater():
    """One closed surface: torso + sewn sleeve holes, no overlapping shoulder balls."""
    mesh = Mesh()
    levels = [(1.04,.37,.235),(1.08,.38,.24),(1.15,.405,.25),(1.30,.44,.275),
              (1.50,.435,.26),(1.64,.43,.245),(1.76,.425,.22),(1.84,.35,.19),
              (1.90,.18,.15),(1.93,.15,.14)]
    rings = []
    n = 32
    for z, rx, ry in levels:
        chest = smooth((z-1.25)/.43)
        weights = {'pelvis':1-chest, 'chest':chest}
        rings.append([mesh.vertex((rx*math.cos(2*math.pi*j/n),ry*math.sin(2*math.pi*j/n),z),weights) for j in range(n)])
    holes = {'R':set([30,31,0,1]),'L':set([14,15,16,17])}
    removed = {'R':[], 'L':[]}
    for k in range(len(rings)-1):
        for j in range(n):
            face=(rings[k][j],rings[k][(j+1)%n],rings[k+1][(j+1)%n],rings[k+1][j])
            side=next((s for s,indices in holes.items() if k in (5,6) and j in indices),None)
            if side:removed[side].append(face)
            else:mesh.faces.append(face)
    mesh.cap(rings[0]);mesh.cap(rings[-1])
    for side, sign in [('R',1),('L',-1)]:
        edges=Counter(tuple(sorted((a,b))) for f in removed[side] for a,b in zip(f,f[1:]+f[:1]))
        boundary={a for edge,count in edges.items() if count==1 for a in edge}
        # Project the boundary to its side plane; preserve its cyclic edge order.
        center=(sum(mesh.vertices[i][1] for i in boundary)/len(boundary),sum(mesh.vertices[i][2] for i in boundary)/len(boundary))
        hole=sorted(boundary,key=lambda i:math.atan2(mesh.vertices[i][2]-center[1],mesh.vertices[i][1]-center[0]))
        if {tuple(sorted((a,b))) for a,b in zip(hole,hole[1:]+hole[:1])}!={e for e,c in edges.items() if c==1}:
            raise ValueError('sleeve boundary ordering failed')
        angles=[math.atan2(mesh.vertices[i][2]-center[1],mesh.vertices[i][1]-center[0]) for i in hole]
        previous=hole
        for k in range(18):
            t=.15+.85*k/17
            if t<=.5:
                q=t*2;xyz=(sign*(.40+.27*q),-.015*q,1.79-.32*q);dx,dz=sign*.27,-.32
            else:
                q=t*2-1;xyz=(sign*(.67+.08*q),-.015+.035*q,1.47-.36*q);dx,dz=sign*.08,-.36
            length=math.hypot(dx,dz);vx,vz=-dz/length,dx/length
            # v should have +Z on both mirrored sides to match the hole angles.
            if vz<0:vx,vz=-vx,-vz
            w=smooth((t-.39)/.22);radius=.13*(1-.28*t)
            weights={f'upper_arm.{side}':1-w,f'forearm.{side}':w}
            ring=[mesh.vertex((xyz[0]+radius*math.sin(a)*vx,xyz[1]+radius*math.cos(a),xyz[2]+radius*math.sin(a)*vz),weights) for a in angles]
            mesh.bridge(previous,ring);previous=ring
        mesh.cap(previous)
    mesh.compact()
    return mesh


def pants():
    """Closed pair-of-pants surface, shared crotch edges and knee deformation loops."""
    mesh=Mesh();rings=[];n=32
    for z,rx,ry in [(1.15,.35,.225),(1.09,.365,.23),(1.02,.35,.23)]:
        rings.append([mesh.vertex((rx*math.cos(2*math.pi*j/n),ry*math.sin(2*math.pi*j/n),z),{'pelvis':1}) for j in range(n)])
    mesh.bridge(rings[0],rings[1]);mesh.bridge(rings[1],rings[2]);mesh.cap(rings[0])
    crotch=[mesh.vertex((0,y,z),{'pelvis':1}) for y,z in [(-.12,.93),(0,.89),(.12,.93)]]
    for side,sign in [('R',1),('L',-1)]:
        if sign==1:loop=[rings[-1][j%n] for j in range(8,-9,-1)]+crotch
        else:loop=[rings[-1][j%n] for j in range(8,25)]+crotch
        # The same waist-centre/crotch edges are shared by the two legs.
        loop=sorted(loop,key=lambda i:math.atan2(mesh.vertices[i][1],mesh.vertices[i][0]-sign*.20))
        angles=[math.atan2(mesh.vertices[i][1],mesh.vertices[i][0]-sign*.20) for i in loop]
        previous=loop
        for z,rx,ry in [(.87,.165,.18),(.82,.16,.175),(.73,.145,.155),(.68,.14,.15),(.64,.138,.15),(.60,.135,.15),(.55,.135,.15),(.44,.13,.145),(.31,.12,.135),(.24,.115,.13)]:
            cy=.035*max(0,1-abs(z-.64)/.44)
            lower=smooth((.73-z)/.18)
            weights={f'thigh.{side}':1-lower,f'shin.{side}':lower}
            ring=[mesh.vertex((sign*.215+rx*math.cos(a),cy+ry*math.sin(a),z),weights) for a in angles]
            mesh.bridge(previous,ring);previous=ring
        mesh.cap(previous)
    return mesh


def shoe(sign):
    mesh=Mesh();previous=None;bottom=None
    for z,rx,ry,cy in [(0,.15,.25,.07),(.025,.17,.28,.07),(.08,.175,.28,.07),(.16,.16,.26,.065),(.24,.11,.14,.015)]:
        ring=[]
        for j in range(24):
            angle=2*math.pi*j/24
            x,y=math.cos(angle),math.sin(angle)
            ring.append(mesh.vertex((sign*.215+rx*math.copysign(abs(x)**.65,x),cy+ry*math.copysign(abs(y)**.65,y),z),{f'foot.{"R" if sign>0 else "L"}':1}))
        if previous:mesh.bridge(previous,ring)
        else:bottom=ring;mesh.cap(ring)
        previous=ring
    mesh.cap(previous)
    return mesh,[bottom[j] for j in (0,6,12,18)]
