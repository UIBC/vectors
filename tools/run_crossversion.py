"""Cross-version replay: does an older verifier answer the corpus the same way?

    python tools/run_crossversion.py                        # current interpreter only
    python tools/run_crossversion.py --also D:\\venv041\\Scripts\\python.exe

Why this is not just a regression test: the corpus carries a version floor
(`min_verifier_version` in each manifest). An old verifier that quietly guessed
PASS on fields it cannot judge would be a defect in the verifier; one that says
"below the floor, cannot judge" is the floor working. Both look like a verdict,
so the matrix has to separate them instead of showing a red cell.

Rules:

  V1  read `min_verifier_version` from each fixture manifest
  V2  verifier below the floor -> PASS is the refused answer. INCONCLUSIVE means "cannot judge",
      FAIL means "a defect was visible anyway"; both are honest. A PASS there would mean it
      declared a package healthy using fields it says it cannot judge.
      (a PASS there would mean it judged bytes it declares it cannot judge)
  V3  verifier at or above the floor -> the answer must equal the frozen row
  V4  a verifier that cannot be run is reported as unrunnable, never as a pass

Exit 1 only when V2 or V3 is violated. A version floor doing its job is a green
cell, not a failure.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_vectors as rv  # noqa: E402


def ver_tuple(v):
    parts = [int(x) for x in re.findall(r"\d+", str(v))]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def floor_of(case):
    p = os.path.join(ROOT, "vectors", case, "manifest.json")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh).get("min_verifier_version", "0.0.0")


def which_version(python):
    code = ("import uibc_core, json; "
            "print(json.dumps({'v': getattr(uibc_core,'__version__','?')}))")
    try:
        out = subprocess.run([python, "-c", code], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
        return json.loads(out.stdout)["v"]
    except Exception:
        return None


def run_row(python, case, extra):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [python, "-m", "uibc_core.cli", "verify", os.path.join(ROOT, "vectors", case), *extra]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=120)
    except Exception:
        return None
    try:
        return json.loads(p.stdout).get("result")
    except Exception:
        for line in p.stdout.splitlines():
            if '"result"' in line:
                return line.split('"')[3]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--also", action="append", default=[],
                    help="another python executable with uibc-core installed")
    a = ap.parse_args()

    pythons = [sys.executable] + a.also
    found = [(p, which_version(p)) for p in pythons]
    found = [(p, v) for p, v in found if v]
    if not found:
        print("CROSSVERSION: no python with uibc-core importable - nothing to compare")
        return 2

    problems = []
    table = []
    for python, version in found:
        vt = ver_tuple(version)
        for case, extra, want_rc, want in rv.ROWS:
            floor = floor_of(case)
            got = run_row(python, case, extra)
            label = case + ("|pinned" if extra else "|open")
            if got is None:
                problems.append(f"V4: {version} could not be run on {label}")
                continue
            if vt < ver_tuple(floor):
                ok = got in {"INCONCLUSIVE", "FAIL"}
                rule = "below floor -> INCONCLUSIVE or FAIL, never PASS"
                if not ok:
                    problems.append(
                        f"V2: {version} is below the floor {floor} for {label} but answered {got} "
                        f"(calling a package healthy with fields it declares it cannot judge)")
            else:
                ok = got == want
                rule = f"must equal frozen row ({want})"
                if not ok:
                    problems.append(f"V3: {version} on {label} answered {got}, frozen row says {want}")
            table.append({"version": version, "row": label, "floor": floor,
                          "expected": ("INCONCLUSIVE or FAIL" if vt < ver_tuple(floor) else want),
                          "got": got, "ok": ok, "rule": rule})
            print(f"[{'OK' if ok else 'VIOLATION'}] {version:<8} {label:<20} "
                  f"floor={floor:<7} got={got:<13} {'(floor)' if vt < ver_tuple(floor) else ''}")

    out = {"contract_version": "uibc-crossversion/1", "rows": table}
    with open(os.path.join(ROOT, "crossversion-results.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print()
    if problems:
        print(f"CROSSVERSION FAILED - {len(problems)} violation(s):")
        for p in problems:
            print(f"  !! {p}")
        return 1
    print(f"CROSSVERSION OK - {len(found)} verifier(s) x {len(rv.ROWS)} rows; "
          f"above-floor rows match the frozen corpus, below-floor rows answer INCONCLUSIVE.")
    print("Written: crossversion-results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

