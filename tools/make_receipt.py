"""Run the six rows and write a receipt that someone else can check.

    python tools/make_receipt.py --runner "your handle" --blind yes|no --code independent|author

The receipt records what was observed, on which interpreter, and the SHA-256 of
every vector file it touched. It does not record that the run was honest - that
is what `tools/check_receipt.py` is for: it re-derives the hashes from this
repository and rejects a receipt whose bytes do not match.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "vectors")
OWNER_PUB = os.path.join(ROOT, "keys", "owner.key.pub")

ROWS = [
    ("clean", [], 0, "PASS"),
    ("clean", ["--pubkey", OWNER_PUB], 0, "PASS"),
    ("tampered", [], 1, "FAIL"),
    ("deleted", [], 1, "FAIL"),
    ("keyswap", [], 0, "PASS"),
    ("keyswap", ["--pubkey", OWNER_PUB], 1, "FAIL"),
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_case(case):
    """SHA-256 of every file under the case, in sorted relative-path order.

    `dirs.sort()` is required, not cosmetic: `os.walk` visits subdirectories in
    raw readdir order, which differs between NTFS and ext4. Without it the same
    bytes produce a different digest per platform, and a receipt made on one
    machine is rejected on the other.
    """
    entries = []
    base = os.path.join(VECTORS, case)
    for root, dirs, files in os.walk(base):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            entries.append(f"{rel}={sha256_file(full)}")
    joined = "\n".join(entries).encode()
    return {"files": len(entries), "case_digest": hashlib.sha256(joined).hexdigest()}


def run_row(case, extra):
    cmd = [sys.executable, "-m", "uibc_core.cli", "verify", os.path.join(VECTORS, case), *extra]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    result = None
    try:
        result = json.loads(p.stdout).get("result")
    except Exception:
        for line in p.stdout.splitlines():
            if '"result"' in line:
                result = line.split('"')[3]
                break
    return {"case": case, "mode": "pinned" if extra else "open",
            "rc": p.returncode, "result": result}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", required=True, help="who ran it (handle or name)")
    ap.add_argument("--blind", choices=["yes", "no"], default="no",
                    help="were the expected verdicts hidden from you before the run?")
    ap.add_argument("--code", choices=["independent", "author"], default="independent",
                    help="did you write the code you ran, or take it from this repo?")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    try:
        from importlib.metadata import version
        core_version = version("uibc-core")
    except Exception:
        core_version = "unknown"

    rows = [run_row(c, e) for c, e, _rc, _res in ROWS]
    expected = [{"case": c, "mode": "pinned" if e else "open", "rc": rc, "result": res}
                for c, e, rc, res in ROWS]
    matched = all(r == x for r, x in zip(rows, expected))

    receipt = {
        "schema": "uibc-receipt/1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runner": {"handle": args.runner, "blind": args.blind, "code": args.code},
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "uibc_core": core_version,
        },
        "vectors": {c: digest_case(c) for c, _e, _r, _s in ROWS},
        "observed": rows,
        "matches_repo_expectation": matched,
        "limits": [
            "Self-reported identity: this file proves a run happened, not who ran it.",
            "The expectation table was visible in EXPECTED.md unless --blind yes was honestly answered.",
        ],
    }

    out = args.out or os.path.join(ROOT, "receipts",
                                  f"{receipt['generated_at'][:10]}-{args.runner.replace(' ', '_')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    print(f"receipt written: {out}")
    print(f"matches repo expectation: {matched}")
    return 0 if matched else 1


if __name__ == "__main__":
    sys.exit(main())
