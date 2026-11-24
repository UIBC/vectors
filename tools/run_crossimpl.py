"""Cross-implementation replay: does a stranger's code reach the same verdicts?

    python tools/run_crossimpl.py            # writes interop-results.json
    python tools/run_crossimpl.py --json     # machine output on stdout too

What this proves, and what it does not
--------------------------------------
It proves that the byte-level rules (RFC 8785 canonicalization, sha256 roots,
Ed25519 seals, strict JSON scanning) are stated precisely enough that a
different language, zero dependencies, no shared code, lands on the same
verdict for 20 cases - the 8 frozen matrix rows plus the 12 adversarial
packages.

It does NOT prove independence: second-impl/verify.mjs is written by the same
maintainer. Independence needs a different maintainer; implementations.json is
where that claim is recorded and where a third entry would go. Both statements
are printed at the end of every run, because a run that only says "agree" is a
claim doing the work of evidence.

A disagreement is never smoothed over: the row is printed, the differing checks
are named, and the run exits 1.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_vectors as rv  # noqa: E402  - the 8 frozen rows
import run_adversarial as ra  # noqa: E402  - the adversarial packages

VECTORS = os.path.join(ROOT, "vectors")
NODE_IMPL = os.path.join(ROOT, "second-impl", "verify.mjs")
OWNER_PUB = os.path.join(ROOT, "keys", "owner.key.pub")

# checks the second implementation claims to cover; everything else is out of
# its declared scope and must not be scored as agreement.
SECOND_IMPL_SCOPE = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S11", "S12"]


def reference_verify(path, extra):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "-m", "uibc_core.cli", "verify", path, *extra]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    try:
        report = json.loads(p.stdout)
    except Exception:
        report = {}
    checks = {c["id"]: c["result"] for c in report.get("checks", []) if "id" in c}
    return p.returncode, report.get("result"), checks


def second_verify(path, extra):
    cmd = ["node", NODE_IMPL, path, "--json"]
    if "--pubkey" in extra:
        cmd += ["--pubkey", extra[extra.index("--pubkey") + 1]]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        report = json.loads(p.stdout)
    except Exception:
        return p.returncode, None, {}, p.stderr.strip()
    checks = {c["id"]: c["result"] for c in report.get("checks", [])}
    return p.returncode, report.get("result"), checks, p.stderr.strip()


def build_rows(tmp):
    rows = []
    # 1) frozen matrix rows, exactly as run_vectors declares them
    for case, extra, want_rc, want_result in rv.ROWS:
        path = os.path.join(VECTORS, case)
        label = case + ("" if not extra else " " + " ".join(os.path.basename(e) if e == OWNER_PUB else e for e in extra))
        rows.append({"id": label, "group": "matrix", "kind": case,
                     "mode": "pinned" if extra else "open", "path": path,
                     "extra": list(extra), "expected": want_result})
    # 2) adversarial packages, built fresh from vectors/clean
    for name, fn, why in ra.CASES:
        d = os.path.join(tmp, name)
        shutil.copytree(os.path.join(VECTORS, "clean"), d)
        fn(d)
        rows.append({"id": name, "group": "adversarial", "kind": name,
                     "mode": "open", "path": d, "extra": [],
                     "why": why,
                     "expected": "PASS" if name in ra.KNOWN_GAPS else "must not PASS"})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out_rows = []
    mismatches = []
    check_disagreements = []
    with tempfile.TemporaryDirectory() as tmp:
        for row in build_rows(tmp):
            rc1, res1, chk1 = reference_verify(row["path"], row["extra"])
            rc2, res2, chk2, err2 = second_verify(row["path"], row["extra"])
            agree = res1 == res2
            # per-check agreement, restricted to the second implementation's scope
            per = {}
            for cid in SECOND_IMPL_SCOPE:
                if cid in chk1 and cid in chk2:
                    per[cid] = chk1[cid] == chk2[cid]
                    if not per[cid]:
                        check_disagreements.append((row["id"], cid, chk1[cid], chk2[cid]))
            print(f"[{'AGREE' if agree else 'DISAGREE'}] {row['id']:<26} "
                  f"reference={res1} second-impl={res2} rc={rc1}/{rc2}")
            out_rows.append({
                "id": row["id"], "group": row["group"], "mode": row["mode"],
                "expected": row["expected"],
                "reference": {"impl": "uibc-core-verifier", "result": res1, "rc": rc1},
                "second_impl": {"impl": "uibc-js/0.1", "result": res2, "rc": rc2},
                "agree": agree, "per_check_agree": per,
            })
            if not agree:
                mismatches.append((row["id"], res1, res2, err2))

    agree_n = sum(1 for r in out_rows if r["agree"])
    per_n = sum(len(r["per_check_agree"]) for r in out_rows)
    per_ok = sum(1 for r in out_rows for v in r["per_check_agree"].values() if v)

    report = {
        "contract_version": "uibc-interop-results/1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus": {"vector_set": "UIBC/vectors", "fixtures": 6, "cases": len(out_rows)},
        "implementations": [
            {"id": "uibc-core-verifier", "language": "Python", "role": "reference",
             "independence": "same-maintainer", "scope": "S1-S19"},
            {"id": "uibc-js/0.1", "language": "JavaScript (Node 22)", "role": "second-implementation",
             "independence": "same-maintainer", "scope": ",".join(SECOND_IMPL_SCOPE)},
        ],
        "verdict_agreement": {"rows": len(out_rows), "agree": agree_n, "disagree": len(mismatches)},
        "check_agreement": {"compared": per_n, "agree": per_ok},
        "rows": out_rows,
        "not_proven_by_this_file": [
            "independence of the second implementation (same maintainer)",
            "checks S9, S10, S13-S19 are outside the second implementation's declared scope",
            "any real-world package beyond the committed fixtures",
        ],
    }
    with open(os.path.join(ROOT, "interop-results.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print()
    if mismatches:
        print(f"CROSSIMPL FAILED - {len(mismatches)} of {len(out_rows)} rows disagree:")
        for cid, a, b, err in mismatches:
            print(f"  !! {cid}: reference={a} second-impl={b}")
            if err:
                print(f"     node stderr: {err.splitlines()[-1]}")
        print("Either the spec is ambiguous or one implementation is wrong. Both are findings.")
        return 1
    if check_disagreements:
        print(f"CROSSIMPL FAILED - {len(check_disagreements)} per-check disagreement(s):")
        for cid, check, a, b in check_disagreements:
            print(f"  !! {cid} / {check}: reference={a} second-impl={b}")
        return 1

    print(f"CROSSIMPL OK - {agree_n}/{len(out_rows)} verdicts agree; "
          f"{per_ok}/{per_n} per-check results agree across {len(SECOND_IMPL_SCOPE)} checks.")
    print("Scope: second-impl/verify.mjs is a same-maintainer implementation - cross-language, "
          "not independent. Independence requires a different maintainer (implementations.json).")
    print("Written: interop-results.json")
    if args.json:
        print(json.dumps(report["verdict_agreement"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
