"""Explicit brow centerline and outward-surface checks for head-form R2.

Pure geometry utilities. No bpy, images, identity fitting or quality score.
"""
import numpy as np


def cubic_curve(x,knots,values):
    """Shape-preserving C1 Hermite interpolation; no cubic overshoot at arch."""
    knots=np.asarray(knots,dtype=float);values=np.asarray(values,dtype=float)
    if len(knots)<2 or len(knots)!=len(values) or np.any(np.diff(knots)<=0):raise ValueError('Invalid curve knots')
    h=np.diff(knots);slope=np.diff(values)/h;m=np.zeros(len(knots));m[0]=slope[0];m[-1]=slope[-1]
    for i in range(1,len(knots)-1):
        if slope[i-1]*slope[i]>0:
            w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1]
            m[i]=(w1+w2)/(w1/slope[i-1]+w2/slope[i])
    x=np.clip(np.asarray(x,dtype=float),knots[0],knots[-1]);i=np.clip(np.searchsorted(knots,x)-1,0,len(knots)-2)
    t=(x-knots[i])/h[i]
    return (2*t**3-3*t**2+1)*values[i]+(t**3-2*t**2+t)*h[i]*m[i]+(-2*t**3+3*t**2)*values[i+1]+(t**3-t**2)*h[i]*m[i+1]


def triangles(polygons):
    return np.asarray([(p[0],p[j],p[j+1]) for p in polygons for j in range(1,len(p)-1)],dtype=int)


def vertex_normals(vertices,polygons):
    vertices=np.asarray(vertices,dtype=float);faces=triangles(polygons);a,b,c=vertices[faces].transpose(1,0,2)
    normals=np.zeros_like(vertices);cross=np.cross(b-a,c-a)
    for corner in range(3):np.add.at(normals,faces[:,corner],cross)
    return normals/np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-20)


def front_surface_y(points,vertices,polygons):
    """First -Y camera hit along parallel rays at input (X,Z), not inside lip.

    No extrapolation: an unsupported brow point raises rather than silently
    choosing an inner/hidden surface or floating next to the skull.
    """
    mesh=np.asarray(vertices,dtype=float)[triangles(polygons)];a,b,c=mesh.transpose(1,0,2)
    v0=b[:,[0,2]]-a[:,[0,2]];v1=c[:,[0,2]]-a[:,[0,2]]
    den=v0[:,0]*v1[:,1]-v0[:,1]*v1[:,0];valid=np.abs(den)>1e-14
    den=np.where(valid,den,1);result=[]
    for point in points:
        v2=np.asarray(point)[[0,2]]-a[:,[0,2]]
        u=(v2[:,0]*v1[:,1]-v2[:,1]*v1[:,0])/den
        v=(v0[:,0]*v2[:,1]-v0[:,1]*v2[:,0])/den
        inside=valid&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)
        if not inside.any():raise ValueError('No outward head surface below authored brow')
        ys=a[:,1]+u*(b[:,1]-a[:,1])+v*(c[:,1]-a[:,1]);result.append(float(ys[inside].min()))
    return np.asarray(result)


def author_brows(original,head_vertices,polygons,settings):
    original=np.asarray(original,dtype=float);result=original.copy();x=np.abs(original[:,0])
    inner=settings['abscissae_m'][0];ratio=(settings['target_tail_x_m']-inner)/(settings['source_tail_x_m']-inner)
    new_x=inner+(x-inner)*ratio;result[:,0]=np.sign(original[:,0])*new_x
    center_z=np.polyval(np.polyfit(x,original[:,2],3),x)
    center_y=np.polyval(np.polyfit(x,original[:,1],3),x)
    t=(new_x-inner)/(settings['target_tail_x_m']-inner)
    taper=np.minimum(1,np.minimum((t+.06)/.18,(1.06-t)/.18));taper=np.clip(taper,.2,1)
    result[:,2]=cubic_curve(new_x,settings['abscissae_m'],settings['heights_m'])+settings['transverse_scale']*taper*(original[:,2]-center_z)
    surface=front_surface_y(result,head_vertices,polygons)
    offset=np.clip(.002-.4*(original[:,1]-center_y),.0007,.0032)
    result[:,1]=surface-offset
    return result
