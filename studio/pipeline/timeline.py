"""Frame-indexed linear controls for the technical probe, not an acting graph."""
from __future__ import annotations

from bisect import bisect_right

from .contracts import ContractError


def evaluate_track(track, frame):
    keys = track['keys']
    if frame <= keys[0]['frame']:
        return keys[0]['value']
    if frame >= keys[-1]['frame']:
        return keys[-1]['value']
    idx = bisect_right([k['frame'] for k in keys], frame) - 1
    left, right = keys[idx:idx + 2]
    t = (frame - left['frame']) / (right['frame'] - left['frame'])
    if isinstance(left['value'], list):
        return [a + (b - a) * t for a, b in zip(left['value'], right['value'])]
    return left['value'] + (right['value'] - left['value']) * t


def evaluate(shot, frame):
    start, end = shot['frame_range']
    if type(frame) is not int or not start <= frame < end:
        raise ContractError('frame outside shot')
    return {track['control']: evaluate_track(track, frame) for track in shot['tracks']}


def bind_controls(bpy, rig):
    """Fail before rendering if an authored object/shape is missing."""
    result = {}
    for semantic, entry in rig['bindings'].items():
        obj = bpy.data.objects.get(entry['object'])
        if obj is None:
            raise ContractError(f'missing rig object: {entry["object"]}')
        if entry['type'] == 'SHAPE_KEY':
            keys = getattr(obj.data, 'shape_keys', None)
            key = keys.key_blocks.get(entry['shape_key']) if keys else None
            if key is None:
                raise ContractError(f'missing shape key: {semantic}')
            result[semantic] = (entry['type'], key)
        elif entry['type'] == 'ARMATURE':
            if obj.type != 'ARMATURE':
                raise ContractError(f'not an armature: {semantic}')
            result[semantic] = (entry['type'], obj)
        else:
            result[semantic] = (entry['type'], obj)
    return result


def apply_controls(bindings, values):
    for semantic, value in values.items():
        if semantic not in bindings:
            raise ContractError(f'unbound control: {semantic}')
        typ, target = bindings[semantic]
        if typ == 'OBJECT_LOCATION':
            target.location = value
        elif typ == 'SHAPE_KEY':
            target.value = value
        else:
            raise ContractError(f'control is not animatable: {semantic}')
