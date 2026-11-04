"""Read evaluated geometry, not controller values, for trusted asset probes."""
from __future__ import annotations
from mathutils import Vector


def measure(objects, package, deps):
    contact_points = {}
    fingertips = {}
    for entry in [*package.get('contact_probes', []), *package.get('fingertip_probes', [])]:
        obj = objects[entry['object']].evaluated_get(deps)
        mesh = obj.to_mesh()
        try:
            points = [obj.matrix_world @ mesh.vertices[i].co for i in entry['vertex_indices']]
        finally:
            obj.to_mesh_clear()
        if 'reference_bone' in entry:
            rig = objects[entry['armature']].evaluated_get(deps)
            reference = rig.matrix_world @ rig.pose.bones[entry['reference_bone']].matrix
            fingertips[entry['id']] = list(reference.inverted() @ (sum(points, Vector()) / len(points)))
        else:
            contact_points[entry['id']] = [list(p) for p in points]
    error = max((abs(p.length / arm.data.bones[p.name].length - 1)
                 for arm in objects.values() if arm.type == 'ARMATURE'
                 for p in arm.evaluated_get(deps).pose.bones), default=0)
    return {'contact_points_world': contact_points, 'fingertips_local': fingertips,
            'bone_relative_length_error': error}
