"""A stranger's submission, judged by a script instead of a conversation.

    python tools/check_submission.py                # every directory under submissions/
    python tools/check_submission.py submissions/x   # one submission

Why this exists: CONFORMANCE-PROGRAM.md said a submission contains a product
record, per-case results and an unedited log, and that verdicts must match the
frozen corpus. Until this file existed that was prose, which means the first
person to submit would have been judged by whoever read the PR first.

Rules:

  S1  a submission directory contains product.json, results.json, run.log
  S2  product.json declares legal_entity, implementation, version, language,
      repository, checks, contact, independence, submitted_at
  S3  independence is one of two words; 'independent' is refused when the legal
      entity is this organisation - the same rule the implementations manifest
      applies, because a self-submission is not a second opinion
  S4  corpus_digest equals the digest of FIXTURES.sha256 as committed here: a
      result set is tied to a corpus version, not to a date
  S5  results cover every frozen case exactly once, with a verdict that equals
      the expected one in tools/run_vectors.py; a submission may not re-score
      the corpus to its own advantage
  S6  run.log is at least 200 bytes and names at least three cases - a log that
      has been tidied into a summary is refused
  S7  checks must be a subset of S1-S19; claiming a check that does not exist is
      refused
  S8  competence_basis must be present and non-empty, or the literal 'none'.
      A reviewer of a software verification record asks who ran it and on what
      standing (MDR submission guidance asks for personnel competence for in-house
      testing, laboratory accreditation for third-party testing). Omitting the
      field is the failure this catches; 'none' is an acceptable, visible answer.
  S9  the 'witness' key must exist, even when its value is null. Null says "no
      witness"; a missing key says "we did not think about it". Only the keyword
      'independent' may be used when a witness is named, and it may not be used
      by this organisation.
  S10 every check id in S1-S19 must appear in exactly one of 'checks' or
      'scope.not_covered'. Silence about a check reads as coverage.

A submission is not certified by passing. Passing means the bytes it shipped
describe the same verdicts this corpus records, and that it has said out loud
which of the reviewer-required facts it does not have.
"""

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_vectors as rv  # noqa: E402 - the frozen expected verdicts

