"""R4 authored forms for native still review, not a production facial rig.

R1–R3 remain unchanged. All dimensions are RH Z-up metres before head scaling.
"""
from __future__ import annotations
import math
from .mesh import Mesh, smooth
from .refined_body import hand as hand_r3, subdivide, digits

SKIN = (.64, .355, .225)
HAIR = (.065, .030, .018)
HEAD_SCALE = (.84, .88, .78)
HEAD_PIVOT_Z = 1.94
PROFILE = [(1.95,.07,.10,.015),(1.99,.19,.16,.008),(2.05,.255,.205,0),
           (2.14,.292,.24,-.006),(2.26,.320,.26,-.009),(2.38,.318,.254,-.008),
           (2.49,.305,.244,-.014),(2.60,.245,.218,-.022),
           (2.67,.125,.12,-.028),(2.705,.025,.035,-.034)]


def gauss(x, z, cx, cz, rx, rz):
    return math.exp(-((x-cx)/rx)**2-((z-cz)/rz)**2)


def profile(z):
    # Monotone cubic Hermite radii: smoothstep per section produced terraces.
    def slope(i,k):
        if i==0:return (PROFILE[1][k]-PROFILE[0][k])/(PROFILE[1][0]-PROFILE[0][0])
        if i==len(PROFILE)-1:return (PROFILE[i][k]-PROFILE[i-1][k])/(PROFILE[i][0]-PROFILE[i-1][0])
        left=(PROFILE[i][k]-PROFILE[i-1][k])/(PROFILE[i][0]-PROFILE[i-1][0])
        right=(PROFILE[i+1][k]-PROFILE[i][k])/(PROFILE[i+1][0]-PROFILE[i][0])
        return 2*left*right/(left+right) if left*right>0 else 0
    for i,(a,b) in enumerate(zip(PROFILE,PROFILE[1:])):
        if a[0] <= z <= b[0]:
            span=b[0]-a[0];t=(z-a[0])/span
            return tuple((2*t**3-3*t*t+1)*a[k]+(t**3-2*t*t+t)*span*slope(i,k)
                         +(-2*t**3+3*t*t)*b[k]+(t**3-t*t)*span*slope(i+1,k) for k in (1,2,3))
    return tuple(PROFILE[0 if z<PROFILE[0][0] else -1][k] for k in (1,2,3))


def sculpt(x,z):
    cheeks=sum(.030*gauss(x,z,s*.18,2.31,.105,.105) for s in (-1,1))
    sockets=sum(.012*gauss(x,z,s*.135,2.405,.085,.066) for s in (-1,1))
    orbital=sum(.045*gauss(x,z,s*.18,2.405,.10,.08) for s in (-1,1))
    brows=sum(.015*gauss(x,z,s*.135,2.49,.12,.038) for s in (-1,1))
    nose=.035*gauss(x,z,0,2.37,.044,.095)+.082*gauss(x,z,0,2.28,.063,.052)
    nose+=sum(.022*gauss(x,z,s*.050,2.26,.025,.024) for s in (-1,1))
    muzzle=.023*gauss(x,z,0,2.16,.14,.066)
    return cheeks+orbital-sockets+brows+nose+muzzle


def front(x,z):
    rx,ry,cy=profile(z)
    f=math.sqrt(max(0,1-(x/rx)**2))
    return cy+ry*f+sculpt(x,z)*f*f


def head_point(point):
    x,y,z=point
    return x*HEAD_SCALE[0],y*HEAD_SCALE[1],HEAD_PIVOT_Z+(z-HEAD_PIVOT_Z)*HEAD_SCALE[2]


def scale_head(mesh):
    mesh.vertices=[head_point(p) for p in mesh.vertices]
    return mesh


