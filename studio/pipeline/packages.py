"""V2 external, trusted-local .blend packages. V1 smoke contracts stay separate.

Hash verification is integrity, NOT trust, artistic approval or a Blender sandbox.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator
from .contracts import (ROOT, SCHEMAS, ContractError, _finite, file_hash, load_json, safe_path)


@lru_cache(maxsize=4)
def validator(kind):
    name = {'asset_package': 'asset-package', 'project': 'project', 'shot': 'shot', 'render_manifest': 'render-manifest'}.get(kind)
    if name is None:
        raise ContractError('unknown v2 document kind')
    schema = load_json(SCHEMAS / f'{name}.v2.schema.json')
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get('kind'), str):
        raise ContractError('expected v2 object document')
    _finite(doc)
    for error in validator(doc['kind']).iter_errors(doc):
        raise ContractError(f'v2 {doc["kind"]} {list(error.absolute_path)}: {error.message}')
    if doc['kind'] == 'asset_package':
        if not doc['blend']['path'].endswith('.blend'):
            raise ContractError('package must reference a .blend file')
        safe_path(ROOT, doc['blend']['path'])
        safe_path(ROOT, doc['provenance']['authoring_script'])
        for binding in doc['bindings'].values():
            if binding['type'] in {'OBJECT_LOCATION', 'OBJECT_ROTATION'} and 'target' in binding:
                raise ContractError('object transform binding cannot specify a bone/shape target')
    if doc['kind'] == 'project' and any(type(v) is not int or v % 2 for v in doc['resolution']):
        raise ContractError('even integer resolution required')
    return doc


def validate_bundle(project, package, shot, root=ROOT, verify_files=True):
    for kind, doc in [('project', project), ('asset_package', package), ('shot', shot)]:
        if not isinstance(doc, dict) or doc.get('kind') != kind:
            raise ContractError('v2 document kind mismatch')
        validate(doc)
    if (shot['project_id'] != project['project_id'] or shot['asset_id'] != package['asset_id'] or
            shot['asset_revision'] != package['revision']):
        raise ContractError('unresolved project/asset revision')
    start, end = shot['frame_range']
    if type(start) is not int or type(end) is not int or not 0 <= start < end or end-start > 960:
        raise ContractError('invalid half-open frame range or preview exceeds 960 frames')
    used = set()
    for track in shot['tracks']:
        name = track['control']
        if name in used or name not in package['bindings']:
            raise ContractError(f'duplicate or unknown control: {name}')
        used.add(name)
        binding = package['bindings'][name]
        prev = start - 1
        for key in track['keys']:
            f, value = key['frame'], key['value']
            if type(f) is not int or not start <= f < end or f <= prev:
                raise ContractError('unordered/out-of-shot frame key')
            prev = f
            if binding['type'] == 'SHAPE_KEY':
                if type(value) not in (int, float) or not 0 <= value <= 1:
                    raise ContractError('shape control needs scalar in [0,1]')
            elif not isinstance(value, list):
                raise ContractError('transform control needs vec3')
        if track['keys'][0]['frame'] != start or track['keys'][-1]['frame'] != end-1:
            raise ContractError('tracks must cover first and last frame')
    contact_ids={p['id'] for p in package.get('contact_probes',[])}
    finger_ids={p['id'] for p in package.get('fingertip_probes',[])}
    for key in ('contact_probes','fingertip_probes'):
        ids=[p['id'] for p in package.get(key,[])]
        if len(ids)!=len(set(ids)):raise ContractError('duplicate geometry probe ID')
    seen=set()
    for contact in shot.get('contacts',[]):
        a,b=contact['frame_range'];name=contact['probe']
        if name not in contact_ids or type(a) is not int or type(b) is not int or not start<=a<b<=end:
            raise ContractError('invalid contact interval or probe')
        for frame in range(a,b):
            if (name,frame) in seen:raise ContractError('overlapping stance intervals')
            seen.add((name,frame))
    if any(c['probe'] not in finger_ids for c in shot.get('finger_checks',[])):
        raise ContractError('unknown finger geometry probe')
    if verify_files:
        dependencies=[(d['path'],d['sha256']) for d in package['provenance'].get('dependencies',[])]
        for path, expected in [(package['blend']['path'], package['blend']['sha256']),
                               (package['provenance']['authoring_script'], package['provenance']['script_sha256']), *dependencies]:
            file = safe_path(root, path)
            if not file.is_file() or file_hash(file) != expected:
                raise ContractError(f'package file missing or hash changed: {path}')
    return project, package, shot


def append_package(bpy, package, root=ROOT):
    """Append only the declared collection; no source scene/settings fallback."""
    path = safe_path(root, package['blend']['path'])
    if file_hash(path) != package['blend']['sha256']:
        raise ContractError('blend changed before import')
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    name = package['blend']['collection']
    before = set(bpy.data.objects.keys())
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        if name not in source.collections:
            raise ContractError(f'package collection absent: {name}')
        target.collections = [name]
    collection = target.collections[0]
    if collection is None:
        raise ContractError('collection import failed')
    bpy.context.scene.collection.children.link(collection)
    objects = {o.name: o for o in collection.all_objects}
    if before.intersection(objects):
        raise ContractError('package object namespace collision')
    # Disable all author scripts/drivers; only explicit numeric controls are supported.
    for obj in objects.values():
        if obj.type not in {'MESH', 'ARMATURE', 'EMPTY'}:
            raise ContractError(f'unsupported package object type: {obj.type}')
        if any(m.type not in {'ARMATURE', 'BEVEL', 'SUBSURF', 'WEIGHTED_NORMAL'} for m in obj.modifiers):
            raise ContractError('unsupported modifier in self-contained package')
        for owner in (obj, obj.data, getattr(obj.data, 'shape_keys', None)):
            animation = getattr(owner, 'animation_data', None)
            if animation and animation.drivers:
                raise ContractError(f'unsupported driver in package: {obj.name}')
        if obj.library is not None:
            raise ContractError('linked library is not a self-contained package')
    for image in bpy.data.images:
        if image.source not in {'GENERATED', 'VIEWER'} and not image.packed_file:
            raise ContractError('unpacked external image in package')
    return objects


def bind(objects, package):
    result = {}
    for name, b in package['bindings'].items():
        obj = objects.get(b['object'])
        if obj is None:
            raise ContractError(f'missing package object: {b["object"]}')
        typ = b['type']
        if typ == 'SHAPE_KEY':
            keys = getattr(obj.data, 'shape_keys', None)
            target = keys.key_blocks.get(b['target']) if keys else None
            if target is None:
                raise ContractError(f'missing package shape: {name}')
        elif typ == 'POSE_ROTATION':
            target = obj.pose.bones.get(b['target']) if obj.type == 'ARMATURE' else None
            if target is None:
                raise ContractError(f'missing package pose bone: {name}')
            target.rotation_mode = 'XYZ'
        else:
            target = obj
            if typ == 'OBJECT_ROTATION':
                target.rotation_mode = 'XYZ'
        result[name] = (typ, target)
    for check in package['ik_checks']:
        arm, target = objects.get(check['armature']), objects.get(check['target'])
        if arm is None or arm.type != 'ARMATURE' or check['bone'] not in arm.pose.bones or target is None:
            raise ContractError('invalid package IK measurement binding')
    for entry in [*package.get('contact_probes',[]),*package.get('fingertip_probes',[])]:
        obj=objects.get(entry['object'])
        if obj is None or obj.type!='MESH' or max(entry['vertex_indices'])>=len(obj.data.vertices):
            raise ContractError('missing/out-of-range geometry probe')
        if any(m.type not in {'ARMATURE','WEIGHTED_NORMAL'} for m in obj.modifiers):
            raise ContractError('geometry probes require topology-preserving modifiers')
        if 'reference_bone' in entry:
            arm=objects.get(entry['armature'])
            if arm is None or arm.type!='ARMATURE' or entry['reference_bone'] not in arm.pose.bones:
                raise ContractError('missing finger reference bone')
    return result


def apply(bindings, values):
    for name, value in values.items():
        if name not in bindings:
            raise ContractError(f'unbound package control: {name}')
        typ, target = bindings[name]
        if typ == 'SHAPE_KEY':
            target.value = value
        elif typ == 'OBJECT_LOCATION':
            target.location = value
        elif typ in ('OBJECT_ROTATION', 'POSE_ROTATION'):
            target.rotation_euler = value
        else:
            raise ContractError('unsupported binding type')
