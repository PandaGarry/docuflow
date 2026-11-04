"""R3 indexed hand/shoulder authoring. R2 recipes remain immutable evidence.

Connected surfaces and clean edge incidence are not collision/art approval.
"""
from __future__ import annotations
from collections import defaultdict
import math
from .mesh import Mesh, smooth, sweater


def digits(sign):
    wrist = (sign * .75, .02, 1.11)
    result = {}
    for j, (name, length) in enumerate(zip(('index', 'middle', 'ring', 'pinky'), (.115, .13, .125, .10))):
        base = (wrist[0] + sign * (j - 1.5) * .034, wrist[1], wrist[2] - .105)
        result[name] = [(base[0], base[1] + .006 * t, base[2] - length * t) for t in (0, .4, .75, 1)]
    base = (wrist[0] - sign * .07, wrist[1] + .008, wrist[2] - .04)
    result['thumb'] = [(base[0] - sign * .07 * t, base[1] + .01 * t, base[2] - .085 * t) for t in (0, .4, .75, 1)]
    return result


def subdivide(mesh):
    """One closed-manifold Catmull-Clark level, including interpolated skin weights.

    Old vertex IDs remain stable, so tip-ring probes keep their correspondence.
    This is authoring geometry, not a runtime topology-changing modifier.
    """
    edges = defaultdict(list)
    incident = defaultdict(list)
    for fi, face in enumerate(mesh.faces):
        for v in face:
            incident[v].append(fi)
        for a, b in zip(face, face[1:] + face[:1]):
            edges[tuple(sorted((a, b)))].append(fi)
    if any(len(fs) != 2 for fs in edges.values()) or len(incident) != len(mesh.vertices):
        raise ValueError('subdivision requires a closed mesh without unused vertices')
    out = Mesh()

    def average(ids):
        return tuple(sum(mesh.vertices[i][k] for i in ids) / len(ids) for k in range(3)), {
            name: sum(mesh.weights[i].get(name, 0) for i in ids) / len(ids)
            for name in {b for i in ids for b in mesh.weights[i]}}

    faces = [average(face) for face in mesh.faces]
    neighbors = defaultdict(set)
    for a, b in edges:
        neighbors[a].add(b); neighbors[b].add(a)
    for i, point in enumerate(mesh.vertices):
        n = len(neighbors[i])
        if n < 3 or len(incident[i]) != n:
            raise ValueError('nonmanifold vertex fan')
        # (F + 2R + (n-3)P)/n; R is average edge midpoint.
        coefficients = defaultdict(float)
        coefficients[i] += (n - 2) / n
        for j in neighbors[i]:
            coefficients[j] += 1 / (n * n)
        for fi in incident[i]:
            for j in mesh.faces[fi]:
                coefficients[j] += 1 / (n * n * len(mesh.faces[fi]))
        xyz = [sum(mesh.vertices[j][k] * w for j, w in coefficients.items()) for k in range(3)]
        weights = {b: sum(mesh.weights[j].get(b, 0) * w for j, w in coefficients.items())
                   for b in {b for j in coefficients for b in mesh.weights[j]}}
        out.vertex(xyz, weights)
    face_ids = [out.vertex(xyz, weights) for xyz, weights in faces]
    edge_ids = {}
    for edge, fs in sorted(edges.items()):
        xyz, weights = average(edge)
        xyz = [(2 * xyz[k] + faces[fs[0]][0][k] + faces[fs[1]][0][k]) / 4 for k in range(3)]
        weights = {b: (2 * weights.get(b, 0) + faces[fs[0]][1].get(b, 0) + faces[fs[1]][1].get(b, 0)) / 4
                   for b in set(weights) | set(faces[fs[0]][1]) | set(faces[fs[1]][1])}
        edge_ids[edge] = out.vertex(xyz, weights)
    for fi, face in enumerate(mesh.faces):
        for j, v in enumerate(face):
            out.faces.append((v, edge_ids[tuple(sorted((v, face[(j+1) % len(face)])))],
                              face_ids[fi], edge_ids[tuple(sorted((face[j-1], v)))]))
    return out