def head():
    mesh=Mesh();colors=[];masks=[];previous=None
    for i in range(85):
        z=PROFILE[0][0]+(PROFILE[-1][0]-PROFILE[0][0])*i/84
        rx,ry,cy=profile(z);ring=[]
        for j in range(192):
            phi=2*math.pi*j/192;x=rx*math.cos(phi);f=max(0,math.sin(phi))
            y=cy+ry*math.sin(phi)+sculpt(x,z)*f*f
            line=2.105+.19*smooth((abs(x)-.065)/.16)
            # Sideburns rise towards the ear; the rear nape is not a beard bowl.
            side=(1-f)**3
            line=line*(1-side)+(2.43 if math.sin(phi)>-.12 else 2.04)*side
            mask=smooth((line-z)/.012)
            if math.sin(phi)<-.20:mask*=smooth((2.12-z)/.07)
            y+=.003*mask*f
            rose=min(.16,sum(.12*gauss(x,z,s*.18,2.31,.10,.085) for s in (-1,1)))
            skin=tuple((1-rose)*c+rose*r for c,r in zip(SKIN,(.65,.24,.18)))
            color=tuple((1-mask)*c+mask*h for c,h in zip(skin,HAIR))
            ring.append(mesh.vertex((x,y,z),{'head':1}));colors.append(color);masks.append(mask)
        if previous:mesh.bridge(previous,ring)
        else:mesh.cap(ring)
        previous=ring
    mesh.cap(previous)
    return scale_head(mesh),colors,masks


def hair_surface(phi,theta):
    limit=1.18-.39*math.sin(phi)
    front_weight=.65+.35*math.sin(phi)
    puff=.16*math.exp(-((theta-.40)/.38)**2)*front_weight*smooth((limit-theta)/.18)
    puff*=1+.12*math.cos(5*phi+1.4*theta)
    sweep=puff/.16
    ridge=.0025*math.sin(15*phi+4.8*theta)*math.sin(theta)**.7
    base_z=min(PROFILE[-1][0],2.29+.420*math.cos(theta))
    rx,ry,cy=profile(base_z)
    x=(rx+.006+ridge+.095*sweep)*math.cos(phi)+.024*sweep
    y=cy+(ry+.006+ridge+.040*sweep)*math.sin(phi)-.026*sweep
    y+=sculpt(x,base_z)*max(0,math.sin(phi))**2
    return x,y,base_z+.005+puff+ridge*math.cos(theta)


def hair():
    mesh=Mesh();previous=None
    for i in range(42):
        ring=[]
        for j in range(160):
            phi=2*math.pi*j/160;limit=1.18-.39*math.sin(phi)
            theta=.012+(limit-.012)*i/41
            ring.append(mesh.vertex(hair_surface(phi,theta),{'head':1}))
        if previous:mesh.bridge(previous,ring)
        else:mesh.cap(ring)
        previous=ring
    mesh.cap(previous)
    return scale_head(mesh)


def hair_fibers():
    mesh=Mesh();colors=[]
    for i in range(480):
        phi0=2*math.pi*i/480;start=1.18-.39*math.sin(phi0)
        end=.06+.18*(.5+.5*math.sin(i*2.399963))
        shade=.72+.38*(.5+.5*math.sin(i*4.456))
        previous=None
        for j in range(33):
            t=j/32;phi=phi0+.36*math.sin(math.pi*t)
            theta=min((1-t)*start+t*end,(1.18-.39*math.sin(phi))*.998)
            x,y,z=hair_surface(phi,theta);normal_offset=.0006
            width=.00065*math.sin(math.pi*(.02+.96*t))**.5
            pair=[]
            for side in (-1,1):
                pair.append(mesh.vertex((x+normal_offset*math.cos(phi)-side*width*math.sin(phi),
                                          y+normal_offset*math.sin(phi)+side*width*math.cos(phi),z+.00035),{'head':1}))
                colors.append(tuple(c*shade for c in HAIR))
            if previous:mesh.faces.append((previous[0],previous[1],pair[1],pair[0]))
            previous=pair
    return scale_head(mesh),colors


def ear(sign):
    mesh=Mesh();colors=[];rings=[]
    # Front concha/helix is a concave disk, not a second sphere laid on top.
    for back in (False,True):
        previous=None
        for i in range(19):
            r=.015+.985*i/18
            if back and i==18:
                ring=rings[-1]
            else:
                ring=[]
                for j in range(64):
                    theta=2*math.pi*j/64
                    x=sign*(.337+.055*r*math.cos(theta));z=2.33+.103*r*math.sin(theta)
                    y=(.018+.030*math.exp(-((r-.78)/.16)**2)-.018*r**3) if not back else -.027*math.sqrt(max(0,1-r*r))
                    ring.append(mesh.vertex((x,y,z),{'head':1}))
                    tint=.22*(1-r) if not back else 0
                    colors.append(tuple((1-tint)*c+tint*q for c,q in zip(SKIN,(.55,.20,.14))))
            if previous:mesh.bridge(previous,ring)
            else:mesh.cap(ring)
            previous=ring
            if not back:rings.append(ring)
    return scale_head(mesh),colors