SUBMISSIONS = os.path.join(ROOT, "submissions")
KNOWN_CHECKS = {f"S{i}" for i in range(1, 20)}
LABELS = {"same-maintainer", "independent"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
VERDICTS = {"PASS", "FAIL", "INCONCLUSIVE"}

# case id -> expected verdict, derived from the gate itself so there is one table
EXPECTED = {}
for case, extra, _rc, want in rv.ROWS:
    key = case + ("|pinned" if extra else "|open")
    EXPECTED[key] = want


def corpus_digest():
    p = os.path.join(ROOT, "FIXTURES.sha256")
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def judge(path):
    problems = []
    # S1
    for name in ("product.json", "results.json", "run.log"):
        if not os.path.isfile(os.path.join(path, name)):
            problems.append(f"S1: missing {name}")
    if problems:
        return problems

    with open(os.path.join(path, "product.json"), encoding="utf-8") as fh:
        product = json.load(fh)
    with open(os.path.join(path, "results.json"), encoding="utf-8") as fh:
        results = json.load(fh)
    with open(os.path.join(path, "run.log"), encoding="utf-8", errors="replace") as fh:
        log = fh.read()

    # S2
    required = ["legal_entity", "implementation", "version", "language",
                "repository", "checks", "contact", "independence", "submitted_at"]
    missing = [k for k in required if not product.get(k)]
    if missing:
        problems.append(f"S2: product.json is missing {missing}")

    # S3
    label = product.get("independence")
    if label not in LABELS:
        problems.append(f"S3: independence='{label}' is not one of {sorted(LABELS)}")
    elif label == "independent" and str(product.get("legal_entity", "")).strip().lower() in {"uibc", "uibc org"}:
        problems.append("S3: 'independent' cannot be this organisation - a self-submission is not a second opinion")

    # S4
    claimed = str(results.get("corpus_digest", ""))
    actual = corpus_digest()
    if claimed != actual:
        problems.append(
            f"S4: corpus_digest {claimed[:12]}... does not match the corpus committed here "
            f"({actual[:12]}...) - results are tied to a corpus version, not to a claim")

    # S5
    rows = results.get("rows") or []
    seen = {}
    for r in rows:
        key = f"{r.get('case')}|{r.get('mode')}"
        if key in seen:
            problems.append(f"S5: case {key} appears twice")
        seen[key] = r.get("verdict")
    for key, want in EXPECTED.items():
        if key not in seen:
            problems.append(f"S5: {key} is missing from the submission")
        elif seen[key] not in VERDICTS:
            problems.append(f"S5: {key} has verdict {seen[key]!r}, not one of {sorted(VERDICTS)}")
        elif seen[key] != want:
            problems.append(f"S5: {key} claims {seen[key]} but the frozen corpus records {want}")
    for key in seen:
        if key not in EXPECTED:
            problems.append(f"S5: {key} is not a frozen case - a submission may not invent rows")

    # S6
    if len(log) < 200:
        problems.append(f"S6: run.log is {len(log)} bytes - too short to be an unedited run")
    named = sum(1 for key in EXPECTED if key.split("|")[0] in log)
    if named < 3:
        problems.append(f"S6: run.log names {named} case(s); an unedited log names the cases it ran")

    # S7
    checks = product.get("checks") or []
    unknown = [c for c in checks if c not in KNOWN_CHECKS]
    if unknown:
        problems.append(f"S7: checks {unknown} do not exist in S1-S19")

    # S8 - who ran it, and on what standing. Reviewers of a verification record
    # ask this before they ask whether it passed; a record that cannot answer it
    # is a narrative with numbers. 'none' is allowed on purpose: an honest
    # absence is checkable, an omission is not.
    basis = product.get("competence_basis")
    if not isinstance(basis, str) or not basis.strip():
        problems.append("S8: competence_basis is missing or empty - say who ran it and on "
                        "what standing, or write 'none'")
    elif basis.strip().lower() != "none" and len(basis.strip()) < 8:
        problems.append(f"S8: competence_basis='{basis}' is too short to identify a basis; "
                        "name the person, laboratory or accreditation, or write 'none'")

    # S9 - a witness must be either absent on purpose or named.
    if "witness" not in product:
        problems.append("S9: the 'witness' key is absent - use null to say there was none, "
                        "which is a different statement from not mentioning it")
    else:
        w = product["witness"]
        if w is not None:
            if not isinstance(w, dict) or not str(w.get("name", "")).strip():
                problems.append("S9: witness must be null or an object with a non-empty name")
            elif str(w.get("independent_of_submitter", "")).lower() not in {"true", "false"}:
                problems.append("S9: witness must state independent_of_submitter as true or false")
            elif str(w.get("independent_of_submitter")).lower() == "true" and \
                    str(product.get("legal_entity", "")).strip().lower() in {"uibc", "uibc org"}:
                problems.append("S9: a witness cannot be independent_of_submitter 'true' when "
                                "the submitter is this organisation and the witness is unnamed "
                                "by an outside body")

    # S10 - silence about a check reads as coverage.
    scope = product.get("scope") if isinstance(product.get("scope"), dict) else {}
    not_covered = scope.get("not_covered")
    if not isinstance(not_covered, list):
        problems.append("S10: scope.not_covered is missing - list the checks this submission "
                        "does not claim, even when the list is empty")
    else:
        closed = list(checks) + list(not_covered)
        bad = [c for c in closed if c not in KNOWN_CHECKS]
        for c in KNOWN_CHECKS:
            n = closed.count(c)
            if n == 0:
                problems.append(f"S10: check {c} is neither claimed nor listed as not covered")
            elif n > 1:
                problems.append(f"S10: check {c} appears {n} times across checks and not_covered")
        if bad:
            problems.append(f"S10: scope.not_covered names unknown checks {bad}")
    return problems


def selftest():
    """Break the format on purpose: every doctored submission must be refused.

    A validator that only ever sees good input is a formality. Each case below
    changes exactly one thing and names the rule that must catch it.
    """
    import shutil
    import tempfile

    src = os.path.join(SUBMISSIONS, "uibc-self-20261120")
    if not os.path.isdir(src):
        src = os.path.join(SUBMISSIONS, "uibc-self-20261124")
    cases = []

    def prep(tmp, name):
        d = os.path.join(tmp, name)
        shutil.copytree(src, d)
        return d

    def edit(d, rel, fn):
        p = os.path.join(d, rel)
        with open(p, encoding="utf-8") as fh:
            obj = json.load(fh)
        fn(obj)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)

    with tempfile.TemporaryDirectory() as tmp:
        # 1: re-score a row to the submission's advantage
        d = prep(tmp, "rescored")
        def rescore(o):
            for r in o["rows"]:
                if r["case"] == "keyswap" and r["mode"] == "open":
                    r["verdict"] = "FAIL"
        edit(d, "results.json", rescore)
        cases.append(("re-scored row", d, "S5"))

        # 2: results tied to a different corpus
        d = prep(tmp, "wrong-corpus")
        edit(d, "results.json", lambda o: o.update(corpus_digest="0" * 64))
        cases.append(("wrong corpus digest", d, "S4"))

        # 3: a frozen case quietly dropped
        d = prep(tmp, "missing-row")
        def drop(o):
            o["rows"] = [r for r in o["rows"] if r["case"] != "unsigned"]
        edit(d, "results.json", drop)
        cases.append(("missing case", d, "S5"))

        # 4: a self-submission labelled independent
        d = prep(tmp, "fake-independent")
        edit(d, "product.json", lambda o: o.update(independence="independent"))
        cases.append(("self-submission as independent", d, "S3"))

        # 5: a log tidied into a summary
        d = prep(tmp, "tidied-log")
        with open(os.path.join(d, "run.log"), "w", encoding="utf-8") as fh:
            fh.write("all eight rows passed\n")
        cases.append(("tidied log", d, "S6"))

        # 6: a check id that does not exist
        d = prep(tmp, "invented-check")
        edit(d, "product.json", lambda o: o.update(checks=["S99", "S1"]))
        cases.append(("invented check id", d, "S7"))

        # 7: competence silently omitted - the reviewer's first question
        d = prep(tmp, "no-competence")
        def drop_basis(o):
            o.pop("competence_basis", None)
        edit(d, "product.json", drop_basis)
        cases.append(("competence omitted", d, "S8"))

        # 8: witness key removed instead of set to null
        d = prep(tmp, "no-witness-key")
        def drop_witness(o):
            o.pop("witness", None)
        edit(d, "product.json", drop_witness)
        cases.append(("witness key omitted", d, "S9"))

        # 9: a check neither claimed nor disclaimed
        d = prep(tmp, "silent-scope")
        def shrink_scope(o):
            o["checks"] = [c for c in o["checks"] if c != "S19"]
            o["scope"] = {"not_covered": []}
        edit(d, "product.json", shrink_scope)
        cases.append(("check neither claimed nor disclaimed", d, "S10"))

        caught = 0
        for name, d, rule in cases:
            problems = judge(d)
            hit = any(p.startswith(rule) for p in problems)
            if hit:
                caught += 1
            print(f"[{'OK' if hit else 'MISSED'}] {name:<34} expected {rule}"
                  + ("" if hit else f"  got: {problems[:1]}"))

    if caught != len(cases):
        print(f"\nSUBMISSION SELFTEST FAILED - {caught}/{len(cases)} doctored submissions were caught.")
        return 1
    print(f"\nSUBMISSION SELFTEST OK - {caught}/{len(cases)} doctored submissions rejected.")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    target = sys.argv[1] if len(sys.argv) > 1 else SUBMISSIONS
    if not os.path.isdir(target):
        print(f"SUBMISSIONS: no directory at {target} - nothing to judge. This is not a pass.")
        return 0
    dirs = sorted(d for d in os.listdir(target)
                  if os.path.isdir(os.path.join(target, d)) and not d.startswith("."))
    if not dirs:
        print("SUBMISSIONS OK - 0 submission(s). An empty directory is a statement about us, not about the corpus.")
        return 0

    failures = 0
    for d in dirs:
        p = os.path.join(target, d)
        problems = judge(p)
        if problems:
            failures += 1
            print(f"[REJECTED] {d}")
            for x in problems:
                print(f"    !! {x}")
        else:
            print(f"[ACCEPTED] {d} - verdicts match the frozen corpus, corpus digest matches, log intact")

    if failures:
        print(f"\nSUBMISSIONS FAILED - {failures} of {len(dirs)} rejected.")
        print("A submission is judged against the corpus, not against the submitter.")
        return 1
    print(f"\nSUBMISSIONS OK - {len(dirs)} submission(s), all matched the frozen corpus.")
    print("Acceptance means the shipped bytes describe the same verdicts; it certifies nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
