"""Bounded, resumable external-package preview. No family/artistic approval implied."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import fcntl
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

from .contracts import ROOT, ContractError, canonical_hash, file_hash, load_json, safe_path
from .packages import validate_bundle, validate
from .kinematics import contact_audit, finger_audit
from .resources import chunks, effective_threads, run_guarded
from .run_probe import code_identity, runtime_identity, write_json


def artifacts(directory, paths):
    result=[]
    for p in sorted(paths):
        relative=p.relative_to(directory).as_posix()
        safe_path(directory,relative)
        result.append({'path':relative,'sha256':file_hash(p),'bytes':p.stat().st_size})
    return result


def verify_files(directory, entries):
    seen=set()
    for entry in entries:
        name=entry['path']
        if name in seen:raise ContractError('duplicate artifact path')
        seen.add(name);path=safe_path(directory,name)
        if not path.is_file() or path.stat().st_size!=entry['bytes'] or file_hash(path)!=entry['sha256']:
            raise ContractError(f'artifact missing or changed: {name}')


def verify_job(job, manifest, identity, shot, package):
    validate(manifest)
    if manifest['job_id'] != canonical_hash(identity) or manifest['identity'] != identity:
        raise ContractError('completed manifest identity mismatch')
    verify_files(job, manifest['artifacts'])
    names = {x['path'] for x in manifest['artifacts']}
    start, end = shot['frame_range']
    required = {'dad-preview.mp4', 'report.json', 'identity.json', 'input/asset.blend',
                'input/project.json', 'input/package.json', 'input/shot.json'}
    required.update(f'frames/{i:06d}.png' for i in range(end-start))
    if not required <= names:
        raise ContractError('required outputs absent from completed manifest')
    report = load_json(job/'report.json')
    if (report.get('status') != 'passed' or report.get('job_id') != manifest['job_id'] or
            report.get('identity') != identity or report.get('frame_range') != [start,end] or
            report.get('package_sha256') != package['blend']['sha256']):
        raise ContractError('completed report identity/status mismatch')
    return report


def worker_env(native_dir, threads):
    env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','LANG','LC_ALL','TMPDIR','LD_LIBRARY_PATH'}}
    env.update(OMP_NUM_THREADS=str(threads),OPENBLAS_NUM_THREADS='1')
    if native_dir:env['LD_LIBRARY_PATH']=str(native_dir)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    return env


def render_chunk(job, job_id, first, end, project, package, native_dir, resume):
    directory=safe_path(job,f'chunks/{first:06d}-{end:06d}');directory.mkdir(parents=True,exist_ok=True)
    checkpoint=directory/'chunk.json'
    identity=canonical_hash({'job_id':job_id,'frame_range':[first,end]})
    if checkpoint.exists():
        if not resume:raise ContractError('completed chunk exists without --resume')
        marker=load_json(checkpoint)
        if marker.get('identity')!=identity or marker.get('status')!='complete':raise ContractError('chunk identity/status mismatch')
        verify_files(directory,marker['artifacts'])
        attempt=safe_path(directory,marker['attempt'])
        print('CHUNK_REUSED',first,end,flush=True)
        return attempt,True
    attempt=directory/f'attempt-{uuid.uuid4().hex}';attempt.mkdir()
    try:
        command=[sys.executable,'-m','studio.pipeline.backends.package_worker','--job',str(job/'input'),
                 '--output',str(attempt),'--first',str(first),'--end',str(end)]
        budget=project['resources']
        result=run_guarded(command,attempt/'worker.log',cwd=ROOT,
            env=worker_env(native_dir,effective_threads(project['render']['threads'])),
            rss_limit_mb=budget['rss_limit_mb'],timeout_seconds=budget['timeout_seconds'])
        report=load_json(attempt/'worker-report.json')
        if (report['status']!='complete' or report['frame_range']!=[first,end] or
                report['package_blend_sha256']!=package['blend']['sha256'] or
                report['asset_id']!=package['asset_id'] or report['asset_revision']!=package['revision'] or
                [x['frame'] for x in report['measurements']]!=list(range(first,end))):
            raise ContractError('worker report identity or frame coverage mismatch')
        if report['peak_worker_rss_bytes']>budget['rss_limit_mb']*1024*1024:
            raise ContractError('worker self-reported peak exceeded RSS budget')
        expected=[f'{f-project["_shot_start"]:06d}.png' for f in range(first,end)]
        if sorted(p.name for p in (attempt/'frames').glob('*.png'))!=expected:raise ContractError('chunk PNG coverage mismatch')
        from PIL import Image
        for path in (attempt/'frames').glob('*.png'):
            with Image.open(path) as image:
                if list(image.size)!=project['resolution'] or image.format!='PNG':raise ContractError('wrong frame dimensions/format')
                image.verify()
        if max(row['max_ik_error_m'] for row in report['measurements'])>.005:raise ContractError('IK residual exceeded 0.005 m')
        write_json(attempt/'process.json',result.to_dict())
        marker={'schema_version':2,'kind':'chunk_checkpoint','identity':identity,'status':'complete',
                'attempt':attempt.name,'frame_range':[first,end],
                'artifacts':artifacts(directory,[p for p in attempt.rglob('*') if p.is_file()])}
        write_json(checkpoint,marker)
        print('CHUNK_COMPLETE',first,end,result.observed_peak_rss_bytes,flush=True)
        return attempt,False
    except BaseException as exc:
        write_json(attempt/'failure.json',{'status':'failed','type':type(exc).__name__,'error':str(exc)})
        raise


def encode(job,project,count):
    import imageio_ffmpeg
    binary=imageio_ffmpeg.get_ffmpeg_exe();budget=project['resources']
    fps=f'{project["fps"]["num"]}/{project["fps"]["den"]}'
    cmd=[binary,'-hide_banner','-y','-framerate',fps,'-start_number','0','-i',str(job/'frames/%06d.png'),
         '-frames:v',str(count),'-an','-c:v','libx264','-threads',str(effective_threads(project['render']['threads'])),
         '-preset','medium','-crf','18','-vf','scale=out_color_matrix=bt709:out_range=tv',
         '-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','iec61966-2-1',
         '-movflags','+faststart',str(job/'dad-preview.mp4')]
    result=run_guarded(cmd,job/'encode.log',cwd=ROOT,rss_limit_mb=budget['rss_limit_mb'],timeout_seconds=budget['timeout_seconds'])
    decoded=run_guarded([binary,'-v','error','-xerror','-i',str(job/'dad-preview.mp4'),'-map','0:v:0',
                         '-f','framehash','-hash','sha256','-'],job/'decode.framehash',cwd=ROOT,
                        rss_limit_mb=budget['rss_limit_mb'],timeout_seconds=budget['timeout_seconds'])
    lines=(job/'decode.framehash').read_text().splitlines()
    frames=[line for line in lines if line and not line.startswith('#')]
    pts=[int(line.split(',')[2]) for line in frames]
    tb=[Fraction(line.split(':',1)[1].strip()) for line in lines if line.startswith('#tb 0:')]
    dims=[line.split(':',1)[1].strip() for line in lines if line.startswith('#dimensions 0:')]
    if (len(frames)!=count or pts!=list(range(count)) or tb!=[Fraction(project['fps']['den'],project['fps']['num'])]
            or dims!=[f'{project["resolution"][0]}x{project["resolution"][1]}']):
        raise ContractError('encoded full decode/frame count/PTS/timebase/dimensions mismatch')
    return {'encode':result.to_dict(),'decode':decoded.to_dict(),'decoded_frames':len(frames),
            'resolution':project['resolution'],'fps':project['fps'],'silent_preview':True}


def run(inputs, package_path, output, native_dir=None, resume=False, record=None, max_new_chunks=None):
    started=time.monotonic()
    project, package, shot=validate_bundle(load_json(inputs/'project.json'),load_json(package_path),load_json(inputs/'shot.json'))
    runtime=runtime_identity(native_dir)
    identity={'inputs':canonical_hash({'project':project,'package':package,'shot':shot}),
              'code':code_identity(),'runtime':canonical_hash(runtime)}
    job_id=canonical_hash(identity);job=safe_path(output,job_id)
    existed=job.exists();job.mkdir(parents=True,exist_ok=True)
    with safe_path(job,'.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise ContractError('job already running') from exc
        if existed and not resume:raise ContractError('job exists: use --resume, never overwrite')
        if existed and load_json(job/'identity.json')!=identity:raise ContractError('job identity mismatch')
        snapshot=copy.deepcopy(package);snapshot['blend']['path']=(job/'input/asset.blend').relative_to(ROOT).as_posix()
        if not existed:
            write_json(job/'identity.json',identity)
            (job/'input').mkdir()
            shutil.copyfile(safe_path(ROOT,package['blend']['path']),job/'input/asset.blend')
            for name,doc in [('project',project),('package',snapshot),('shot',shot)]:write_json(job/'input'/f'{name}.json',doc)
        for name,expected in [('project',project),('package',snapshot),('shot',shot)]:
            if load_json(job/'input'/f'{name}.json')!=expected:raise ContractError('job input snapshot changed')
        validate_bundle(project,snapshot,shot)
        if (job/'manifest.json').exists():
            manifest=load_json(job/'manifest.json')
            report=verify_job(job,manifest,identity,shot,package)
            print('PACKAGE_CACHE_VERIFIED',job_id,flush=True)
        else:
            try:
                first,end=shot['frame_range'];attempts=[];reused=0;fresh=0
                internal={**project,'_shot_start':first}
                for a,b in chunks(first,end,project['resources']['chunk_frames']):
                    attempt,hit=render_chunk(job,job_id,a,b,internal,package,native_dir,resume)
                    attempts.append(attempt);reused+=int(hit);fresh+=int(not hit)
                    if max_new_chunks is not None and fresh>=max_new_chunks:
                        write_json(job/'paused.json',{'status':'paused','new_chunks':fresh,'reused_chunks':reused})
                        print('PACKAGE_PAUSED',job_id,flush=True)
                        return job,False
                (job/'frames').mkdir(exist_ok=True)
                reports=[];processes=[]
                for attempt in attempts:
                    reports.append(load_json(attempt/'worker-report.json'));processes.append(load_json(attempt/'process.json'))
                    for p in (attempt/'frames').glob('*.png'):shutil.copyfile(p,job/'frames'/p.name)
                media=encode(job,project,end-first)
                rows=[row for report in reports for row in report['measurements']]
                if [x['frame'] for x in rows]!=list(range(first,end)):raise ContractError('aggregate measurement coverage mismatch')
                if len({r['raw_png_sha256'] for r in rows})<2:raise ContractError('render did not vary')
                motion_checks={}
                if shot.get('contacts'):
                    motion_checks['contacts']=contact_audit(rows,shot['contacts'],package.get('contact_probes',[]),[first,end])
                if shot.get('finger_checks'):
                    motion_checks['fingers']=finger_audit(rows,shot['finger_checks'])
                if motion_checks:
                    motion_checks['bones']={'passed':max(row['bone_relative_length_error'] for row in rows)<.001,'relative_length_error':max(row['bone_relative_length_error'] for row in rows)}
                if any(not c['passed'] for c in motion_checks.values()):
                    write_json(job/'motion-failure.json',motion_checks)
                    raise ContractError('evaluated stance/finger/bone quality check failed')
                first_skin=rows[0]['skin_vertices_m']
                span=max((math.dist(value,first_skin[name]) for row in rows for name,value in row['skin_vertices_m'].items()),default=0)
                if span<.05:raise ContractError('evaluated skinned mesh did not move')
                report={'schema_version':2,'kind':'package_preview_report','status':'passed','scope':'unreviewed rig blockout only',
                    'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'job_id':job_id,'identity':identity,
                    'asset_id':package['asset_id'],'asset_revision':package['revision'],'art_status':'unreviewed','motion_checks':motion_checks,
                    'package_sha256':package['blend']['sha256'],'runtime':runtime,'frame_range':[first,end],
                    'chunks':len(attempts),'reused_chunks_this_invocation':reused,'new_chunks_this_invocation':fresh,
                    'worker_processes':processes,'effective_threads':sorted({r['effective_threads'] for r in reports}),
                    'peak_worker_rss_bytes':max(r['peak_worker_rss_bytes'] for r in reports),
                    'peak_observed_group_rss_bytes':max(p['observed_peak_rss_bytes'] for p in processes),
                    'max_ik_error_m':max(row['max_ik_error_m'] for row in rows),'skin_vertex_span_m':span,
                    'wall_seconds_this_invocation':round(time.monotonic()-started,4),'media':media,
                    'limitations':['Not approved likeness/topology/face rig, walking, lip sync or artistic acting.',
                        'Preview is silent, native preview resolution, not 1080p delivery.',
                        'RSS guard is sampled, not a hard OS memory sandbox; only trusted local packages.',
                        'Native mirror remains experimental; no official production image or 960-frame stress proof.']}
                write_json(job/'report.json',report)
                (job/'paused.json').unlink(missing_ok=True)
                if (job/'last-failure.json').exists():
                    (job/'failure-history').mkdir(exist_ok=True)
                    (job/'last-failure.json').rename(job/'failure-history'/f'{uuid.uuid4().hex}.json')
                included=[p for p in job.rglob('*') if p.is_file() and p.name not in ('.lock','manifest.json','paused.json')]
                manifest={'schema_version':2,'kind':'render_manifest','job_id':job_id,'status':'complete',
                          'identity':identity,'artifacts':artifacts(job,included)}
                verify_job(job,manifest,identity,shot,package);write_json(job/'manifest.json',manifest)
            except BaseException as exc:
                write_json(job/'last-failure.json',{'status':'failed','type':type(exc).__name__,'error':str(exc)})
                raise
        if record:
            persisted=copy.deepcopy(report);persisted['artifact_cache_directory']=job.relative_to(ROOT).as_posix()
            persisted['manifest_sha256']=file_hash(job/'manifest.json')
            write_json(record,persisted)
        print('PACKAGE_PREVIEW_PASSED',job/'dad-preview.mp4',flush=True)
        return job,True


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',default='studio/production/dad-preview')
    parser.add_argument('--package',default='studio/out/dad-blockout/package.json')
    parser.add_argument('--output',default='studio/out/package-preview')
    parser.add_argument('--native-dir');parser.add_argument('--resume',action='store_true')
    parser.add_argument('--record');parser.add_argument('--max-new-chunks',type=int)
    args=parser.parse_args(argv)
    try:
        if args.max_new_chunks is not None and args.max_new_chunks<1:raise ContractError('positive max-new-chunks required')
        _,complete=run(safe_path(ROOT,args.inputs),safe_path(ROOT,args.package),safe_path(ROOT,args.output),
            safe_path(ROOT,args.native_dir) if args.native_dir else None,args.resume,
            safe_path(ROOT,args.record) if args.record else None,args.max_new_chunks)
        return 0 if complete else 75
    except (ContractError,OSError,ValueError,KeyError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
