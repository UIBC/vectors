"""The implementations manifest, checked instead of believed.

    python tools/check_implementations.py

Every correction below exists because a manifest is a place where a number can
be typed by hand and read as a result:

  R1  ids unique, 19 known check ids, an implementation must declare at least one
  R2  an independence label must be one of the two words the contract defines
  R3  'independent' from the maintainer's own address is refused - the label is
      checked against the repository/publisher, not trusted
  R4  every implementation in this file must appear in the recorded results,
      and the counts stated here must equal the counts in interop-results.json
  R5  results must show zero disagreements before any agreement number may be
      quoted; a manifest may not survive a failed run

The gate says nothing about whether an implementation is any good. It only
refuses a manifest that claims more than the run it points at.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "implementations.json")
RESULTS = os.path.join(ROOT, "interop-results.json")

KNOWN_CHECKS = {f"S{i}" for i in range(1, 20)}
LABELS = {"same-maintainer", "independent"}
ROLES = {"reference", "second-implementation", "public-corpus-replay",
         "external-verifier-benchmark", "external-implementation"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    problems = []
    m = load(MANIFEST)
    impls = m.get("implementations") or []
    if not impls:
        problems.append("R1: no implementations declared")

    owner_addr = (m.get("maintainer") or {}).get("org", "")
    owner_gh = (m.get("maintainer") or {}).get("github", "")

    ids = []
    for i in impls:
        ids.append(i.get("id"))
        checks = i.get("checks") or []
        unknown = [c for c in checks if c not in KNOWN_CHECKS]
        if not checks and not i.get("coverage_note"):
            problems.append(f"R1: {i.get('id')} declares no checks and no coverage note")
        if unknown:
            problems.append(f"R1: {i.get('id')} declares unknown check ids {unknown}")
        if i.get("role") not in ROLES:
            problems.append(f"R1: {i.get('id')} role='{i.get('role')}' is not one of {sorted(ROLES)}")
        if not str(i.get("evidence_source", "")).strip():
            problems.append(f"R1: {i.get('id')} names no evidence source - a row without a record is a claim")
        label = i.get("independence")
        if label not in LABELS:
            problems.append(f"R2: {i.get('id')} independence='{label}' is not one of {sorted(LABELS)}")
        if label == "independent":
            repo = str(i.get("repository", ""))
            if (owner_gh and owner_gh.lower() in repo.lower()) or (owner_addr and owner_addr.lower() in repo.lower()):
                problems.append(
                    f"R3: {i.get('id')} claims 'independent' but its repository is the "
                    f"maintainer's own address ({repo}). Same maintainer is 'same-maintainer'.")
    if len(set(ids)) != len(ids):
        problems.append("R1: duplicate implementation id")

    if not os.path.isfile(RESULTS):
        problems.append("R4: interop-results.json is missing - a manifest without a run is a wish")
        report = None
    else:
        report = load(RESULTS)

    if report is not None:
        recorded = {r.get("id") for r in report.get("implementations", [])}
        for i in impls:
            if i.get("scored_in_this_run") and i.get("id") not in recorded:
                problems.append(f"R4: {i.get('id')} is scored in this run but absent from interop-results.json")
            if not i.get("scored_in_this_run") and i.get("id") in recorded:
                problems.append(f"R4: {i.get('id')} says it is not scored here, but the run recorded it")
        v = report.get("verdict_agreement", {})
        c = report.get("check_agreement", {})
        ev = m.get("evidence", {})
        pairs = [
            ("rows", ev.get("rows"), v.get("rows")),
            ("verdicts_agree", ev.get("verdicts_agree"), v.get("agree")),
            ("check_comparisons", ev.get("check_comparisons"), c.get("compared")),
            ("checks_agree", ev.get("checks_agree"), c.get("agree")),
        ]
        for name, stated, actual in pairs:
            if stated != actual:
                problems.append(f"R4: evidence.{name}={stated} but the run recorded {actual}")
        if v.get("disagree"):
            problems.append(f"R5: the recorded run has {v.get('disagree')} disagreement(s); no agreement may be quoted")
        if c.get("compared") != c.get("agree"):
            problems.append(f"R5: {c.get('compared', 0) - c.get('agree', 0)} per-check disagreement(s) in the recorded run")
        if v.get("rows") != v.get("agree"):
            problems.append("R5: verdict counts do not agree with each other")

    if problems:
        print("IMPLEMENTATIONS GATE FAILED:")
        for p in problems:
            print(f"  !! {p}")
        return 1

    print(f"IMPLEMENTATIONS OK - {len(impls)} implementation(s), "
          f"{sum(1 for i in impls if i.get('independence') == 'independent')} independent, "
          f"{m['evidence']['verdicts_agree']}/{m['evidence']['rows']} verdicts agree, "
          f"{m['evidence']['checks_agree']}/{m['evidence']['check_comparisons']} per-check agree.")
    print("This gate refuses overclaims; it does not certify any product.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
