"""V2 contract and REAL process-guard tests; unit media files are explicit stand-ins."""
from __future__ import annotations
import copy
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import psutil
from studio.pipeline.contracts import ROOT, ContractError, canonical_hash, file_hash, load_json
from studio.pipeline.packages import validate, validate_bundle, validator, apply
from studio.pipeline.resources import WorkerError, chunks, effective_threads, run_guarded
from studio.pipeline.render_package import artifacts, verify_files, verify_job
from studio.pipeline.run_probe import write_json


class PackageContracts(unittest.TestCase):
    def setUp(self):
        base=ROOT/'studio/production/dad-preview'
        self.p=load_json(base/'project.json');self.a=load_json(base/'package-r1.json');self.s=load_json(base/'shot.json')

    def reject(self):
        with self.assertRaises(ContractError):validate_bundle(self.p,self.a,self.s,verify_files=False)

    def test_recorded_v2_metadata_not_actual_media(self):
        validate_bundle(self.p,self.a,self.s,verify_files=False)

    def test_all_four_v2_schemas(self):
        for kind in ['project','shot','asset_package','render_manifest']:validator(kind)

    def test_v1_not_silently_migrated(self):
        self.p['schema_version']=1;self.reject()

    def test_wrong_kind(self):
        self.a['kind']='asset';self.reject()

    def test_unknown_field(self):
        self.p['production_approved']=True;self.reject()

    def test_no_self_approved_character(self):
        self.a['art_status']='approved';self.reject()

    def test_wrong_axis(self):
        self.a['coordinate_system']='Y_UP';self.reject()

    def test_degrees_rejected(self):
        self.a['rotation_unit']='degree';self.reject()

    def test_cross_reference(self):
        self.s['asset_id']='other';self.reject()

    def test_revision_pinned(self):
        self.s['asset_revision']='r0';self.reject()

    def test_absolute_blend_path(self):
        self.a['blend']['path']='/tmp/file.blend';self.reject()

    def test_traversal_blend_path(self):
        self.a['blend']['path']='../file.blend';self.reject()

    def test_network_blend_rejected(self):
        self.a['blend']['path']='https://example.org/file.blend';self.reject()

    def test_wrong_asset_type(self):
        self.a['blend']['path']='file.obj';self.reject()

    def test_missing_pose_target(self):
        del self.a['bindings']['head.rotation']['target'];self.reject()

    def test_extra_target_not_silently_ignored(self):
        self.a['bindings']['arm.R.target']['target']='bone';self.reject()

    def test_unknown_channel(self):
        self.s['tracks'][0]['control']='missing';self.reject()

    def test_duplicate_channel(self):
        self.s['tracks'].append(copy.deepcopy(self.s['tracks'][0]));self.reject()

    def test_zero_time_denominator(self):
        self.p['fps']['den']=0;self.reject()

    def test_fractional_fps_supported(self):
        self.p['fps']={'num':30000,'den':1001};validate_bundle(self.p,self.a,self.s,verify_files=False)

    def test_frame_end_is_exclusive(self):
        self.s['tracks'][0]['keys'][-1]['frame']=48;self.reject()

    def test_missing_last_key(self):
        self.s['tracks'][0]['keys'].pop();self.reject()

    def test_boolean_key_frame(self):
        self.s['tracks'][0]['keys'][0]['frame']=False;self.reject()

    def test_nonfinite_keys(self):
        self.s['tracks'][0]['keys'][0]['value'][0]=math.inf;self.reject()

    def test_shape_range(self):
        self.s['tracks'][3]['keys'][0]['value']=1.5;self.reject()

    def test_vector_required_for_rotation(self):
        self.s['tracks'][2]['keys'][0]['value']=.5;self.reject()

    def test_odd_resolution(self):
        self.p['resolution'][0]=959;self.reject()

    def test_no_unbounded_chunk(self):
        self.p['resources']['chunk_frames']=0;self.reject()

    def test_no_unbounded_memory(self):
        self.p['resources']['rss_limit_mb']=999999;self.reject()

    def test_missing_files_fail_not_procedural_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ContractError,'missing or hash changed'):
                validate_bundle(self.p,self.a,self.s,root=Path(root))

    def test_correct_hashes_and_tampered_file(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);blend=root/'fixture.blend';recipe=root/'recipe.py'
            blend.write_bytes(b'NOT A BLEND: unit integrity fixture');recipe.write_text('# unit fixture')
            self.a['blend'].update(path='fixture.blend',sha256=file_hash(blend))
            self.a['provenance'].update(authoring_script='recipe.py',script_sha256=file_hash(recipe))
            validate_bundle(self.p,self.a,self.s,root=root)
            blend.write_bytes(b'changed')
            with self.assertRaises(ContractError):validate_bundle(self.p,self.a,self.s,root=root)

    def test_unbound_control_fails(self):
        with self.assertRaises(ContractError):apply({}, {'jaw.open':.5})