def eye_white(cx):
    mesh=Mesh();previous=None
    for i in range(19):
        r=.006+.994*i/18
        ring=[]
        for j in range(96):
            a=2*math.pi*j/96;dx=.080*r*math.cos(a);dz=(.046 if math.sin(a)>0 else .055)*r*math.sin(a)
            y=eye_y(cx,cx+dx,2.405+dz+.035*dx)
            ring.append(mesh.vertex((cx+dx,y,2.405+dz+.035*dx),{'head':1}))
        if previous:mesh.bridge(previous,ring)
        else:mesh.cap(ring)
        previous=ring
    return scale_head(mesh)


def lids(cx):
    mesh=Mesh();previous=None;colors=[]
    for i in range(9):
        t=i/8;ring=[]
        for j in range(96):
            a=2*math.pi*j/96;x=cx+(.080+.023*t)*math.cos(a)
            z=2.405+((.046 if math.sin(a)>0 else .055)+.026*t)*math.sin(a)+.035*(x-cx)
            y=(1-t)*eye_y(cx,x,z)+t*(front(x,z)-.0005)+.0025*math.sin(math.pi*t)
            ring.append(mesh.vertex((x,y,z),{'head':1}))
            warmth=.15*(1-t)
            colors.append(tuple((1-warmth)*c+warmth*v for c,v in zip(SKIN,(.55,.25,.18))))
        if previous:mesh.bridge(previous,ring)
        previous=ring
    return scale_head(mesh),colors


def eye_y(cx,x,z):
    dx=x-cx;dz=z-2.405-.035*dx
    rz=.046 if dz>0 else .055
    return .246-.15*(1 if cx>0 else -1)*dx+.0215*max(0,1-(dx/.080)**2-(dz/rz)**2)


def iris(cx):
    mesh=Mesh();colors=[];previous=None;center=cx+.006
    for i in range(13):
        r=.0225+(.052-.0225)*i/12;ring=[]
        for j in range(128):
            a=2*math.pi*j/128;x=center+r*math.cos(a);z=2.405+.82*r*math.sin(a)
            ring.append(mesh.vertex((x,eye_y(cx,x,z)+.0007,z),{'head':1}))
            strands=.85+.14*math.sin(61*a+8*r/.052)+.10*math.sin(113*a-6*r/.052)
            limbus=1-.65*smooth((r/.052-.84)/.16)
            colors.append(tuple(c*strands*limbus for c in (.155,.070,.027)))
        if previous:mesh.bridge(previous,ring)
        previous=ring
    return scale_head(mesh),colors


def pupil(cx):
    mesh=Mesh();previous=None;center=cx+.006
    for i in range(8):
        r=.0002+.0225*i/7;ring=[]
        for j in range(96):
            a=2*math.pi*j/96;x=center+r*math.cos(a);z=2.405+.92*r*math.sin(a)
            ring.append(mesh.vertex((x,eye_y(cx,x,z)+.0009,z),{'head':1}))
        if previous:mesh.bridge(previous,ring)
        else:mesh.cap(ring)
        previous=ring
    return scale_head(mesh)


def ribbon(points, radius_z, radius_y):
    """Smooth small facial tube following the actual head surface."""
    mesh=Mesh();previous=None
    for i,(x,z) in enumerate(points):
        t=i/(len(points)-1);taper=.16+.84*math.sin(math.pi*t)**.45
        y=front(x,z)+.003
        ring=[mesh.vertex((x,y+radius_y*taper*math.cos(2*math.pi*j/16),z+radius_z*taper*math.sin(2*math.pi*j/16)),{'head':1}) for j in range(16)]
        if previous:mesh.bridge(previous,ring)
        else:mesh.cap(ring)
        previous=ring
    mesh.cap(previous)
    return scale_head(mesh)


def eyebrow(sign):
    return ribbon([(sign*(.045+.18*t),2.500+.023*math.sin(math.pi*t)-.007*t) for t in [i/32 for i in range(33)]],.019,.008)


def moustache(sign):
    return ribbon([(sign*(.005+.128*t),2.204-.025*t+.005*math.sin(math.pi*t)) for t in [i/36 for i in range(37)]],.016,.009)


def mouth_line():
    return ribbon([(.112*t,2.153+.015*abs(t)**1.7) for t in [-1+2*i/64 for i in range(65)]],.0028,.003)


