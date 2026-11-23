"""The gate: five assertions that must hold, or this run is not evidence.

    python tools/run_vectors.py

Each assertion is a (case, mode, expected) row. A row that does not match is
printed and the process exits 1 - a vector set that "mostly" holds is worth
nothing, because the one cell that drifted is the one that matters.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "vectors")
OWNER_PUB = os.path.join(ROOT, "keys", "owner.key.pub")

ROWS = [
    # (case, extra args, expected exit code, expected result)
    ("clean",    [],                                      0, "PASS"),
    ("clean",    ["--pubkey", OWNER_PUB],                  0, "PASS"),
    ("tampered", [],                                       1, "FAIL"),
    ("deleted",  [],                                       1, "FAIL"),
    # documented boundary: a full re-seal by another key verifies against itself,
    # and is only caught when the verifier pins the owner's public key.
    ("keyswap",  [],                                       0, "PASS"),
    ("keyswap",  ["--pubkey", OWNER_PUB],                  1, "FAIL"),
]


def verify(case, extra):
    path = os.path.join(VECTORS, case)
    cmd = [sys.executable, "-m", "uibc_core.cli", "verify", path, *extra]
    p = subprocess.run(cmd, capture_output=True, text=True)
    result = None
    try:
        result = json.loads(p.stdout).get("result")
    except Exception:
        for line in p.stdout.splitlines():
            if '"result"' in line:
                result = line.split('"')[3]
                break
    return p.returncode, result, p.stdout, p.stderr


def main():
    failures = []
    for case, extra, want_rc, want_result in ROWS:
        rc, result, out, err = verify(case, extra)
        label = f"{case}{' ' + ' '.join(extra) if extra else ''}"
        ok = (rc == want_rc and result == want_result)
        print(f"[{'OK' if ok else 'MISMATCH'}] {label:<28} rc={rc} result={result} "
              f"(expected rc={want_rc} result={want_result})")
        if not ok:
            failures.append((label, rc, result, want_rc, want_result, err.strip()))

    if failures:
        print(f"\nMATRIX GATE FAILED - {len(failures)} of {len(ROWS)} rows deviated:")
        for label, rc, result, want_rc, want_result, err in failures:
            print(f"  !! {label}: got rc={rc} result={result}, expected rc={want_rc} result={want_result}")
            if err:
                print(f"     stderr: {err.splitlines()[-1]}")
        print("A vector set whose cells drift is not evidence. Fix the vectors or the verifier.")
        return 1

    print(f"\nMATRIX GATE OK - all {len(ROWS)} rows match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
