"""Execute and verify the narrow Blender smoke slice, not an episode renderer.

Usage: .venv-blender/bin/python -m studio.pipeline.run_probe [--native-dir ...]
"""
from __future__ import annotations

import argparse
import array
import copy
import datetime as dt
from fractions import Fraction
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
import wave

from .contracts import (ROOT, ContractError, canonical_hash, file_hash, frame_to_sample,
                        load_bundle, load_json, safe_path, validate_document)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temp.replace(path)


def runtime_identity(native_dir=None):
    versions = {}
    lock = ROOT / 'studio/production/blender-requirements.lock'
    for line in lock.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.split('==')
        actual = importlib.metadata.version(name)
        if version != actual:
            raise ContractError(f'runtime mismatch: {name} {actual}, expected {version}')
        versions[name] = actual
    native = {'provider': 'operating_system', 'production_approved': False,
              'note': 'OS package inventory/security approval is outside this smoke test'}
    if native_dir:
        lock_native = load_json(ROOT / 'studio/production/sandbox-native-libs.lock.json')
        for record in lock_native['libraries']:
            path = safe_path(native_dir, record['file'])
            if not path.is_file() or file_hash(path) != record['sha256']:
                raise ContractError(f'native dependency missing or changed: {record["file"]}')
        native = {'provider': 'isolated_distro_mirror_experiment', 'production_approved': False,
                  'lock_sha256': file_hash(ROOT / 'studio/production/sandbox-native-libs.lock.json'),
                  'note': 'Pinned mirror blobs, NOT official distro signatures or a production base image'}
    spec = importlib.util.find_spec('bpy')
    if spec is None or spec.origin is None:
        raise ContractError('bpy package not found')
    package = Path(spec.origin).parent
    ocio = package / '4.5/datafiles/colormanagement/config.ocio'
    return {'bpy_module_sha256': file_hash(spec.origin), 'ocio_sha256': file_hash(ocio),
            'python': platform.python_version(), 'platform': platform.platform(),
            'libc': list(platform.libc_ver()), 'packages': versions, 'native': native}


def code_identity():
    files = list((ROOT / 'studio/pipeline').rglob('*.py'))
    files += list((ROOT / 'studio/schemas').glob('*.json'))
    files += [ROOT / 'studio/fonts/Nunito-700.ttf']
    return canonical_hash({p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(files)})


def verify_artifacts(manifest, directory):
    validate_document(manifest)
    if manifest['status'] != 'complete':
        raise ContractError('cannot resume failed job')
    paths = set()
    for entry in manifest['artifacts']:
        if entry['path'] in paths:
            raise ContractError('duplicate artifact path')
        paths.add(entry['path'])
        path = safe_path(directory, entry['path'])
        if not path.is_file() or path.stat().st_size != entry['bytes'] or file_hash(path) != entry['sha256']:
            raise ContractError(f'artifact missing or changed: {entry["path"]}')
    if not {'report.json', 'technical-smoke.mp4', 'worker-report.json', 'scene.blend'} <= paths:
        raise ContractError('required smoke artifacts absent from manifest')
    report = validate_document(load_json(safe_path(directory, 'report.json')))
    if report['kind'] != 'quality_report' or report['status'] != 'passed' or not all(x['passed'] for x in report['checks']):
        raise ContractError('cached report did not pass')
    return report


def _tone(path, samples, rate):
    # Synthetic diagnostic audio, never passed off as dialogue or voice synthesis.
    data = array.array('h')
    for i in range(samples):
        seconds = i / rate
        local = seconds % .5
        envelope = max(0, 1 - local / .16) if local < .16 else 0
        envelope *= min(1, local / .012)
        value = .035 * envelope * math.sin(2 * math.pi * (440 if seconds < .5 else 660) * seconds)
        data.append(round(value * 32767))
    if sys.byteorder != 'little':
        data.byteswap()
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(data.tobytes())


