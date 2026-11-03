#!/usr/bin/env python3
"""Explicit, sandbox-only native-library experiment; NOT production provisioning.

Prefer genuine OS packages libxrender1 libxfixes3 libxi6 libxkbcommon0 libsm6
libice6 libgl1 in a supported Linux image. This fallback exists because the
sandbox cannot reach distro mirrors. It never patches Blender or creates stubs.
Only immutable Git blobs listed in the checked-in lock may be fetched.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'studio/production/sandbox-native-libs.lock.json'


def prepare(directory, fetch=False, accept_experimental=False):
    if fetch and not accept_experimental:
        raise ValueError('fetch requires --accept-experimental-mirror; this is not an approved production OS source')
    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT):
        raise ValueError('native directory must stay inside the repository workspace')
    records = json.loads(LOCK.read_text())['libraries']
    for record in records:
        if (record['source_repo'] != 'eXtern-OS/eXternOS-Base' or
                not re.fullmatch(r'[A-Za-z0-9_.-]+', record['file']) or
                not re.fullmatch(r'[0-9a-f]{40}', record['git_blob_sha1']) or
                not re.fullmatch(r'[0-9a-f]{64}', record['sha256'])):
            raise ValueError('invalid native lock entry')
        path = (directory / record['file']).resolve()
        if not path.is_relative_to(directory):
            raise ValueError('native file escapes directory')
        if path.exists():
            content = path.read_bytes()
        elif fetch:
            result = subprocess.run(['gh', 'api', f'repos/{record["source_repo"]}/git/blobs/{record["git_blob_sha1"]}'],
                                    capture_output=True, text=True, check=True, timeout=60)
            content = base64.b64decode(json.loads(result.stdout)['content'])
        else:
            raise ValueError(f'missing {record["file"]}; use OS packages or explicitly opt in to the sandbox experiment')
        git_sha = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
        if (not content.startswith(b'\x7fELF') or len(content) != record['bytes'] or
                hashlib.sha256(content).hexdigest() != record['sha256'] or git_sha != record['git_blob_sha1']):
            raise ValueError(f'integrity mismatch: {record["file"]}; existing files are not overwritten')
        if not path.exists():
            directory.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + '.tmp')
            temporary.write_bytes(content)
            temporary.replace(path)
        print(f'VERIFIED {record["file"]} {record["sha256"]}')
    if fetch:
        notices = json.loads((ROOT / 'studio/production/sandbox-native-notices.json').read_text())
        notice_path = (directory / 'THIRD_PARTY_NOTICES.txt').resolve()
        if not notice_path.is_relative_to(directory):
            raise ValueError('notice path escapes directory')
        text = 'EXPERIMENTAL SANDBOX LIBRARIES — NOT AN APPROVED PRODUCTION IMAGE\n\n'
        for notice in notices['notices']:
            body = notice['text']
            if hashlib.sha256(body.encode()).hexdigest() != notice['content_sha256']:
                raise ValueError('notice checksum mismatch')
            text += f'{notice["package"]}\nhttps://github.com/{notice["repo"]}/blob/{notice["revision"]}/{notice["path"]}\n\n{body}\n\n'
        notice_path.write_text(text)
    return len(records)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='.cache/blender-native')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--accept-experimental-mirror', action='store_true')
    args = parser.parse_args(argv)
    try:
        prepare(ROOT / args.directory, args.fetch, args.accept_experimental_mirror)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
