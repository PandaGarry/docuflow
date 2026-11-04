"""Contracts/integrity/error-path tests. These do NOT render or judge character art.

Actual Blender/FFmpeg integration evidence is recorded separately by run_probe.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from studio.pipeline import contracts as c
from studio.pipeline import run_probe as runner
from studio.pipeline.timeline import apply_controls, bind_controls, evaluate, evaluate_track
from studio.tools.prepare_blender_native import prepare


class Contracts(unittest.TestCase):
    def setUp(self):
        self.bundle = copy.deepcopy(c.load_bundle(c.ROOT / 'studio/production/smoke'))

    def rejects(self):
        with self.assertRaises(c.ContractError):
            c.validate_bundle(self.bundle)

    def test_live_smoke_bundle(self):
        self.assertEqual(c.validate_bundle(self.bundle)['shot']['frame_range'], [0, 24])

    def test_all_seven_schemas_are_valid(self):
        self.assertEqual(len(c.KINDS), 7)
        for kind in c.KINDS:
            c.validator(kind)

    def test_unknown_kind(self):
        for value in [None, [], {}, {'kind': 'episode'}, {'kind': []}]:
            with self.subTest(value=value), self.assertRaises(c.ContractError):
                c.validate_document(value)

    def test_unknown_version_rejected_not_migrated_silently(self):
        self.bundle['project']['schema_version'] = 2
        self.rejects()

    def test_boolean_not_integer_version(self):
        self.bundle['project']['schema_version'] = True
        self.rejects()

    def test_unknown_fields_rejected(self):
        self.bundle['project']['hidden_legacy_axis'] = 'Y'
        self.rejects()

    def test_zero_fps(self):
        self.bundle['project']['fps']['num'] = 0
        self.rejects()

    def test_zero_denominator(self):
        self.bundle['project']['fps']['den'] = 0
        self.rejects()

    def test_odd_resolution(self):
        self.bundle['project']['resolution'][0] = 1919
        self.rejects()

    def test_boolean_resolution(self):
        self.bundle['project']['resolution'][0] = True
        self.rejects()

    def test_legacy_axis_rejected(self):
        self.bundle['project']['coordinate_system'] = 'RH_Y_UP_METERS'
        self.rejects()

    def test_wrong_forward_axis(self):
        self.bundle['project']['forward_axis'] = '-Y'
        self.rejects()

    def test_smoke_cannot_be_approved_character_asset(self):
        self.bundle['asset']['approved_for_character_production'] = True
        self.rejects()

    def test_cross_references(self):
        for kind, field in [('shot', 'rig_id'), ('shot', 'asset_id'), ('shot', 'project_id'), ('rig', 'asset_id')]:
            with self.subTest(kind=kind, field=field):
                other = copy.deepcopy(self.bundle)
                other[kind][field] = 'not-in-bundle'
                with self.assertRaises(c.ContractError):
                    c.validate_bundle(other)

    def test_missing_bundle_member(self):
        del self.bundle['rig']
        self.rejects()

    def test_wrong_bundle_document_type(self):
        self.bundle['asset'] = []
        self.rejects()

    def test_reversed_frame_range(self):
        self.bundle['shot']['frame_range'] = [24, 0]
        self.rejects()

    def test_smoke_workload_cap(self):
        self.bundle['shot']['frame_range'] = [0, 241]
        self.rejects()

    def test_duplicate_tracks(self):
        self.bundle['shot']['tracks'].append(copy.deepcopy(self.bundle['shot']['tracks'][0]))
        self.rejects()

    def test_unknown_control(self):
        self.bundle['shot']['tracks'][0]['control'] = 'not.bound'
        self.rejects()

    def test_missing_required_smoke_track(self):
        self.bundle['shot']['tracks'].pop()
        self.rejects()

    def test_armature_is_not_scalar_track(self):
        self.bundle['shot']['tracks'][0]['control'] = 'body.armature'
        self.rejects()

    def test_location_requires_vec3(self):
        self.bundle['shot']['tracks'][0]['keys'][0]['value'] = .5
        self.rejects()

    def test_location_vector_size(self):
        self.bundle['shot']['tracks'][0]['keys'][0]['value'] = [1, 2]
        self.rejects()

    def test_shape_range(self):
        self.bundle['shot']['tracks'][1]['keys'][1]['value'] = 1.01
        self.rejects()

    def test_shape_not_vector(self):
        self.bundle['shot']['tracks'][1]['keys'][1]['value'] = [0, 0, 0]
        self.rejects()

    def test_key_at_half_open_end_is_invalid(self):
        self.bundle['shot']['tracks'][0]['keys'][-1]['frame'] = 24
        self.rejects()

    def test_duplicate_key_frames(self):
        self.bundle['shot']['tracks'][0]['keys'][1]['frame'] = 0
        self.rejects()

    def test_fractional_key_frame(self):
        self.bundle['shot']['tracks'][0]['keys'][1]['frame'] = 6.5
        self.rejects()

    def test_missing_first_key(self):
        self.bundle['shot']['tracks'][0]['keys'].pop(0)
        self.rejects()

    def test_missing_last_key(self):
        self.bundle['shot']['tracks'][0]['keys'].pop()
        self.rejects()

    def test_nonfinite_python_values(self):
        for value in [math.nan, math.inf, -math.inf]:
            self.bundle['shot']['tracks'][1]['keys'][1]['value'] = value
            self.rejects()

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            path.write_text('{"kind":"project","kind":"asset"}')
            with self.assertRaises(c.ContractError):
                c.load_json(path)

    def test_nonfinite_json_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            path.write_text('{"x":NaN}')
            with self.assertRaises(c.ContractError):
                c.load_json(path)

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            path.write_text('{')
            with self.assertRaises(c.ContractError):
                c.load_json(path)

    def test_exact_48khz_frame_mapping(self):
        fps = {'num': 24, 'den': 1}
        for frame in [0, 1, 23, 24, 960]:
            self.assertEqual(c.frame_to_sample(frame, fps), frame * 2000)
        self.assertEqual(c.frame_time(960, fps), 40)

    def test_fractional_fps_no_cumulative_rounding_drift(self):
        fps = {'num': 30000, 'den': 1001}
        indices = [c.frame_to_sample(i, fps) for i in range(1001)]
        self.assertEqual(indices[1000], 1601600)
        self.assertEqual(set(b-a for a, b in zip(indices, indices[1:])), {1601, 1602})

    def test_negative_frame_to_sample(self):
        with self.assertRaises(c.ContractError):
            c.frame_to_sample(-1, {'num': 24, 'den': 1})

    def test_canonical_hash_ignores_dictionary_order(self):
        self.assertEqual(c.canonical_hash({'b': 1, 'a': 2}), c.canonical_hash({'a': 2, 'b': 1}))
        self.assertNotEqual(c.canonical_hash({'a': 1}), c.canonical_hash({'a': 2}))


class SpeechContracts(unittest.TestCase):
    def setUp(self):
        # Deliberately only a schema fixture; no voice/alignment claim.
        self.doc = {'schema_version': 1, 'kind': 'speech', 'speech_id': 'test', 'speaker': 'fixture',
                    'take_revision': '1', 'audio_path': 'audio/fixture.wav', 'audio_sha256': '0' * 64,
                    'sample_rate': 48000, 'sample_count': 48000, 'transcript': 'па',
                    'alignment_source': 'test_fixture',
                    'phones': [{'symbol': 'p', 'start_sample': 0, 'end_sample': 4000, 'reviewed': False},
                               {'symbol': 'a', 'start_sample': 4000, 'end_sample': 48000, 'reviewed': False}]}

    def test_valid_sample_spans(self):
        c.validate_document(self.doc)

    def test_overlap_rejected(self):
        self.doc['phones'][1]['start_sample'] = 3999
        with self.assertRaises(c.ContractError):
            c.validate_document(self.doc)

    def test_overrun_rejected(self):
        self.doc['phones'][1]['end_sample'] = 48001
        with self.assertRaises(c.ContractError):
            c.validate_document(self.doc)

    def test_zero_length_phone_rejected(self):
        self.doc['phones'][0]['end_sample'] = 0
        with self.assertRaises(c.ContractError):
            c.validate_document(self.doc)

    def test_speech_path_escape_rejected(self):
        self.doc['audio_path'] = '../fixture.wav'
        with self.assertRaises(c.ContractError):
            c.validate_document(self.doc)

    def test_unhashed_audio_rejected(self):
        self.doc['audio_sha256'] = 'not-a-hash'
        with self.assertRaises(c.ContractError):
            c.validate_document(self.doc)


class PathsAndTimeline(unittest.TestCase):
    def test_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as root:
            for value in ['../escape', '/etc/passwd', 'C:/escape', 'dir\\file', '']:
                with self.subTest(path=value), self.assertRaises(c.ContractError):
                    c.safe_path(root, value)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            (Path(root) / 'escape').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(c.ContractError):
                c.safe_path(root, 'escape/file')

    def test_scalar_linear_interpolation_and_holds(self):
        track = {'keys': [{'frame': 2, 'value': 0}, {'frame': 6, 'value': 1}]}
        self.assertEqual([evaluate_track(track, f) for f in [-1, 2, 4, 6, 10]], [0, 0, .5, 1, 1])

    def test_vector_linear_interpolation(self):
        track = {'keys': [{'frame': 0, 'value': [0, 2, 4]}, {'frame': 2, 'value': [2, 4, 6]}]}
        self.assertEqual(evaluate_track(track, 1), [1, 3, 5])

    def test_evaluate_outside_half_open_shot(self):
        shot = c.load_bundle(c.ROOT / 'studio/production/smoke')['shot']
        for frame in [-1, 24, .5]:
            with self.subTest(frame=frame), self.assertRaises(c.ContractError):
                evaluate(shot, frame)

    def test_missing_object_fails_binding(self):
        from types import SimpleNamespace
        bpy = SimpleNamespace(data=SimpleNamespace(objects={}))
        with self.assertRaises(c.ContractError):
            bind_controls(bpy, {'bindings': {'test': {'object': 'Absent', 'type': 'OBJECT_LOCATION'}}})

    def test_missing_shape_fails_binding(self):
        from types import SimpleNamespace
        obj = SimpleNamespace(data=SimpleNamespace(shape_keys=None))
        bpy = SimpleNamespace(data=SimpleNamespace(objects={'Jaw': obj}))
        with self.assertRaises(c.ContractError):
            bind_controls(bpy, {'bindings': {'jaw.open': {'object': 'Jaw', 'type': 'SHAPE_KEY', 'shape_key': 'Open'}}})

    def test_no_silent_missing_control(self):
        with self.assertRaises(c.ContractError):
            apply_controls({}, {'jaw.open': .5})


class IntegrityAndFailures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = {'schema_version': 1, 'kind': 'quality_report', 'scope': 'technical_smoke_only',
                       'status': 'passed', 'checks': [{'id': 'unit_fixture', 'passed': True, 'detail': 'not a render'}],
                       'metrics': {}, 'limitations': ['Unit-test stand-ins, not real media.']}
        (self.root / 'report.json').write_text(json.dumps(self.report))
        for name in ['technical-smoke.mp4', 'scene.blend', 'worker-report.json']:
            (self.root / name).write_text('UNIT FIXTURE ONLY: not real media')
        self.manifest = {'schema_version': 1, 'kind': 'manifest', 'job_id': '0'*64, 'purpose': 'technical_smoke',
                         'status': 'complete', 'backend': 'unit_fixture', 'inputs_sha256': '0'*64,
                         'code_sha256': '0'*64, 'runtime_sha256': '0'*64, 'frame_range': [0, 24],
                         'fps': {'num': 24, 'den': 1}, 'resolution': [1920, 1080], 'artifacts': []}
        self.refresh()

    def refresh(self):
        self.manifest['artifacts'] = [{'path': p.name, 'bytes': p.stat().st_size,
                                      'sha256': c.file_hash(p), 'role': 'unit_fixture'}
                                     for p in sorted(self.root.iterdir()) if p.is_file()]

    def test_verified_integrity_fixture(self):
        self.assertEqual(runner.verify_artifacts(self.manifest, self.root)['status'], 'passed')

    def test_modified_artifact_rejected(self):
        (self.root / 'scene.blend').write_text('changed')
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_missing_artifact_rejected(self):
        (self.root / 'technical-smoke.mp4').unlink()
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_duplicate_artifact_paths_rejected(self):
        self.manifest['artifacts'].append(self.manifest['artifacts'][0])
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_failure_status_cannot_resume(self):
        self.manifest['status'] = 'failed'
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_manifest_path_escape_rejected(self):
        self.manifest['artifacts'][0]['path'] = '../secret'
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_missing_required_outputs_rejected_even_when_hashes_match(self):
        self.manifest['artifacts'] = [x for x in self.manifest['artifacts'] if x['path'] != 'scene.blend']
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_failed_report_rejected_even_when_hashes_match(self):
        self.report['status'] = 'failed'
        (self.root / 'report.json').write_text(json.dumps(self.report))
        self.refresh()
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def test_false_check_rejected_even_if_status_claims_passed(self):
        self.report['checks'][0]['passed'] = False
        (self.root / 'report.json').write_text(json.dumps(self.report))
        self.refresh()
        with self.assertRaises(c.ContractError):
            runner.verify_artifacts(self.manifest, self.root)

    def _failed_worker(self, error=None):
        bundle = c.load_bundle(c.ROOT / 'studio/production/smoke')
        result = subprocess.CompletedProcess([], 7)
        with patch.object(runner, 'load_bundle', return_value=bundle), \
             patch.object(runner, 'runtime_identity', return_value={'test': 'fixture'}), \
             patch.object(runner, 'code_identity', return_value='0'*64), \
             patch.object(runner.subprocess, 'run', side_effect=error, return_value=result), \
             patch('builtins.print'):
            with self.assertRaises((c.ContractError, subprocess.TimeoutExpired)):
                runner.run('unused', self.root / 'jobs')
        job = next((self.root / 'jobs').iterdir())
        self.assertFalse((job / 'manifest.json').exists())
        self.assertTrue((job / 'failure.json').exists())
        return c.load_json(job / 'failure.json')

    def test_worker_nonzero_never_completes_job(self):
        self.assertIn('worker failed (7)', self._failed_worker()['error'])

    def test_worker_timeout_never_completes_job(self):
        self.assertEqual(self._failed_worker(subprocess.TimeoutExpired('worker', 1))['error_type'], 'TimeoutExpired')

    def cache_job(self):
        import shutil
        bundle = c.load_bundle(c.ROOT / 'studio/production/smoke')
        identity = {'test': 'fixture'}
        input_hash, code_hash, runtime_hash = c.canonical_hash(bundle), '0'*64, c.canonical_hash(identity)
        job_id = c.canonical_hash({'inputs': input_hash, 'code': code_hash, 'runtime': runtime_hash})
        output = self.root / 'jobs'
        job = output / job_id
        job.mkdir(parents=True)
        for entry in self.manifest['artifacts']:
            shutil.copyfile(self.root / entry['path'], job / entry['path'])
        manifest = {**self.manifest, 'job_id': job_id, 'inputs_sha256': input_hash,
                    'code_sha256': code_hash, 'runtime_sha256': runtime_hash}
        runner.write_json(job / 'manifest.json', manifest)
        return bundle, identity, output, job

    def test_completed_resume_does_not_invoke_renderer(self):
        bundle, identity, output, job = self.cache_job()
        with patch.object(runner, 'load_bundle', return_value=bundle), \
             patch.object(runner, 'runtime_identity', return_value=identity), \
             patch.object(runner, 'code_identity', return_value='0'*64), \
             patch.object(runner.subprocess, 'run', side_effect=AssertionError('must not render')), \
             patch('builtins.print'):
            self.assertEqual(runner.run('unused', output, resume=True), job)

    def test_completed_job_not_blindly_overwritten(self):
        bundle, identity, output, job = self.cache_job()
        before = c.file_hash(job / 'manifest.json')
        with patch.object(runner, 'load_bundle', return_value=bundle), \
             patch.object(runner, 'runtime_identity', return_value=identity), \
             patch.object(runner, 'code_identity', return_value='0'*64):
            with self.assertRaisesRegex(c.ContractError, 'job exists'):
                runner.run('unused', output)
        self.assertEqual(c.file_hash(job / 'manifest.json'), before)

    def test_changed_code_cannot_reuse_completed_job(self):
        bundle, identity, output, job = self.cache_job()
        with patch.object(runner, 'load_bundle', return_value=bundle), \
             patch.object(runner, 'runtime_identity', return_value=identity), \
             patch.object(runner, 'code_identity', return_value='1'*64), \
             patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 9)), \
             patch('builtins.print'):
            with self.assertRaisesRegex(c.ContractError, 'worker failed'):
                runner.run('unused', output, resume=True)
        self.assertTrue((job / 'manifest.json').exists())
        self.assertEqual(len(list(output.iterdir())), 2)

    def test_tampered_completed_job_cannot_resume(self):
        bundle, identity, output, job = self.cache_job()
        (job / 'scene.blend').write_text('corruption')
        with patch.object(runner, 'load_bundle', return_value=bundle), \
             patch.object(runner, 'runtime_identity', return_value=identity), \
             patch.object(runner, 'code_identity', return_value='0'*64):
            with self.assertRaisesRegex(c.ContractError, 'changed'):
                runner.run('unused', output, resume=True)

    def test_runtime_version_mismatch_rejected_before_worker(self):
        with patch.object(runner.importlib.metadata, 'version', return_value='WRONG'):
            with self.assertRaises(c.ContractError):
                runner.runtime_identity()

    def test_native_fetch_requires_explicit_experimental_opt_in(self):
        with self.assertRaisesRegex(ValueError, 'requires'):
            prepare(c.ROOT / '.cache/unit-test-not-created', fetch=True)


if __name__ == '__main__':
    unittest.main()