def hand(sign, refine=True):
    """Palm with five sewn apertures; no overlapping palm/finger shells."""
    if sign not in (-1, 1):
        raise ValueError('hand side must be -1 or +1')
    mesh = Mesh(); side = 'R' if sign > 0 else 'L'
    wrist = (sign * .75, .02, 1.11)
    centers = [(j - 1.5) * .034 for j in range(4)]
    xs = sorted({round(x, 12) for x in [-.075, .075] + [c + d for c in centers for d in (-.014, 0, .014)]})
    ys = [-.034, -.020, 0, .020, .034]
    zs = [0, -.025, -.040, -.055, -.085, -.105]
    lookup = {}

    def vertex(x, y, z):
        key = tuple(round(v, 12) for v in (x, y, z))
        if key not in lookup:
            lookup[key] = mesh.vertex(tuple(wrist[k] + key[k] for k in range(3)), {f'hand.{side}': 1})
        return lookup[key]

    def face(coords):
        mesh.faces.append(tuple(vertex(*p) for p in coords))

    for y in (ys[0], ys[-1]):
        for x0, x1 in zip(xs, xs[1:]):
            for z0, z1 in zip(zs, zs[1:]):
                face([(x0,y,z0),(x1,y,z0),(x1,y,z1),(x0,y,z1)])
    for x in (xs[0], xs[-1]):
        for j, (y0,y1) in enumerate(zip(ys,ys[1:])):
            for k, (z0,z1) in enumerate(zip(zs,zs[1:])):
                if x == -sign * .075 and j in (1,2) and k in (1,2):
                    continue  # Thumb aperture, not an intersecting tube.
                face([(x,y0,z0),(x,y1,z0),(x,y1,z1),(x,y0,z1)])
    for z in (zs[0], zs[-1]):
        for x0,x1 in zip(xs,xs[1:]):
            for j,(y0,y1) in enumerate(zip(ys,ys[1:])):
                if z == zs[-1] and j in (1,2) and any(abs((x0+x1)/2-c) < .014-1e-8 for c in centers):
                    continue
                face([(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)])
    tips = {}
    for name, points in digits(sign).items():
        a,b = points[:2]; tangent = [b[k]-a[k] for k in range(3)]
        norm = math.sqrt(sum(v*v for v in tangent)); tangent = [v/norm for v in tangent]
        axis = [0,1,0]; dot = sum(a*b for a,b in zip(axis,tangent))
        axis = [axis[k]-dot*tangent[k] for k in range(3)]
        norm = math.sqrt(sum(v*v for v in axis)); axis = [v/norm for v in axis]
        cross = [tangent[1]*axis[2]-tangent[2]*axis[1],tangent[2]*axis[0]-tangent[0]*axis[2],tangent[0]*axis[1]-tangent[1]*axis[0]]
        if name == 'thumb':
            hole = [(wrist[0]-sign*.075,wrist[1]+y,wrist[2]+z) for y,z in
                    [(-.02,-.055),(0,-.055),(.02,-.055),(.02,-.04),(.02,-.025),(0,-.025),(-.02,-.025),(-.02,-.04)]]
        else:
            cx = points[0][0]-wrist[0]
            hole = [(wrist[0]+cx+x,wrist[1]+y,wrist[2]-.105) for x,y in
                    [(-.014,-.02),(0,-.02),(.014,-.02),(.014,0),(.014,.02),(0,.02),(-.014,.02),(-.014,0)]]
        center = [sum(p[k] for p in hole)/8 for k in range(3)]
        hole.sort(key=lambda p: math.atan2(sum((p[k]-center[k])*cross[k] for k in range(3)),
                                           sum((p[k]-center[k])*axis[k] for k in range(3))))
        angles = [math.atan2(sum((p[k]-center[k])*cross[k] for k in range(3)),
                            sum((p[k]-center[k])*axis[k] for k in range(3))) for p in hole]
        previous = [vertex(*(p[k]-wrist[k] for k in range(3))) for p in hole]
        for i in range(1,25):
            t = i/24; segment = 0 if t < .4 else (1 if t < .75 else 2)
            low,high = (0,.4,.75)[segment],(.4,.75,1)[segment]
            u = (t-low)/(high-low); a,b = points[segment:segment+2]
            center = [a[k]+(b[k]-a[k])*u for k in range(3)]
            if t < .30: weights = {f'{name}.01.{side}':1}
            elif t < .50:
                w = smooth((t-.30)/.20); weights = {f'{name}.01.{side}':1-w,f'{name}.02.{side}':w}
            elif t < .65: weights = {f'{name}.02.{side}':1}
            elif t < .85:
                w = smooth((t-.65)/.20); weights = {f'{name}.02.{side}':1-w,f'{name}.03.{side}':w}
            else: weights = {f'{name}.03.{side}':1}
            if t < .16:
                w = smooth(t/.16)
                weights = {k:v*w for k,v in weights.items()}; weights[f'hand.{side}'] = 1-w
            radius = (.018 if name == 'thumb' else (.012 if name == 'pinky' else .0145))*(1-.30*t)
            if t > .9: radius *= 1-.7*(t-.9)/.1
            ring = [mesh.vertex([center[k]+radius*(axis[k]*math.cos(a)+cross[k]*math.sin(a)) for k in range(3)],weights) for a in angles]
            mesh.bridge(previous,ring); previous = ring
        mesh.cap(previous); tips[name] = previous
    return (subdivide(mesh) if refine else mesh), tips


