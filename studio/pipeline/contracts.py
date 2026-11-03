"""Versioned contracts for the first *technical smoke* pipeline slice.

Not yet a general character/episode schema. Production assets are intentionally
rejected rather than silently rendered as the synthetic probe.
"""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / 'studio/schemas'
KINDS = {'project', 'asset', 'rig', 'shot', 'speech', 'manifest', 'quality_report'}


class ContractError(ValueError):
    pass


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ContractError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_json(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ContractError(f'configuration too large: {path.name}')
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f'nonfinite JSON: {x}')))
    except (ValueError, UnicodeError) as exc:
        raise ContractError(f'{path.name}: {exc}') from exc


def canonical_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def safe_path(root, value):
    if (not isinstance(value, str) or not value or '\\' in value or '\0' in value or ':' in value
            or Path(value).is_absolute() or '..' in Path(value).parts):
        raise ContractError(f'unsafe relative path: {value!r}')
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ContractError('path escapes project root')
    return path


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError('nonfinite numeric value')
    if isinstance(value, dict):
        for x in value.values():
            _finite(x)
    if isinstance(value, list):
        for x in value:
            _finite(x)


@lru_cache(maxsize=7)
def validator(kind):
    name = 'report' if kind == 'quality_report' else kind
    schema = load_json(SCHEMAS / f'{name}.schema.json')
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_document(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get('kind'), str) or doc['kind'] not in KINDS:
        raise ContractError('unknown document kind')
    _finite(doc)
    for error in validator(doc['kind']).iter_errors(doc):
        path = '.'.join(str(x) for x in error.absolute_path) or '<root>'
        raise ContractError(f'{doc["kind"]}.{path}: {error.message}')
    if doc['kind'] == 'project':
        if any(type(v) is not int or v % 2 for v in doc['resolution']):
            raise ContractError('resolution must be even integer pixels')
    if doc['kind'] == 'speech':
        safe_path(ROOT, doc['audio_path'])
        last_end = 0
        for phone in doc['phones']:
            start, end = phone['start_sample'], phone['end_sample']
            if not 0 <= last_end <= start < end <= doc['sample_count']:
                raise ContractError('phone spans overlap, reverse, or exceed audio')
            last_end = end
    if doc['kind'] == 'manifest':
        for artifact in doc['artifacts']:
            safe_path(ROOT, artifact['path'])
    if doc['kind'] in ('shot', 'manifest'):
        start, end = doc['frame_range']
        if type(start) is not int or type(end) is not int or start >= end:
            raise ContractError('invalid half-open integer frame range')
    return doc


def validate_bundle(bundle):
    if set(bundle) != {'project', 'asset', 'rig', 'shot'}:
        raise ContractError('smoke bundle must contain project, asset, rig and shot')
    for key, doc in bundle.items():
        if not isinstance(doc, dict) or doc.get('kind') != key:
            raise ContractError('bundle/document kind mismatch')
        validate_document(doc)
    p, a, r, s = (bundle[k] for k in ('project', 'asset', 'rig', 'shot'))
    if (s['project_id'] != p['project_id'] or s['asset_id'] != a['asset_id'] or
            s['rig_id'] != r['rig_id'] or r['asset_id'] != a['asset_id']):
        raise ContractError('unresolved project/asset/rig reference')
    start, end = s['frame_range']
    if end - start > 240:
        raise ContractError('smoke workload limited to 240 frames')
    controls = set()
    for track in s['tracks']:
        control = track['control']
        if control in controls:
            raise ContractError('duplicate control track')
        controls.add(control)
        if control not in r['bindings']:
            raise ContractError(f'unknown control: {control}')
        typ = r['bindings'][control]['type']
        if typ == 'ARMATURE':
            raise ContractError('armature binding is not a numeric track')
        last = start - 1
        for key in track['keys']:
            f, value = key['frame'], key['value']
            if type(f) is not int or not start <= f < end or f <= last:
                raise ContractError('track keys must be ordered integer frames inside shot')
            if typ == 'OBJECT_LOCATION' and not isinstance(value, list):
                raise ContractError('location control needs vec3')
            if typ == 'SHAPE_KEY' and (isinstance(value, list) or not 0 <= value <= 1):
                raise ContractError('shape key control needs scalar in [0,1]')
            last = f
        if track['keys'][0]['frame'] != start or track['keys'][-1]['frame'] != end - 1:
            raise ContractError('smoke tracks must explicitly cover first and last frame')
    if not {'arm.R.ik_target', 'jaw.open'} <= controls:
        raise ContractError('smoke shot must exercise IK target and shape key')
    return bundle


def load_bundle(directory):
    root = Path(directory)
    return validate_bundle({k: load_json(root / f'{k}.json') for k in ('project', 'asset', 'rig', 'shot')})


def frame_time(frame, fps):
    return Fraction(frame * fps['den'], fps['num'])


def frame_to_sample(frame, fps, sample_rate=48000):
    if frame < 0:
        raise ContractError('negative frame')
    value = frame_time(frame, fps) * sample_rate
    return (value.numerator * 2 + value.denominator) // (2 * value.denominator)
