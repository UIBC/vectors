"""Adversarial supplement: doctored packages that must not come back PASS.

    python tools/run_adversarial.py            # documented gaps are reported, not hidden
    python tools/run_adversarial.py --strict   # any documented gap fails the run

Separate from the frozen eight-row matrix on purpose: the matrix pins what *is*
the case; this pins what *breaks* a verdict. Cases are built at run time from
`vectors/clean`, so nothing here changes committed bytes.

Two groups:

  MUST-REJECT  the verifier must answer FAIL or INCONCLUSIVE (never PASS)
  KNOWN-GAP    a genuine gap we found in the reference verifier, recorded with a
               defect id, printed loudly, and required to still reproduce. A gap
               that disappears makes the run red until someone moves the case
               and updates the ledger - so the list cannot rot.

Pass criterion: every MUST-REJECT row is rejected, and every KNOWN-GAP row still
behaves exactly as the ledger says. --strict additionally requires KNOWN-GAP rows
to be rejected, so a fix can be proven.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "vectors", "clean")

# defect D-002: S7 index-metadata digest covers path/content_hash/type/note but
# NOT evidence_id, media_type or created_at. Verified 2026-11-24: those three
# fields can be rewritten in evidence/index.json and the verdict stays PASS.
D002 = "D-002 (S7 digest does not cover this field)"

KNOWN_GAPS = {
    "index-metadata-drift": D002,
    "evidence-id-drift": D002,
    "media-type-drift": D002,
}


def _read(d, rel):
    p = os.path.join(d, rel)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _write(d, rel, obj):
    p = os.path.join(d, rel)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def mutate_dup_member(d):
    p = os.path.join(d, "identity.json")
    with open(p, "rb") as fh:
        b = fh.read()
    b = b.replace(b"{\n", b'{\n  "agent_id": "vec-agent-666",\n', 1)
    with open(p, "wb") as fh:
        fh.write(b)


def mutate_control_char(d):
    p = os.path.join(d, "identity.json")
    with open(p, "rb") as fh:
        b = fh.read()
    b = b.replace(b'"vec-agent-001"', b'"vec-agent-001\x01"', 1)
    with open(p, "wb") as fh:
        fh.write(b)


def mutate_extra_root_file(d):
    with open(os.path.join(d, "unexpected.txt"), "w", encoding="utf-8") as fh:
        fh.write("undeclared file at package root\n")


def mutate_path_escape(d):
    idx = _read(d, os.path.join("evidence", "index.json"))
    idx["entries"][0]["path"] = "../escape/report.txt"
    _write(d, os.path.join("evidence", "index.json"), idx)


def mutate_hash_flip(d):
    p = os.path.join(d, "evidence", "files", "report.txt")
    with open(p, "ab") as fh:
        fh.write(b"x")


def mutate_ts_rollback(d):
    lc = _read(d, "lifecycle.json")
    lc["events"][0]["timestamp"] = "2026-11-23T15:36:56Z"
    lc["events"][1]["timestamp"] = "2026-11-22T00:00:00Z"
    _write(d, "lifecycle.json", lc)


def mutate_seq_gap(d):
    lc = _read(d, "lifecycle.json")
    lc["events"][1]["sequence_number"] = 3
    _write(d, "lifecycle.json", lc)


def mutate_unsigned(d):
    os.remove(os.path.join(d, "signatures", "seal.json"))


def mutate_status_upgrade(d):
    mutate_unsigned(d)
    p = os.path.join(d, "manifest.json")
    with open(p, "rb") as fh:
        b = fh.read()
    b = b.replace(b'"status": "SUBMITTED"', b'"status": "PASS"')
    with open(p, "wb") as fh:
        fh.write(b)


def mutate_index_created_at(d):
    idx = _read(d, os.path.join("evidence", "index.json"))
    idx["entries"][0]["created_at"] = "2026-11-24T00:00:00Z"
    _write(d, os.path.join("evidence", "index.json"), idx)


def mutate_index_evidence_id(d):
    idx = _read(d, os.path.join("evidence", "index.json"))
    idx["entries"][0]["evidence_id"] = "11111111-1111-4111-8111-111111111111"
    _write(d, os.path.join("evidence", "index.json"), idx)


def mutate_index_media_type(d):
    idx = _read(d, os.path.join("evidence", "index.json"))
    idx["entries"][0]["media_type"] = "application/octet-stream"
    _write(d, os.path.join("evidence", "index.json"), idx)


CASES = [
    ("dup-json-member", mutate_dup_member, "S11 duplicate member name"),
    ("control-char", mutate_control_char, "S11 raw control character"),
    ("extra-root-file", mutate_extra_root_file, "S1 undeclared root entry"),
    ("index-path-escape", mutate_path_escape, "S1/S4 path leaves evidence dir"),
    ("hash-flip", mutate_hash_flip, "S4 one byte appended after sealing"),
    ("ts-rollback", mutate_ts_rollback, "S3 non-monotonic timestamps"),
    ("seq-gap", mutate_seq_gap, "S3 sequence not contiguous"),
    ("unsigned", mutate_unsigned, "S6 no seal -> INCONCLUSIVE, never PASS"),
    ("status-upgrade", mutate_status_upgrade, "self-declared PASS cannot upgrade"),
    # documented gaps: these three are NOT caught today
    ("index-metadata-drift", mutate_index_created_at, "created_at rewritten"),
    ("evidence-id-drift", mutate_index_evidence_id, "evidence_id rewritten"),
    ("media-type-drift", mutate_index_media_type, "media_type rewritten"),
]


def verify(path):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, "-m", "uibc_core.cli", "verify", path],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    result = None
    try:
        result = json.loads(p.stdout).get("result")
    except Exception:
        for line in p.stdout.splitlines():
            if '"result"' in line:
                result = line.split('"')[3]
                break
    return p.returncode, result


def tree_digest(d):
    h = hashlib.sha256()
    for root, _dirs, names in os.walk(d):
        for n in sorted(names):
            p = os.path.join(root, n)
            h.update(os.path.relpath(p, d).replace(os.sep, "/").encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="treat documented gaps as failures (use after a fix)")
    a = ap.parse_args()

    problems = []
    gaps_seen = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn, why in CASES:
            d = os.path.join(tmp, name)
            shutil.copytree(CLEAN, d)
            fn(d)
            rc, result = verify(d)
            dig = tree_digest(d)
            if name in KNOWN_GAPS:
                gaps_seen += 1
                documented = (result == "PASS" and rc == 0)
                label = "DEFECT" if documented else "STALE"
                print("[%s] %-22s rc=%s result=%-13s %s | %s" %
                      (label, name, rc, result, why, KNOWN_GAPS[name]))
                if documented and a.strict:
                    problems.append((name, rc, result, "known gap not yet fixed"))
                if not documented:
                    problems.append((name, rc, result, "gap no longer reproduces: move it to MUST-REJECT"))
            else:
                ok = result != "PASS" and rc == 1
                print("[%s] %-22s rc=%s result=%-13s %s" %
                      ("OK" if ok else "MISMATCH", name, rc, result, why))
                if not ok:
                    problems.append((name, rc, result, "expected rejection"))
            print("      case-digest=%s" % dig)

    total = len(CASES)
    if problems:
        print("\nADVERSARIAL FAILED - %d problem(s) over %d cases:" % (len(problems), total))
        for name, rc, result, msg in problems:
            print("  !! %-22s rc=%s result=%s - %s" % (name, rc, result, msg))
        return 1

    strict = " (strict: known gaps count as failures)" if a.strict else ""
    print("\nADVERSARIAL OK - %d/%d must-reject cases rejected; %d documented gap(s) still reproduce%s."
          % (total - gaps_seen, total - gaps_seen, gaps_seen, strict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
