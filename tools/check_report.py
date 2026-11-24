"""Check someone's *claim*, not just their package.

    python tools/check_report.py receipts/x.json [--package <dir>]
    python tools/check_report.py --selftest

A verifier report is data, and data can be edited after the run. The rules below
are the ones a reader would apply before quoting a PASS:

  R1  result=PASS while any check is FAIL or INCONCLUSIVE        -> OVERCLAIM
  R2  assurance="attested" while check S6 is not PASS            -> OVERCLAIM
  R3  trust_level in {anchored, witnessed} while S6 is not PASS  -> OVERCLAIM
  R4  (--package) manifest.status claims PASS/APPROVED while the
      report result is not PASS                                  -> DECLARED OVERRIDE

--selftest builds four doctored reports plus one honest one and requires the
four to be rejected and the honest one to be accepted. A checker that accepts
everything fails its own negative control.
"""

import argparse
import json
import os
import sys

PASSY = {"PASS", "APPROVED", "CERTIFIED", "OK"}


def check(report, package_manifest=None):
    errs = []
    checks = report.get("checks") or []
    results = {c.get("id"): c.get("result") for c in checks if isinstance(c, dict)}
    verdict = report.get("result")

    if verdict == "PASS" and any(r in ("FAIL", "INCONCLUSIVE") for r in results.values()):
        bad = [k for k, v in results.items() if v in ("FAIL", "INCONCLUSIVE")]
        errs.append("R1 OVERCLAIM: result=PASS while %s is not PASS" % ",".join(bad))
    if report.get("assurance") == "attested" and results.get("S6") != "PASS":
        errs.append("R2 OVERCLAIM: assurance=attested while S6=%s" % results.get("S6"))
    if report.get("trust_level") in ("anchored", "witnessed") and results.get("S6") != "PASS":
        errs.append("R3 OVERCLAIM: trust_level=%s while S6=%s" %
                    (report.get("trust_level"), results.get("S6")))
    if package_manifest:
        st = (package_manifest.get("status") or "").upper()
        if st in PASSY and verdict != "PASS" and verdict is not None:
            errs.append("R4 DECLARED OVERRIDE: manifest.status=%s but verifier result=%s" % (st, verdict))
    return errs


def selftest():
    good = {
        "result": "PASS", "trust_level": "unanchored", "assurance": "unattested",
        "checks": [{"id": "S4", "result": "PASS"}, {"id": "S6", "result": "PASS"}],
    }
    bad = [
        ("pass-while-inconclusive", {"result": "PASS", "checks": [{"id": "S6", "result": "INCONCLUSIVE"}]}),
        ("attested-without-seal", {"result": "INCONCLUSIVE", "assurance": "attested",
                                   "checks": [{"id": "S6", "result": "INCONCLUSIVE"}]}),
        ("anchored-without-seal", {"result": "INCONCLUSIVE", "trust_level": "anchored",
                                   "checks": [{"id": "S6", "result": "INCONCLUSIVE"}]}),
        ("package-declares-pass", {"result": "INCONCLUSIVE",
                                   "checks": [{"id": "S6", "result": "INCONCLUSIVE"}]}),
    ]
    fails = 0
    for name, rep in bad:
        manifest = {"status": "PASS"} if name == "package-declares-pass" else None
        errs = check(rep, manifest)
        ok = bool(errs)
        print("%-26s -> %s" % (name, "REJECTED" if ok else "ACCEPTED (BAD)"))
        fails += 0 if ok else 1
    errs = check(good, {"status": "SUBMITTED"})
    print("%-26s -> %s" % ("honest-report", "ACCEPTED" if not errs else "REJECTED (BAD)"))
    fails += 0 if not errs else 1
    if fails:
        print("REPORT SELFTEST FAIL - %d wrong outcome(s)" % fails)
        return 1
    print("REPORT SELFTEST OK - 4/4 doctored reports rejected, 1 honest report accepted")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report", nargs="?")
    ap.add_argument("--package", help="directory containing manifest.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.report:
        ap.error("report path required (or --selftest)")
    with open(a.report, encoding="utf-8") as fh:
        rep = json.load(fh)
    manifest = None
    if a.package:
        p = os.path.join(a.package, "manifest.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                manifest = json.load(fh)
    errs = check(rep, manifest)
    if errs:
        print("REPORT REJECTED")
        for e in errs:
            print("  [FAIL] %s" % e)
        return 1
    print("REPORT ACCEPTED - result=%s, no overclaim found by R1-R4" % rep.get("result"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