def shoulders():
    """Same sewn surface as r2; locally fair the seam and soften weight transitions."""
    mesh = sweater()
    # C1 Hermite centerline: the r2 piecewise tangent kink made inner-elbow
    # rings nearly coincide even at rest. Fix geometry, not the strain limit.
    for side, sign in [('R',1),('L',-1)]:
        ids=[i for i,w in enumerate(mesh.weights) if any(b.endswith('.'+side) for b in w)]
        count=len(ids)//18
        p0=(sign*.40,0,1.79);p1=(sign*.67,-.015,1.47);p2=(sign*.75,.02,1.11)
        joint=tuple((p2[k]-p0[k])/2 for k in range(3))
        for row in range(18):
            t=.15+.85*row/17
            if t<=.5:
                u=t*2;a,b=p0,p1;m0=tuple(p1[k]-p0[k] for k in range(3));m1=joint
                old=(sign*(.40+.27*u),-.015*u,1.79-.32*u);dx,dz=sign*.27,-.32
            else:
                u=t*2-1;a,b=p1,p2;m0=joint;m1=tuple(p2[k]-p1[k] for k in range(3))
                old=(sign*(.67+.08*u),-.015+.035*u,1.47-.36*u);dx,dz=sign*.08,-.36
            center=tuple((2*u**3-3*u*u+1)*a[k]+(u**3-2*u*u+u)*m0[k]+(-2*u**3+3*u*u)*b[k]+(u**3-u*u)*m1[k] for k in range(3))
            tangent=tuple((6*u*u-6*u)*a[k]+(3*u*u-4*u+1)*m0[k]+(-6*u*u+6*u)*b[k]+(3*u*u-2*u)*m1[k] for k in range(3))
            # Keep the first sleeve's inner wall outside the torso aperture.
            # R2's circular section dipped back inside the chest and pinched.
            q=max(0,min(1,(t-.15)/.25));flare=1-smooth(q)
            derivative=-6*q*(1-q)/.25
            center=(center[0]+sign*.060*flare,center[1],center[2]+.030*flare)
            tangent=(tangent[0]+sign*.030*derivative,tangent[1],tangent[2]+.015*derivative)
            length=math.sqrt(sum(v*v for v in tangent));tangent=tuple(v/length for v in tangent)
            axis=(0,1,0);dot=tangent[1];axis=tuple(axis[k]-dot*tangent[k] for k in range(3))
            length=math.sqrt(sum(v*v for v in axis));axis=tuple(v/length for v in axis)
            cross=(tangent[1]*axis[2]-tangent[2]*axis[1],tangent[2]*axis[0]-tangent[0]*axis[2],tangent[0]*axis[1]-tangent[1]*axis[0])
            if cross[2]<0:cross=tuple(-v for v in cross)
            length=math.hypot(dx,dz);vx,vz=-dz/length,dx/length
            if vz<0:vx,vz=-vx,-vz
            radius=.13*(1-.28*t)
            for i in ids[row*count:(row+1)*count]:
                x,y,z=mesh.vertices[i];angle=math.atan2((x-old[0])*vx+(z-old[2])*vz,y-old[1])
                mesh.vertices[i]=tuple(center[k]+radius*(axis[k]*math.cos(angle)+cross[k]*math.sin(angle)) for k in range(3))
                helper=.80*(1-smooth(abs(t-.5)/.20))
                original=mesh.weights[i]
                mesh.weights[i]={k:v*(1-helper) for k,v in original.items()}
                mesh.weights[i][f'elbow_deform.{side}']=helper
    graph = defaultdict(set)
    for face in mesh.faces:
        for a,b in zip(face,face[1:]+face[:1]):
            graph[a].add(b); graph[b].add(a)
    mask = [smooth((abs(x)-.20)/.13)*(1-smooth((abs(x)-.53)/.16))*smooth((z-1.49)/.14)*(1-smooth((z-1.83)/.10))
            for x,y,z in mesh.vertices]
    for _ in range(4):
        for strength in (.42,-.44):
            before = mesh.vertices[:]
            mesh.vertices = [tuple(p[k]+strength*mask[i]*(sum(before[j][k] for j in graph[i])/len(graph[i])-p[k]) for k in range(3))
                             for i,p in enumerate(before)]
    for i,(x,y,z) in enumerate(mesh.vertices):
        side = 'R' if x > 0 else 'L'
        influence = smooth((z-1.47)/.19)*smooth((abs(x)-.16)/.10)
        upper = smooth((abs(x)-.18)/.44)
        clavicle = (1-upper)*.45*smooth((abs(x)-.16)/.18)
        desired = {f'upper_arm.{side}':upper,f'clavicle.{side}':clavicle,'chest':1-upper-clavicle}
        old = mesh.weights[i]
        mesh.weights[i] = {k:(1-influence)*old.get(k,0)+influence*desired.get(k,0) for k in set(old)|set(desired)}
        mesh.weights[i] = {k:v for k,v in mesh.weights[i].items() if v>0}
    return mesh
