"""Which of the nineteen checks does the corpus actually put under test?

    python tools/coverage_map.py            # write COVERAGE.md and coverage.json
    python tools/coverage_map.py --check    # fail if the committed files are stale

Why this exists: the repository claims nineteen checks and ships eight frozen
cases. Those two numbers are not the same number, and nothing in the repo said
so - EXPECTED.md lists which check each case is meant to trip, not which checks
no case touches at all. An implementation could skip every check that no fixture
exercises and still pass the whole matrix. That is not a defect in the
implementation; it is a gap in the corpus, and it belongs in a file a reader can
open rather than in my memory of what I built.

Three things are counted, and the second one is the uncomfortable one:

  exercised     the check appears in the verifier's output for at least one case
  discriminating  ... and answers something other than PASS for at least one case.
                A check that has only ever said PASS has never been observed to
                say anything: the code path exists, the decision does not.
  basis         the citation the verifier attaches to that check (direct /
                related / none). 'none' means the check is this project's own
                definition, and a reader is entitled to weigh it accordingly.

The map is regenerated, not edited: `--check` rebuilds it from the corpus as
committed and fails on a byte difference, so this file cannot drift away from
the thing it describes.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_vectors as rv  # noqa: E402 - the frozen rows, one source of truth

MD = os.path.join(ROOT, "COVERAGE.md")
JSON = os.path.join(ROOT, "coverage.json")


def verify(case, extra):
    cmd = [sys.executable, "-m", "uibc_core.cli", "verify",
           os.path.join(ROOT, "vectors", case), *extra]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    try:
        return json.loads(p.stdout)
    except Exception:
        raise SystemExit(f"the verifier did not print JSON for case {case} {extra} - "
                         "a coverage map read from unparseable output would be fiction")


def collect():
    per_check = {}
    rows = []
    for case, extra, want_rc, want_result in rv.ROWS:
        doc = verify(case, extra)
        mode = ("pinned" if any(a == "--pubkey" for a in extra)
                else ("flags" if extra else "open"))
        rows.append({"case": case, "mode": mode, "result": doc.get("result"),
                     "checks": len(doc.get("checks", []))})
        for c in doc.get("checks", []):
            d = per_check.setdefault(c["id"], {"id": c["id"], "name": c.get("name", ""),
                                               "basis": (c.get("basis") or {}).get("class", ""),
                                               "citation": (c.get("basis") or {}).get("citation", ""),
                                               "matrix": [], "adverse": []})
            d["matrix"].append({"case": case, "mode": mode, "result": c.get("result")})
    return per_check, rows


def collect_adversarial(per_check):
    """The same measurement over the doctored cases, which are built at run time.

    Two scopes are reported because they answer different questions. The frozen
    matrix is what a submission runs, so it is what a submission may claim. The
    adversarial supplement is what the corpus tests beyond that - a rule reached
    only by a doctored package is exercised by the corpus but is not evidence
    any submission can ship.
    """
    import run_adversarial as adv  # noqa: E402 - one definition of the cases
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn, why in adv.CASES:
            d = os.path.join(tmp, name)
            import shutil
            shutil.copytree(adv.CLEAN, d)
            fn(d)
            _rc, _result, doc = adv.verify(d, adv.extra_args(name, d))
            ids = [c["id"] for c in doc.get("checks", [])]
            out.append({"case": name, "why": why, "checks": ids})
            for c in doc.get("checks", []):
                d2 = per_check.setdefault(c["id"], {"id": c["id"], "name": c.get("name", ""),
                                                    "basis": (c.get("basis") or {}).get("class", ""),
                                                    "citation": (c.get("basis") or {}).get("citation", ""),
                                                    "matrix": [], "adverse": []})
                if not d2.get("name"):
                    d2["name"] = c.get("name", "")
                d2["adverse"].append({"case": name, "result": c.get("result")})
    return out


def order(ids):
    return sorted(ids, key=lambda s: int(s[1:]) if s[1:].isdigit() else 999)


def render(per_check, rows, adverse):
    ids = order(per_check)
    table_ids = order(set(ids) | {f"S{i}" for i in range(1, 20)})
    in_matrix = [i for i in table_ids if per_check.get(i, {}).get("matrix")]
    in_adverse = [i for i in table_ids if per_check.get(i, {}).get("adverse")]
    anywhere = [i for i in table_ids if per_check.get(i)]
    deciding = [i for i in anywhere
                if any(o["result"] != "PASS" for o in per_check[i]["matrix"])
                or any(o["result"] != "PASS" for o in per_check[i]["adverse"])]
    unreached = [i for i in table_ids if i not in per_check]

    lines = [
        "# Coverage — which checks the corpus puts under test",
        "",
        "Generated by `tools/coverage_map.py`. `python tools/coverage_map.py --check`",
        "rebuilds it from the corpus and fails on any byte difference, so this file",
        "cannot drift from the thing it describes.",
        "",
        "Two scopes, because they answer different questions:",
        "",
        f"- **frozen matrix** (the eight rows a submission runs): "
        f"**{len(in_matrix)}/19** checks reached",
        f"- **everything the corpus ships** (matrix + {len(adverse)} doctored cases): "
        f"**{len(anywhere)}/19** reached",
        f"- **checks that have ever answered something other than PASS**: "
        f"**{len(deciding)}/19**",
        f"- **checks no shipped case reaches**: **{len(unreached)}**"
        + (f" — {', '.join(unreached)}" if unreached else ""),
        "",
        "A check that has only ever said PASS has never been observed to decide",
        "anything. That is not proof it is broken; it is proof the corpus does not",
        "test it, and the difference matters when the claim is \"nineteen checks\".",
        "",
        "Why the two scopes differ: a submission runs the frozen matrix, so it may",
        "only claim ids the matrix observed (rule S13). A rule reached only by a",
        "doctored package is exercised by the corpus but is not evidence any",
        "submission can ship — the difference is the whole reason the doctored",
        "cases are generated at run time instead of committed.",
        "",
        "| check | name | basis | matrix cases | adversarial cases | non-PASS seen |",
        "|---|---|---|---|---|---|",
    ]
    for i in table_ids:
        if i not in per_check:
            lines.append(f"| {i} | — | — | 0 | 0 | **no case reaches it** |")
            continue
        d = per_check[i]
        m = len(d["matrix"])
        a = len(d["adverse"])
        bad = (sum(1 for o in d["matrix"] if o["result"] != "PASS")
               + sum(1 for o in d["adverse"] if o["result"] != "PASS"))
        basis = d["basis"] or "?"
        if d["citation"]:
            basis += f" ({d['citation']})"
        mark = "" if bad else " **never**"
        lines.append(f"| {i} | {d['name']} | {basis} | {m} | {a} | {bad}{mark} |")

    lines += ["", "## The eight frozen cases, and what each one reaches", "",
              "| case | mode | verdict | checks evaluated |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {r['mode']} | {r['result']} | {r['checks']} |")
    lines += ["", "## The doctored cases, and what each one reaches", "",
              "| case | verdict-driving rule | checks evaluated |", "|---|---|---|"]
    for r in adverse:
        lines.append(f"| {r['case']} | {r['why']} | {len(r['checks'])}: "
                     + ", ".join(r["checks"]) + " |")
    lines += [
        "",
        "## What this map is not",
        "",
        "It is not a statement that the corpus is adequate. It counts exposure, not",
        "quality: a check reached by one case may still be reached only in its easy",
        "branch. It is the smallest honest answer to \"which of your nineteen checks",
        "does your own corpus test?\", published because the alternative is a reader",
        "assuming the answer is nineteen.",
        "",
    ]
    doc = "\n".join(lines)
    data = {
        "contract": "uibc-coverage-map/1",
        "corpus_digest": _digest(),
        "counts": {"specified": 19, "matrix_reached": len(in_matrix),
                   "any_case_reached": len(anywhere), "deciding": len(deciding),
                   "unreached": len(unreached)},
        "unreached": unreached,
        "checks": [{"id": i, "name": per_check[i]["name"], "basis": per_check[i]["basis"],
                    "citation": per_check[i]["citation"],
                    "matrix_cases": len(per_check[i]["matrix"]),
                    "adversarial_cases": len(per_check[i]["adverse"]),
                    "non_pass": (sum(1 for o in per_check[i]["matrix"] if o["result"] != "PASS")
                                 + sum(1 for o in per_check[i]["adverse"] if o["result"] != "PASS"))}
                   for i in ids],
        "rows": rows,
        "adversarial": [{"case": r["case"], "checks": r["checks"]} for r in adverse],
    }
    return doc, data


def _digest():
    with open(os.path.join(ROOT, "FIXTURES.sha256"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def emit(doc, data, md_path, json_path):
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="rebuild and compare against the committed files, writing nothing")
    a = ap.parse_args()

    per_check, rows = collect()
    adverse = collect_adversarial(per_check)
    doc, data = render(per_check, rows, adverse)

    if a.check:
        stale = []
        with tempfile.TemporaryDirectory() as tmp:
            m, j = os.path.join(tmp, "COVERAGE.md"), os.path.join(tmp, "coverage.json")
            emit(doc, data, m, j)
            for name, new, old in (("COVERAGE.md", m, MD), ("coverage.json", j, JSON)):
                if not os.path.isfile(old):
                    stale.append(name + " (missing)")
                    continue
                with open(new, "rb") as fh:
                    nb = fh.read()
                with open(old, "rb") as fh:
                    ob = fh.read()
                if nb != ob:
                    stale.append(name)
        if stale:
            print("COVERAGE STALE - the committed map no longer matches the corpus: "
                  + ", ".join(stale))
            print("Regenerate: python tools/coverage_map.py")
            return 1
        print(f"COVERAGE OK - {data['counts']['matrix_reached']}/19 checks reached by the frozen "
              f"matrix, {data['counts']['any_case_reached']}/19 by any shipped case, "
              f"{data['counts']['deciding']}/19 ever decided non-PASS, "
              f"{data['counts']['unreached']} reached by nothing.")
        return 0

    emit(doc, data, MD, JSON)
    print(f"WROTE COVERAGE.md and coverage.json - {data['counts']['matrix_reached']}/19 matrix, "
          f"{data['counts']['any_case_reached']}/19 any case, {data['counts']['deciding']}/19 "
          f"deciding, {data['counts']['unreached']} unreached.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
