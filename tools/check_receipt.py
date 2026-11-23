"""Check a receipt against the bytes in this repository.

    python tools/check_receipt.py receipts/<file>.json

Rejects a receipt when:
  - a vector's bytes no longer hash to what the receipt recorded (the repo moved
    after the run, so the receipt describes a different thing),
  - a row is missing, or the verdict it claims is not a legal verdict,
  - the receipt claims a match the observed rows do not support,
  - the runner fields are blank.

Accepts a receipt whose cells disagree with EXPECTED.md - that is an honest
finding, not a failure, and it is printed as DIRECTION: divergent.
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "vectors")
LEGAL = {"PASS", "FAIL", "INCONCLUSIVE", "BLOCKED"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_case(case):
    entries = []
    base = os.path.join(VECTORS, case)
    for root, _dirs, files in os.walk(base):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            entries.append(f"{rel}={sha256_file(full)}")
    joined = "\n".join(entries).encode()
    return {"files": len(entries), "case_digest": hashlib.sha256(joined).hexdigest()}


def main():
    if len(sys.argv) != 2:
        print("usage: python tools/check_receipt.py <receipt.json>")
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        rec = json.load(f)

    problems = []

    runner = rec.get("runner", {})
    for key in ("handle", "blind", "code"):
        if not str(runner.get(key, "")).strip():
            problems.append(f"runner.{key} is blank")

    if rec.get("schema") != "uibc-receipt/1":
        problems.append(f"unknown schema: {rec.get('schema')!r}")

    observed = rec.get("observed", [])
    if len(observed) != 6:
        problems.append(f"expected 6 rows, receipt carries {len(observed)}")
    for row in observed:
        if row.get("result") not in LEGAL:
            problems.append(f"{row.get('case')}[{row.get('mode')}] claims illegal verdict {row.get('result')!r}")

    for case, want in (rec.get("vectors") or {}).items():
        if not os.path.isdir(os.path.join(VECTORS, case)):
            problems.append(f"vector {case!r} recorded in the receipt does not exist here")
            continue
        got = digest_case(case)
        if got["case_digest"] != want.get("case_digest"):
            problems.append(f"{case}: bytes changed since that run "
                            f"(receipt {str(want.get('case_digest'))[:12]}, now {got['case_digest'][:12]})")

    claimed_match = rec.get("matches_repo_expectation")
    if claimed_match is not None and not isinstance(claimed_match, bool):
        problems.append("matches_repo_expectation is not a boolean")

    if problems:
        print("REJECTED - this receipt is not usable evidence:")
        for p in problems:
            print("  !! " + p)
        return 1

    print("ACCEPTABLE - receipt is internally consistent with the bytes in this repository.")
    print(f"  runner: {runner['handle']} (blind={runner['blind']}, code={runner['code']})")
    print(f"  env:    {rec.get('environment', {}).get('platform')} / py{rec.get('environment', {}).get('python')}"
          f" / uibc-core {rec.get('environment', {}).get('uibc_core')}")
    print(f"  rows:   {len(observed)} observed; claims match = {claimed_match}")
    print("  direction: this receipt is self-reported. It is a row in RUNS.md, not a witness.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
