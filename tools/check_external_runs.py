"""Check the ledger of runs done by people who are not us.

    python tools/check_external_runs.py
    python tools/check_external_runs.py --selftest   # the rules, proven on doctored ledgers

The claim "no external run has been done" is cheap to make and impossible to
dispute, which is why it survived twenty rounds of this repository. This file
makes the number a derived quantity: `registry/external-runs.json` holds one
record per run somebody else performed, and the headline count must equal the
number of records that pass every rule below. If the count and the records
disagree, the gate fails - so the number cannot be typed in, only earned.

Rules per record:

  E1  the record carries the contract, an id, a runner, a date, a verifier
      version, an os, and a corpus_digest
  E2  `corpus_digest` equals this repository's FIXTURES.sha256 digest: a run
      against a different corpus is a run against a different corpus
  E3  `log_path` exists and its SHA-256 equals `log_sha256` in the record -
      a record whose log cannot be produced is a claim, not a record
  E4  the log is not byte-identical to our own `submissions/*/run.log`. A
      re-run that reproduces our bytes exactly is our log with a new filename;
      a real run on another machine differs in path, timing and interpreter
  E5  `gates` is a non-empty list, each entry a name and a boolean, and a
      record whose gates all pass is "verified"; anything else is a published
      failure that stays in the ledger and does not raise the headline
  E6  `headline_verified` equals the number of verified records. A failure is
      published as a failure; it is not deleted and it does not raise the count

Exit 1 on any violation. Exit 0 with `EXTERNAL RUNS OK - 0 verified ...` when
the ledger is empty and honest, which is the current state.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER_REL = os.path.join("registry", "external-runs.json")
CONTRACT = "uibc-external-runs/1"
REQUIRED = ("id", "runner", "date", "verifier_version", "os", "corpus_digest",
            "independent_of_maintainer", "gates", "log_path", "log_sha256")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus_digest(root=ROOT):
    with open(os.path.join(root, "FIXTURES.sha256"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def our_logs(root=ROOT):
    out = set()
    base = os.path.join(root, "submissions")
    if not os.path.isdir(base):
        return out
    for name in os.listdir(base):
        p = os.path.join(base, name, "run.log")
        if os.path.isfile(p):
            out.add(sha256_file(p))
    return out


def audit(doc, root=ROOT):
    """Return (problems, verified, failed_runs, total)."""
    problems = []
    if doc.get("contract") != CONTRACT:
        problems.append(f"ledger contract is {doc.get('contract')!r}, not {CONTRACT!r}")
    digest = corpus_digest(root)
    ours = our_logs(root)
    entries = doc.get("entries")
    if not isinstance(entries, list):
        problems.append("ledger has no entries list")
        entries = []

    verified = failed = 0
    seen = set()
    for i, e in enumerate(entries):
        label = e.get("id") or f"entry #{i}"
        missing = [k for k in REQUIRED if k not in e]
        if missing:
            problems.append(f"E1: {label} is missing {', '.join(missing)}")
            continue
        if label in seen:
            problems.append(f"E1: {label} appears twice")
        seen.add(label)
        if e["corpus_digest"] != digest:
            problems.append(
                f"E2: {label} ran against corpus {str(e['corpus_digest'])[:12]}..., "
                f"this repository is {digest[:12]}...")
            continue
        log_path = os.path.join(root, str(e["log_path"]).replace("/", os.sep))
        if not os.path.isfile(log_path):
            problems.append(f"E3: {label} names {e['log_path']}, which is not in the repository")
            continue
        actual = sha256_file(log_path)
        if actual != e["log_sha256"]:
            problems.append(f"E3: {label} log digest is {actual[:12]}..., record says "
                            f"{str(e['log_sha256'])[:12]}...")
            continue
        if actual in ours:
            problems.append(f"E4: {label} log is byte-identical to our own submission log - "
                            f"a re-run on another machine does not produce these bytes")
            continue
        gates = e["gates"]
        if not isinstance(gates, list) or not gates:
            problems.append(f"E5: {label} records no gates; a run that shows nothing is not a run")
            continue
        if not all(isinstance(g, dict) and isinstance(g.get("ok"), bool) for g in gates):
            problems.append(f"E5: {label} has a gate that is not {name, ok-bool}")
            continue
        if all(g["ok"] for g in gates):
            verified += 1
        else:
            failed += 1

    headline = doc.get("headline_verified")
    if headline != verified:
        problems.append(
            f"E6: headline_verified says {headline!r}, the records support {verified}. "
            f"The number is derived; typing it is the defect this rule exists for.")
    return problems, verified, failed, len(entries)


def selftest():
    """Prove the rules by trying to satisfy the headline dishonestly."""
    keep = tempfile.mkdtemp()
    shadow = os.path.join(keep, "repo")
    os.makedirs(os.path.join(shadow, "registry"))
    os.makedirs(os.path.join(shadow, "submissions", "self"))
    os.makedirs(os.path.join(shadow, "logs"))
    shutil.copy(os.path.join(ROOT, "FIXTURES.sha256"), shadow)
    our_log = os.path.join(shadow, "submissions", "self", "run.log")
    with open(our_log, "w", encoding="utf-8") as fh:
        fh.write("[OK] clean rc=0 result=PASS\nSTRANGER OK - every gate that ran matched\n")

    def ledger(entries, headline):
        return {"contract": CONTRACT, "headline_verified": headline, "entries": entries}

    def run_log(name, body):
        p = os.path.join(shadow, "logs", name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return "logs/" + name, sha256_file(p)

    def entry(eid, log_rel, log_sha, gates=None, digest=None):
        return {"id": eid, "runner": "R. Reviewer", "date": "2026-11-25",
                "verifier_version": "0.5.0", "os": "linux", "python": "3.12",
                "independent_of_maintainer": True,
                "corpus_digest": digest or corpus_digest(shadow),
                "gates": gates or [{"name": "stranger", "ok": True}],
                "log_path": log_rel, "log_sha256": log_sha, "note": ""}

    good_rel, good_sha = run_log("good.log",
                                 "STRANGER OK - every gate that ran matched\n"
                                 "python: /home/reviewer/venv/bin/python\n")
    cases = []

    # control: an honest record is accepted
    cases.append(("an honest record", ledger([entry("rev-1", good_rel, good_sha)], 1), True))
    # C1: headline typed up without a record
    cases.append(("headline without a record", ledger([], 3), False))
    # C2: a record whose log is absent
    cases.append(("record with no log",
                  ledger([entry("rev-2", "logs/missing.log", "0" * 64)], 1), False))
    # C3: a log that has been edited after the digest was recorded
    cases.append(("log edited after the digest",
                  ledger([entry("rev-3", good_rel, "f" * 64)], 1), False))
    # C4: our own log renamed as somebody else's run
    cases.append(("our log with a new filename",
                  ledger([entry("rev-4", "submissions/self/run.log",
                                sha256_file(our_log))], 1), False))
    # C5: a run against a different corpus
    cases.append(("run against another corpus",
                  ledger([entry("rev-5", good_rel, good_sha, digest="a" * 64)], 1), False))
    # C6: a failing run that raises the headline anyway
    cases.append(("failure counted as verified",
                  ledger([entry("rev-6", good_rel, good_sha,
                                gates=[{"name": "stranger", "ok": False}])], 1), False))

    bad = []
    for label, doc, must_pass in cases:
        problems, verified, failed, total = audit(doc, shadow)
        ok = not problems
        if ok != must_pass:
            bad.append((label, problems, must_pass))
        print(f"[{'OK' if ok == must_pass else 'MISSED'}] {label:<32} "
              f"problems={len(problems)} expected_{'accept' if must_pass else 'reject'}")

    shutil.rmtree(keep, ignore_errors=True)
    if bad:
        print(f"\nEXTERNAL RUNS SELFTEST FAILED - {len(bad)} of {len(cases)} cases wrong:")
        for label, problems, must_pass in bad:
            print(f"  !! {label}: expected {'accept' if must_pass else 'reject'}, got "
                  f"{'accept' if not problems else 'reject'} ({'; '.join(problems)[:150]})")
        return 1
    print(f"\nEXTERNAL RUNS SELFTEST OK - {len(cases)} ledger(s) judged as expected; "
          f"the headline is refused when it is typed.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    path = os.path.join(ROOT, LEDGER_REL)
    if not os.path.isfile(path):
        print("EXTERNAL RUNS FAILED - registry/external-runs.json is missing. An "
              "absent ledger reads as an absent gap.")
        return 1
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    problems, verified, failed, total = audit(doc)
    if problems:
        print(f"EXTERNAL RUNS FAILED - {len(problems)} problem(s):")
        for p in problems:
            print(f"  !! {p}")
        return 1
    print(f"EXTERNAL RUNS OK - {verified} verified record(s), {failed} published "
          f"failure(s), {total} total; headline is derived from the records, not typed.")
    if verified == 0:
        print("Zero is the honest number today: nobody outside this repository has "
              "returned a run. tools/make_repro_request.py builds the pack to ask "
              "with; sending it is a maintainer action, not a tool's.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