def _ffmpeg_verify(binary, directory, bundle):
    p, shot = bundle['project'], bundle['shot']
    start, end = shot['frame_range']
    count = end - start
    rate = p['audio_sample_rate']
    samples = frame_to_sample(end, p['fps'], rate) - frame_to_sample(start, p['fps'], rate)
    _tone(directory / 'test-tone.wav', samples, rate)
    fps = f'{p["fps"]["num"]}/{p["fps"]["den"]}'
    command = [binary, '-hide_banner', '-y', '-framerate', fps, '-start_number', '0',
               '-i', str(directory / 'frames/%06d.png'), '-i', str(directory / 'test-tone.wav'),
               '-frames:v', str(count), '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-ar', str(rate),
               '-movflags', '+faststart', str(directory / 'technical-smoke.mp4')]
    with (directory / 'ffmpeg.log').open('wb') as log:
        tick = time.perf_counter()
        encoded = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        encode_seconds = time.perf_counter() - tick
    if encoded.returncode:
        raise ContractError(f'FFmpeg encoding failed ({encoded.returncode}); see ffmpeg.log')
    video = subprocess.run([binary, '-v', 'error', '-xerror', '-i', str(directory / 'technical-smoke.mp4'),
                            '-map', '0:v:0', '-f', 'framehash', '-hash', 'sha256', '-'],
                           capture_output=True, timeout=180, check=True)
    lines = video.stdout.decode().splitlines()
    hashes = [line for line in lines if line and not line.startswith('#')]
    decoded_pts = [int(line.split(',')[2].strip()) for line in hashes]
    expected_tb = Fraction(p['fps']['den'], p['fps']['num'])
    tb_lines = [line.split(':', 1)[1].strip() for line in lines if line.startswith('#tb 0:')]
    dims = [line.split(':', 1)[1].strip() for line in lines if line.startswith('#dimensions 0:')]
    width, height = p['resolution']
    audio = subprocess.run([binary, '-v', 'error', '-xerror', '-i', str(directory / 'technical-smoke.mp4'),
                            '-map', '0:a:0', '-c:a', 'pcm_s16le', '-f', 'wav', '-'],
                           capture_output=True, timeout=180, check=True)
    with wave.open(io.BytesIO(audio.stdout), 'rb') as wav:
        decoded_rate, channels, sample_width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        pcm = wav.readframes(samples + 4096)
    audio_samples = len(pcm) // (channels * sample_width)
    (directory / 'decoded-video.framehash').write_bytes(video.stdout)
    checks = [
        {'id': 'ffmpeg_full_video_decode', 'passed': len(hashes) == count and decoded_pts == list(range(count)),
         'detail': f'{len(hashes)} decoded frames, expected {count}, PTS {decoded_pts[:2]}…{decoded_pts[-2:]}'},
        {'id': 'encoded_resolution', 'passed': dims == [f'{width}x{height}'], 'detail': str(dims)},
        {'id': 'encoded_timebase', 'passed': len(tb_lines) == 1 and Fraction(tb_lines[0]) == expected_tb,
         'detail': str(tb_lines)},
        {'id': 'aac_native_48khz_mono', 'passed': decoded_rate == rate and channels == 1 and sample_width == 2,
         'detail': f'{decoded_rate} Hz, {channels} channel, {sample_width * 8}-bit decode'},
        {'id': 'aac_duration_padding', 'passed': 0 <= audio_samples - samples < 1024,
         'detail': f'{audio_samples} decoded samples; {samples} input; AAC tail padding <1024 allowed'},
        {'id': 'diagnostic_audio_not_silent', 'passed': any(pcm), 'detail': 'synthetic test tone, not dialogue'},
    ]
    version = subprocess.run([binary, '-version'], capture_output=True, text=True, check=True, timeout=10).stdout.splitlines()[0]
    metrics = {'ffmpeg_version': version, 'encode_exit_code': encoded.returncode,
               'video_decode_exit_code': video.returncode, 'audio_decode_exit_code': audio.returncode,
               'encode_seconds': round(encode_seconds, 4), 'decoded_frames': len(hashes),
               'input_audio_samples': samples, 'decoded_audio_samples': audio_samples,
               'decoded_audio_rate': decoded_rate, 'duration_seconds': float(Fraction(count * p['fps']['den'], p['fps']['num']))}
    return checks, metrics


