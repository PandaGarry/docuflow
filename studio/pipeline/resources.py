"""Sampled process-group RSS/timeout guard for trusted workers, not a sandbox."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import os
import math
from pathlib import Path
import signal
import subprocess
import time

import psutil
from .contracts import ContractError


class WorkerError(ContractError):
    pass


@dataclass
class ProcessResult:
    pid: int
    exit_code: int
    wall_seconds: float
    observed_peak_rss_bytes: int

    def to_dict(self):
        return asdict(self)


def effective_threads(requested):
    if type(requested) is not int or requested < 1:
        raise ContractError('positive integer thread count required')
    available = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)
    return min(requested, available)


def chunks(start, end, size):
    if any(type(x) is not int for x in (start, end, size)) or not 0 <= start < end or size < 1:
        raise ContractError('invalid chunk range')
    return [(f, min(f+size, end)) for f in range(start, end, size)]


def _terminate_group(proc):
    # Unix process group includes descendants even if the root exits first.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run_guarded(command, log_path, *, cwd, env=None, rss_limit_mb, timeout_seconds, interval=.05):
    if (any(type(x) not in (int, float) or not math.isfinite(x) for x in (rss_limit_mb, timeout_seconds, interval))
            or rss_limit_mb <= 0 or timeout_seconds <= 0 or not 0 < interval <= 1):
        raise ContractError('invalid resource budget')
    limit = int(rss_limit_mb * 1024 * 1024)
    started, peak = time.monotonic(), 0
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(log_path).open('wb') as log:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            root = psutil.Process(proc.pid)
            while True:
                if time.monotonic() - started > timeout_seconds:
                    raise WorkerError(f'worker timeout exceeded: {timeout_seconds}s')
                rss = 0
                try:
                    members = [root, *root.children(recursive=True)]
                except psutil.NoSuchProcess:
                    members = []
                for member in members:
                    try:
                        rss += member.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak = max(peak, rss)
                if rss > limit:
                    raise WorkerError(f'worker RSS limit exceeded: {rss} > {limit} bytes')
                code = proc.poll()
                if code is not None:
                    if code != 0:
                        raise WorkerError(f'worker exited {code}; see {log_path}')
                    return ProcessResult(proc.pid, code, round(time.monotonic()-started, 4), peak)
                time.sleep(interval)
        finally:
            _terminate_group(proc)