def lower_lip():
    return ribbon([(.098*t,2.143+.014*abs(t)**1.7) for t in [-1+2*i/48 for i in range(49)]],.0048,.005)


def hand(sign):
    """Tapered wrist extension + convex thenar/hypothenar forms, same sewn cage."""
    mesh,tips=hand_r3(sign,refine=False);wrist=(sign*.75,.02,1.11)
    for i,(x,y,z) in enumerate(mesh.vertices):
        local=(x-wrist[0],y-wrist[1],z-wrist[2]);px,py,pz=local
        side='R' if sign>0 else 'L'
        names=[n for n in ('index','middle','ring','pinky') if any(k.startswith(n+'.') for k in mesh.weights[i])]
        if names:
            n=names[0];points=digits(sign)[n];length=points[0][2]-points[-1][2]
            t=max(0,min(1,(points[0][2]-z)/length));cx=points[0][0];cy=points[0][1]+.006*t
            factor=(1.20 if n=='pinky' else 1.15)*(1+.10*math.exp(-((t-.4)/.10)**2)+.07*math.exp(-((t-.75)/.09)**2))
            x=cx+(x-cx)*factor;y=cy+(y-cy)*factor
            px,py=x-wrist[0],y-wrist[1]
            mesh.vertices[i]=(x,y,z)
        if any(k.startswith('thumb.') for k in mesh.weights[i]):
            points=digits(sign)['thumb'];a,b=points[0],points[-1]
            axis=tuple(b[k]-a[k] for k in range(3));norm=sum(v*v for v in axis)
            t=max(0,min(1,sum((q-a[k])*axis[k] for k,q in enumerate((x,y,z)))/norm))
            center=tuple(a[k]+t*axis[k] for k in range(3))
            x,y,z=tuple(center[k]+1.20*(q-center[k]) for k,q in enumerate((x,y,z)))
            px,py,pz=x-wrist[0],y-wrist[1],z-wrist[2]
            mesh.vertices[i]=(x,y,z)
        palm=mesh.weights[i].get(f'hand.{side}',0)
        if palm<=0:continue
        u=max(0,min(1,-pz/.105))
        width=.63+.37*smooth(u/.65)
        px=px*(1-palm+palm*width)
        bulge=math.sin(math.pi*u)*(1-min(1,(px/.075)**2))
        thenar=math.exp(-((px+sign*.038)/.032)**2-((pz+.045)/.038)**2)
        hypothenar=math.exp(-((px-sign*.047)/.025)**2-((pz+.068)/.04)**2)
        if py>=0:py+=palm*(.003*bulge+.014*thenar+.007*hypothenar)
        else:py-=palm*.009*bulge
        # Extend skin inside the tilted cuff instead of leaving a wrist gap.
        extension=.033*(1-smooth(u/.24))*palm
        pz+=extension
        mesh.vertices[i]=(wrist[0]+px,wrist[1]+py,wrist[2]+pz)
        if u==0:mesh.weights[i]={f'forearm.{"R" if sign>0 else "L"}':1}
    return subdivide(subdivide(mesh)),tips


def beard_fibers():
    mesh=Mesh();colors=[]
    for i in range(45*13):
        phi0=math.pi*((i%45)+.5)/45;z0=1.985+.355*((i//45)+.5)/13
        rx,ry,cy=profile(z0);x=rx*math.cos(phi0);f=math.sin(phi0)
        line=2.105+.19*smooth((abs(x)-.065)/.16)
        line=line*(1-(1-f)**3)+2.43*(1-f)**3
        if z0>line-.003:continue
        previous=None;shade=.72+.34*(.5+.5*math.sin(i*2.399963))
        length=.016+.014*(.5+.5*math.sin(i*1.773))
        for j in range(9):
            t=j/8;z=z0-length*t;phi=phi0+.018*t*math.cos(phi0)
            rx,ry,cy=profile(z);x=rx*math.cos(phi);f=math.sin(phi)
            y=cy+ry*f+sculpt(x,z)*f*f+.003*f
            width=.00065*(.25+.75*math.sin(math.pi*t))
            pair=[]
            for side in (-1,1):
                pair.append(mesh.vertex((x+.0007*math.cos(phi)-side*width*math.sin(phi),
                                         y+.0007*f+side*width*math.cos(phi),z),{'head':1}))
                colors.append(tuple(c*shade for c in HAIR))
            if previous:mesh.faces.append((previous[0],previous[1],pair[1],pair[0]))
            previous=pair
    return scale_head(mesh),colors