def build_report(directory, bundle, worker, ff_checks, ff_metrics, runtime, elapsed):
    from PIL import Image

    start, end = bundle['shot']['frame_range']
    count = end - start
    rows = worker['measurements']
    if [r['frame'] for r in rows] != list(range(start, end)):
        raise ContractError('worker measurement coverage is incomplete')
    source_frames = sorted((directory / 'frames').glob('*.png'))
    valid_images = len(source_frames) == count
    for path in source_frames:
        with Image.open(path) as image:
            valid_images = valid_images and list(image.size) == bundle['project']['resolution'] and image.format == 'PNG'
            image.verify()
    def span(field):
        return max(math.dist(a[field], b[field]) for a in rows for b in rows)
    max_ik = max(row['ik_error_m'] for row in rows)
    max_bone = max(row['bone_relative_length_error'] for row in rows)
    arm_span, jaw_span = span('arm_vertex_m'), span('jaw_centroid_m')
    checks = [
        {'id': 'native_source_png_sequence', 'passed': valid_images, 'detail': f'{len(source_frames)} PNGs at {bundle["project"]["resolution"]}'},
        {'id': 'minimum_24_native_1080p_frames', 'passed': count >= 24 and bundle['project']['resolution'] == [1920, 1080],
         'detail': 'G1 runtime smoke target, NOT character quality approval'},
        {'id': 'headless_cycles_cpu', 'passed': worker['background'] and worker['engine'] == 'CYCLES' and worker['device'] == 'CPU',
         'detail': f'Blender {worker["blender"]}, background={worker["background"]}'},
        {'id': 'evaluated_ik_endpoint', 'passed': max_ik < .005, 'detail': f'max {max_ik:.8f} m; smoke tolerance 0.005 m'},
        {'id': 'evaluated_bone_lengths', 'passed': max_bone < .001, 'detail': f'max relative error {max_bone:.9f}'},
        {'id': 'evaluated_skin_moved', 'passed': arm_span > .05, 'detail': f'mesh vertex span {arm_span:.6f} m'},
        {'id': 'evaluated_shape_key_moved', 'passed': jaw_span > .1, 'detail': f'jaw mesh centroid span {jaw_span:.6f} m'},
        {'id': 'raw_render_varies', 'passed': len({r['raw_png_sha256'] for r in rows}) >= 12,
         'detail': 'raw render hashes recorded BEFORE labels; at least 12 distinct images'},
        *ff_checks,
    ]
    return {'schema_version': 1, 'kind': 'quality_report', 'scope': 'technical_smoke_only',
            'status': 'passed' if all(c['passed'] for c in checks) else 'failed', 'checks': checks,
            'metrics': {'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                        'blender': worker['blender'], 'blender_build_hash': worker['blender_build_hash'],
                        'worker_exit_code': 0, 'wall_seconds': round(elapsed, 4),
                        'worker_wall_seconds': worker['wall_seconds'], 'peak_worker_rss_bytes': worker['peak_rss_bytes'],
                        'max_child_rss_bytes': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
                        'render_samples': worker['samples'], 'denoise': worker['denoise'],
                        'max_ik_error_m': max_ik, 'max_bone_relative_error': max_bone,
                        'arm_vertex_span_m': arm_span, 'jaw_centroid_span_m': jaw_span,
                        'color_management': worker['color_management'], 'runtime': runtime, **ff_metrics},
            'limitations': ['Synthetic diagnostic geometry, not a family model or approved design.',
                            'No walking, contacts, lip sync, acting, or episode generation is validated.',
                            'Low-sample CPU smoke workload is not a production render benchmark.',
                            'Native distro mirror fallback is experimental, not a signed production OS image.',
                            'One run is not a clean-machine reproducibility or long-render stability proof.',
                            'OS-provider cache identity does not fingerprint every system library; production deployment is pending.',
                            'AAC decoding may include less than 1024 trailing padding samples.']}


