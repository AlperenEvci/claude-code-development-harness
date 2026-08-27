#!/usr/bin/env python3
"""Run the repository's isolated unittest cases concurrently.

Every test uses its own temporary directory, so process-level parallelism keeps the
release check fast while preserving normal unittest behavior and failure output.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Result:
    test_id: str
    returncode: int
    stdout: str
    stderr: str


def iter_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_cases(item)
        else:
            yield item


def run_case(test_id: str, timeout: int) -> Result:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", test_id],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return Result(test_id, completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return Result(test_id, 124, stdout, stderr + f"\nTIMEOUT after {timeout}s\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=int, default=90, help="Per-test timeout in seconds")
    args = parser.parse_args()

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    test_ids = sorted(case.id() for case in iter_cases(suite))
    if not test_ids:
        print("No tests discovered", file=sys.stderr)
        return 2

    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(run_case, test_id, args.timeout): test_id for test_id in test_ids}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            status = "PASS" if result.returncode == 0 else "FAIL"
            print(f"[{status}] {result.test_id}", flush=True)
            if result.returncode != 0:
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr)

    failures = [result for result in results if result.returncode != 0]
    print(f"\n{len(results) - len(failures)}/{len(results)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
