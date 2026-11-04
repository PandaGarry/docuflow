#!/usr/bin/env python3
"""Indexed anatomical control cage for the first primary-head rebuild.

Pure numpy; no bpy/private image input. Control points are bound to verified
original Rain vertex IDs, not a growing stack of guessed Gaussian centers.
Compact C2 interpolation reproduces authored 3D control displacements. It does
not infer a head from a photograph or establish likeness/anatomical approval.
"""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
SPEC=ROOT/'studio/authoring/mom-head-form-r1.json'
DATA=ROOT/'studio/reviews/mom-form-audit/head-edit-data.json.gz'


def kernel(distances):
    t=np.clip(1-np.asarray(distances,dtype=float),0,1)
    return t**4*(5-4*t)


class ControlCage:
    def __init__(self,centers,displacements,radius):
        self.centers=np.asarray(centers,dtype=float)
        self.displacements=np.asarray(displacements,dtype=float)
        self.radius=float(radius)
        if self.centers.ndim!=2 or self.centers.shape[1]!=3 or self.displacements.shape!=self.centers.shape:
            raise ValueError('Expected matching N x 3 control arrays')
        if not np.isfinite(self.centers).all() or not np.isfinite(self.displacements).all() or not np.isfinite(self.radius) or self.radius<=0:
            raise ValueError('Nonfinite controls or invalid radius')
        distances=np.linalg.norm(self.centers[:,None]-self.centers[None,:],axis=2)
        if np.any(distances[np.triu_indices(len(centers),1)]<1e-7):
            raise ValueError('Coincident cage constraints')
        system=kernel(distances/self.radius)
        self.condition_number=float(np.linalg.cond(system))
        if self.condition_number>1e10:raise ValueError('Ill-conditioned control cage')
        self.weights=np.linalg.solve(system,self.displacements)

    def __call__(self,points):
        points=np.asarray(points,dtype=float)
        if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Expected finite N x 3 points')
        result=points.copy()
        for start in range(0,len(points),1024):
            p=points[start:start+1024]
            result[start:start+1024]+=kernel(np.linalg.norm(p[:,None]-self.centers[None,:],axis=2)/self.radius)@self.weights
        return result

    def jacobians(self,points):
        points=np.asarray(points,dtype=float);result=[]
        for start in range(0,len(points),1024):
            delta=points[start:start+1024,None]-self.centers[None,:]
            t=np.linalg.norm(delta,axis=2)/self.radius
            gradients=-20*np.maximum(1-t,0)[:,:,None]**3*delta/self.radius**2
            result.append(np.eye(3)[None]+np.einsum('nkx,ky->nyx',gradients,self.weights))
        return np.concatenate(result)


def load_cage(spec_path=SPEC):
    spec=json.loads(Path(spec_path).read_text())
    payload=DATA.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=spec['indexed_data_sha256']:raise ValueError('Indexed source dataset changed')
    data=json.loads(gzip.decompress(payload))
    vertices=np.asarray(data['official-source']['basis_vertices'],dtype=float)
    centers=[];displacements=[]
    for entry in spec['controls']:
        p=vertices[entry['source_vertex']]
        if not np.allclose(p,entry['source_world_m'],atol=1e-8,rtol=0):raise ValueError('Control binding/index mismatch')
        centers.append(p);displacements.append(entry['target_world_m']-p)
    return spec,vertices,ControlCage(centers,displacements,spec['support_radius_m'])


def inspect_cage():
    spec,vertices,cage=load_cage();changed=cage(vertices)
    determinants=np.linalg.det(cage.jacobians(vertices))
    if determinants.min()<=0:raise ValueError(f'Cage fold at source head samples: det {determinants.min()}')
    if np.linalg.norm(changed-vertices,axis=1).max()>.04:raise ValueError('Unbounded head edit')
    return {'controls':len(spec['controls']),'condition_number':cage.condition_number,
            'min_sampled_jacobian_determinant':float(determinants.min()),
            'max_sampled_jacobian_determinant':float(determinants.max()),
            'maximum_basis_change_m':float(np.linalg.norm(changed-vertices,axis=1).max()),
            'control_interpolation_error_m':float(np.abs(cage(cage.centers)-cage.centers-cage.displacements).max()),
            'scope':'Sampled mathematical safety only, not continuous invertibility, anatomy, likeness or pose approval.'}


if __name__=='__main__':
    print(json.dumps(inspect_cage(),indent=2))