class ProcessGuards(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def run_code(self,code,**kwargs):
        return run_guarded([sys.executable,'-c',code],self.root/'worker.log',cwd=ROOT,
                           rss_limit_mb=kwargs.get('rss',128),timeout_seconds=kwargs.get('timeout',5))

    def test_real_subprocess_success(self):
        r=self.run_code('print("guard-ok",flush=True)')
        self.assertEqual(r.exit_code,0);self.assertIn('guard-ok',(self.root/'worker.log').read_text())

    def test_real_nonzero_fails(self):
        with self.assertRaisesRegex(WorkerError,'exited 7'):self.run_code('raise SystemExit(7)')

    def test_real_timeout_kills_worker(self):
        with self.assertRaisesRegex(WorkerError,'timeout'):self.run_code('import time;time.sleep(20)',timeout=.2)

    def test_real_memory_limit_kills_worker(self):
        with self.assertRaisesRegex(WorkerError,'RSS limit'):
            self.run_code('import time;data=bytearray(64*1024*1024);time.sleep(20)',rss=16)

    def test_real_descendant_is_killed_on_timeout(self):
        pidfile=self.root/'child.pid'
        code=f'import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(30)'
        with self.assertRaisesRegex(WorkerError,'timeout'):self.run_code(code,timeout=.5)
        self.assertTrue(pidfile.exists())
        try:
            child=psutil.Process(int(pidfile.read_text()))
            try:child.wait(timeout=2)
            except psutil.TimeoutExpired:pass
            if child.is_running():self.assertIn(child.status(),[psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD])
        except psutil.NoSuchProcess:pass

    def test_threads_capped_to_affinity(self):
        with patch('os.sched_getaffinity',return_value={0,1}):self.assertEqual(effective_threads(8),2)

    def test_invalid_threads(self):
        for n in [0,-1,True,1.5]:
            with self.subTest(n=n),self.assertRaises(ContractError):effective_threads(n)

    def test_invalid_budgets(self):
        for value in [math.nan,math.inf,-1,False]:
            with self.subTest(value=value),self.assertRaises(ContractError):self.run_code('pass',rss=value)

    def test_chunks_cover_half_open_range(self):
        self.assertEqual(chunks(3,14,4),[(3,7),(7,11),(11,14)])

    def test_invalid_chunks(self):
        for args in [(0,0,4),(4,2,2),(0,4,0),(0,4,True)]:
            with self.subTest(args=args),self.assertRaises(ContractError):chunks(*args)


class Integrity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.identity={k:str(i+1)*64 for i,k in enumerate(['inputs','code','runtime'])}
        self.shot={'frame_range':[0,2]};self.package={'blend':{'sha256':'4'*64}}
        report={'status':'passed','job_id':canonical_hash(self.identity),'identity':self.identity,
                'frame_range':[0,2],'package_sha256':'4'*64}
        names=['dad-preview.mp4','identity.json','input/asset.blend','input/project.json','input/package.json','input/shot.json','frames/000000.png','frames/000001.png']
        for name in names:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'UNIT FIXTURE, NOT MEDIA')
        write_json(self.root/'report.json',report)
        self.manifest={'schema_version':2,'kind':'render_manifest','job_id':canonical_hash(self.identity),
                       'status':'complete','identity':self.identity,'artifacts':artifacts(self.root,[p for p in self.root.rglob('*') if p.is_file()])}

    def verify(self):return verify_job(self.root,self.manifest,self.identity,self.shot,self.package)

    def test_integrity_fixture(self):self.assertEqual(self.verify()['status'],'passed')

    def test_changed_same_size_bytes(self):
        p=self.root/'dad-preview.mp4';s=p.read_bytes();p.write_bytes(bytes([s[0]^1])+s[1:])
        with self.assertRaises(ContractError):self.verify()

    def test_missing_output_not_hidden_by_manifest_omission(self):
        self.manifest['artifacts']=[e for e in self.manifest['artifacts'] if e['path']!='dad-preview.mp4']
        with self.assertRaisesRegex(ContractError,'required outputs'):self.verify()

    def test_empty_diagnostic_log_is_a_valid_hashed_artifact(self):
        (self.root/'empty.log').write_bytes(b'')
        self.manifest['artifacts']=artifacts(self.root,[p for p in self.root.rglob('*') if p.is_file()])
        self.assertEqual(self.verify()['status'],'passed')

    def test_wrong_manifest_identity(self):
        self.manifest['identity']['code']='5'*64
        with self.assertRaises(ContractError):self.verify()

    def test_report_cannot_claim_different_package(self):
        doc=load_json(self.root/'report.json');doc['package_sha256']='9'*64;write_json(self.root/'report.json',doc)
        self.manifest['artifacts']=artifacts(self.root,[p for p in self.root.rglob('*') if p.is_file()])
        with self.assertRaisesRegex(ContractError,'report identity'):self.verify()

    def test_traversal_rejected(self):
        self.manifest['artifacts'][0]['path']='../outside'
        with self.assertRaises(ContractError):self.verify()

    def test_duplicate_artifact_rejected(self):
        self.manifest['artifacts'].append(self.manifest['artifacts'][0])
        with self.assertRaises(ContractError):self.verify()

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            p=self.root/'dad-preview.mp4';p.unlink();p.symlink_to(Path(other)/'file')
            with self.assertRaises(ContractError):self.verify()


if __name__=='__main__':unittest.main()