def run(inputs, output, native_dir=None, resume=False, record=None):
    started = time.perf_counter()
    bundle = load_bundle(inputs)
    runtime = runtime_identity(native_dir)
    input_hash, code_hash, runtime_hash = canonical_hash(bundle), code_identity(), canonical_hash(runtime)
    job_id = canonical_hash({'inputs': input_hash, 'code': code_hash, 'runtime': runtime_hash})
    directory = safe_path(output, job_id)
    if directory.exists():
        if not resume:
            raise ContractError(f'job exists: {directory}; use --resume to verify, never blindly overwrite')
        manifest = load_json(directory / 'manifest.json')
        if (manifest['job_id'] != job_id or manifest['inputs_sha256'] != input_hash or
                manifest['code_sha256'] != code_hash or manifest['runtime_sha256'] != runtime_hash):
            raise ContractError('cache identity mismatch')
        report = verify_artifacts(manifest, directory)
        print('PROBE_CACHE_VERIFIED', job_id, flush=True)
    else:
        directory.mkdir(parents=True)
        write_json(directory / 'inputs.json', bundle)
        snapshot_dir = directory / 'input-config'
        for kind, document in bundle.items():
            write_json(snapshot_dir / f'{kind}.json', document)
        env = {k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'LD_LIBRARY_PATH'}}
        env.update({'OMP_NUM_THREADS': str(bundle['project']['render']['threads']), 'OPENBLAS_NUM_THREADS': '1'})
        if native_dir:
            env['LD_LIBRARY_PATH'] = str(Path(native_dir).resolve()) + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        command = [sys.executable, '-m', 'studio.pipeline.backends.blender_worker', '--inputs', str(snapshot_dir), '--output', str(directory)]
        try:
            print('PROBE_START', job_id, flush=True)
            with (directory / 'worker.log').open('wb') as log:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            if result.returncode:
                raise ContractError(f'Blender worker failed ({result.returncode}); see {directory / "worker.log"}')
            worker = load_json(directory / 'worker-report.json')
            import imageio_ffmpeg
            ff_checks, ff_metrics = _ffmpeg_verify(imageio_ffmpeg.get_ffmpeg_exe(), directory, bundle)
            report = build_report(directory, bundle, worker, ff_checks, ff_metrics, runtime, time.perf_counter() - started)
            validate_document(report)
            write_json(directory / 'report.json', report)
            if report['status'] != 'passed':
                raise ContractError(f'smoke quality checks failed: {directory / "report.json"}')
            artifacts = []
            for path in sorted(directory.rglob('*')):
                if path.is_file() and path.name != 'progress.json':
                    artifacts.append({'path': path.relative_to(directory).as_posix(), 'sha256': file_hash(path),
                                      'bytes': path.stat().st_size, 'role': 'render_frame' if path.suffix == '.png' else 'smoke_evidence'})
            manifest = {'schema_version': 1, 'kind': 'manifest', 'job_id': job_id, 'purpose': 'technical_smoke',
                        'status': 'complete', 'backend': 'blender_bpy_subprocess',
                        'inputs_sha256': input_hash, 'code_sha256': code_hash, 'runtime_sha256': runtime_hash,
                        'frame_range': bundle['shot']['frame_range'], 'fps': bundle['project']['fps'],
                        'resolution': bundle['project']['resolution'], 'artifacts': artifacts}
            validate_document(manifest)
            verify_artifacts(manifest, directory)
            write_json(directory / 'manifest.json', manifest)
        except BaseException as exc:
            # A failed/timeout/interrupted job must never acquire a success manifest.
            write_json(directory / 'failure.json', {'error_type': type(exc).__name__, 'error': str(exc), 'job_id': job_id})
            raise
    if record:
        snapshot = copy.deepcopy(report)
        snapshot['metrics']['evidence_manifest'] = manifest
        snapshot['metrics']['manifest_sha256'] = file_hash(directory / 'manifest.json')
        snapshot['metrics']['artifact_cache_directory'] = directory.relative_to(ROOT).as_posix()
        write_json(record, snapshot)
    print('PROBE_PASSED', directory / 'technical-smoke.mp4', flush=True)
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', default='studio/production/smoke')
    parser.add_argument('--output', default='studio/out/blender-smoke')
    parser.add_argument('--native-dir', help='Explicit experimental sandbox dependency directory; never implicit')
    parser.add_argument('--resume', action='store_true', help='Verify every artifact before reusing a completed identical job')
    parser.add_argument('--record', help='Persist compact factual evidence outside ignored render cache')
    args = parser.parse_args(argv)
    try:
        run(safe_path(ROOT, args.inputs), safe_path(ROOT, args.output),
            safe_path(ROOT, args.native_dir) if args.native_dir else None,
            args.resume, safe_path(ROOT, args.record) if args.record else None)
    except (ContractError, OSError, subprocess.SubprocessError, importlib.metadata.PackageNotFoundError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
