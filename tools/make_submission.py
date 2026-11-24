"""Write a submission from a run, instead of describing one by hand.

    python tools/make_submission.py --id uibc-self-20261124 \\
        --legal-entity "UIBC" --implementation uibc-core-verifier \\
        --language Python --repository https://github.com/example/verifier \\
        --contact https://github.com/UIBC --date 2026-11-24

    python tools/make_submission.py --id uibc-self-20261124 --reproduce

Why this exists: the first submission in this repository was written by hand
from a run I did once. Two things were wrong with that and only one of them was
obvious. The obvious one is that a stranger has to assemble three files, so
"submit yours" costs more than "read mine". The other one is that a hand-written
row can go stale in silence: change a fixture, rebuild a package, and the
committed results.json keeps claiming verdicts the current corpus no longer
produces - while every gate stays green, because none of them re-derives the row.
`--reproduce` is the fix for that half: it rebuilds the whole submission from
the corpus as committed, and a byte difference is a red leg in CI.

What this does not do: it does not decide anything for you. Independence,
competence basis and witness are copied from the flags or from the record being
reproduced, and the gate judges them afterwards. A generator that quietly filled
in "independent" would be the same disease as a validator that only sees good
input.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import run_vectors as rv  # noqa: E402 - the frozen rows, one source of truth

SUBMISSIONS = os.path.join(ROOT, "submissions")
ALL_CHECKS = [f"S{i}" for i in range(1, 20)]
CONTRACT = "uibc-submission-results/1"
ROW_LINE = "[OK]"


def corpus_digest():
    with open(os.path.join(ROOT, "FIXTURES.sha256"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def verifier_version():
    try:
        import uibc_core  # noqa: F401
        from importlib.metadata import version
        return version("uibc-core")
    except Exception:
        return None


def run_matrix():
    """Run the matrix gate as a reviewer would, and keep its stdout verbatim."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, os.path.join(TOOLS, "run_vectors.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if p.returncode != 0:
        sys.stderr.write(p.stdout[-4000:])
        raise SystemExit("the matrix gate did not pass - no submission is written from a run "
                         "that disagrees with the corpus")
    return p.stdout


def emitted_ids(case, extra):
    """The check ids this verifier actually evaluated on one case.

    Read from the verifier's own JSON rather than assumed: the specification
    names nineteen checks, and a submission may only claim the ones its results
    observed. S13 in the gate enforces that; this is where the observation is
    recorded.
    """
    import coverage_map as cov  # noqa: E402 - same directory, one implementation
    doc = cov.verify(case, extra)
    return sorted((c["id"] for c in doc.get("checks", [])),
                  key=lambda s: int(s[1:]) if s[1:].isdigit() else 999)


def parse_rows(log):
    rows = []
    for line in log.splitlines():
        if not line.startswith(ROW_LINE):
            continue
        label, rest = line[len(ROW_LINE):].strip().split(" rc=", 1)
        rc = int(rest.split(" ", 1)[0])
        verdict = rest.split("result=", 1)[1].split(" ", 1)[0]
        # the row's flags, recovered from the label the log printed: the label
        # is what a reviewer replays, so the mode is derived from it rather
        # than from a second table that could disagree. `split()` not
        # `split(" ")` - the log pads the label column, and padded spaces
        # parsed as flags once, which turned every open row into `flags`.
        parts = label.split()
        case = parts[0]
        flags = parts[1:]
        mode = rv.mode_of(flags)
        rows.append({"case": case, "mode": mode, "verdict": verdict, "exit_code": rc})
    if not rows:
        raise SystemExit("no verdict rows found in the matrix output - refusing to write a "
                         "submission whose results are empty")
    return rows


def attach_emitted(rows):
    """Record which checks each row actually put under test."""
    by_label = {}
    for case, extra, _rc, _want in rv.ROWS:
        mode = rv.mode_of(extra)
        by_label[(case, mode)] = extra
    for r in rows:
        extra = by_label.get((r["case"], r["mode"]), [])
        r["checks_emitted"] = emitted_ids(r["case"], extra)
    return rows


def build_results(rows, product, date):
    return {
        "contract_version": CONTRACT,
        "corpus_digest": corpus_digest(),
        "verifier": {
            "id": product["implementation"],
            "version": product["version"],
            "command": "python -m uibc_core.cli verify <pkg> [--pubkey keys/owner.key.pub]",
        },
        "rows": rows,
        "recorded_at": date,
    }


def build_product(args, product_in=None, rows=None):
    """Describe the submitter, and claim only what the rows actually observed.

    Default claim is the union of check ids the verifier emitted across this run,
    not all nineteen. Nineteen is how many the specification names; it is not how
    many this corpus put under test (see COVERAGE.md), and a submission that
    claimed all nineteen would be asserting behaviour nobody watched.
    """
    base = dict(product_in) if product_in else {}
    if "checks" in base:
        checks = base["checks"]
        not_covered = base.get("scope", {}).get("not_covered",
                                                [c for c in ALL_CHECKS if c not in checks])
    elif args.checks and args.checks != "all":
        checks = [c.strip() for c in args.checks.split(",") if c.strip()]
        not_covered = [c for c in ALL_CHECKS if c not in checks]
    elif rows is not None:
        checks = sorted({i for r in rows for i in r.get("checks_emitted", [])},
                        key=lambda s: int(s[1:]) if s[1:].isdigit() else 999)
        not_covered = [c for c in ALL_CHECKS if c not in checks]
    else:  # no rows and no explicit list: claim nothing, and say so
        checks, not_covered = [], list(ALL_CHECKS)
    out = {
        "legal_entity": base.get("legal_entity") or args.legal_entity,
        "implementation": base.get("implementation") or args.implementation,
        "version": base.get("version") or args.version or verifier_version(),
        "language": base.get("language") or args.language,
        "repository": base.get("repository") or args.repository,
        "checks": checks,
        "scope": {"not_covered": base.get("scope", {}).get("not_covered", not_covered)},
        "contact": base.get("contact") or args.contact,
        "independence": base.get("independence") or args.independence,
        "competence_basis": base.get("competence_basis") or args.competence,
        "witness": base.get("witness") if "witness" in base else _witness_from_args(args),
        "submitted_at": base.get("submitted_at") or args.date,
    }
    if base.get("submitter_pubkey"):
        out["submitter_pubkey"] = base["submitter_pubkey"]
    note = base.get("note") or args.note
    if note:
        out["note"] = note
    return out


def _witness_from_args(args):
    if not args.witness_name:
        return None
    return {"name": args.witness_name, "role": args.witness_role or "reviewer",
            "independent_of_submitter": str(args.witness_independent).lower() == "true"}


def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def emit(dest, product, results, log):
    os.makedirs(dest, exist_ok=True)
    write_json(os.path.join(dest, "product.json"), product)
    write_json(os.path.join(dest, "results.json"), results)
    write_text(os.path.join(dest, "run.log"), log)


def _neutral(**kw):
    """An args object with every flag at its default, for the reproduce path."""
    import types
    d = dict(checks="all", legal_entity=None, implementation=None, version=None,
             language=None, repository=None, contact=None, independence="same-maintainer",
             competence="none", witness_name=None, witness_role=None,
             witness_independent="false", note=None, date=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def reproduce(sub_id):
    src = os.path.join(SUBMISSIONS, sub_id)
    if not os.path.isdir(src):
        print(f"REPRODUCE: no submission at {src} - nothing to rebuild. This is not a pass.")
        return 2
    with open(os.path.join(src, "product.json"), encoding="utf-8") as fh:
        product_in = json.load(fh)
    log = run_matrix()
    rows = attach_emitted(parse_rows(log))
    product = build_product(_neutral(), product_in, rows)
    if "witness" not in product:
        product["witness"] = product_in.get("witness")
    results = build_results(rows, product, product.get("submitted_at"))

    stale = []
    with tempfile.TemporaryDirectory() as tmp:
        emit(tmp, product, results, log)
        for name in ("product.json", "results.json", "run.log"):
            with open(os.path.join(src, name), "rb") as fh:
                a = fh.read()
            with open(os.path.join(tmp, name), "rb") as fh:
                b = fh.read()
            if a != b:
                stale.append(name)
    if stale:
        print(f"SUBMISSION STALE - {sub_id} no longer matches a run of this corpus: "
              + ", ".join(stale))
        print("Regenerate it: python tools/make_submission.py --id " + sub_id
              + " --date " + str(product.get("submitted_at")))
        return 1
    print(f"SUBMISSION REPRODUCED - {sub_id}: the committed files are byte-identical to a "
          "fresh run of this corpus.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="submission directory name")
    ap.add_argument("--legal-entity")
    ap.add_argument("--implementation")
    ap.add_argument("--version")
    ap.add_argument("--language")
    ap.add_argument("--repository")
    ap.add_argument("--contact")
    ap.add_argument("--checks", default="all", help="comma list of check ids, or 'all'")
    ap.add_argument("--independence", default="same-maintainer",
                    choices=["same-maintainer", "independent"])
    ap.add_argument("--competence", default="none",
                    help="who ran it and on what standing, or 'none'")
    ap.add_argument("--witness-name")
    ap.add_argument("--witness-role")
    ap.add_argument("--witness-independent", default="false", choices=["true", "false"])
    ap.add_argument("--note")
    ap.add_argument("--date", default=None)
    ap.add_argument("--out", default=None, help="destination directory under submissions/")
    ap.add_argument("--reproduce", action="store_true",
                    help="rebuild an existing submission and diff it, writing nothing")
    a = ap.parse_args()

    if a.reproduce:
        return reproduce(a.id)

    a.date = a.date or _today()
    missing = [n for n in ("legal_entity", "implementation", "language", "repository", "contact")
               if not getattr(a, n)]
    if missing:
        raise SystemExit("missing --" + ", --".join(m.replace("_", "-") for m in missing)
                         + ": a submission without an accountable party is an anonymous claim")
    log = run_matrix()
    rows = attach_emitted(parse_rows(log))
    product = build_product(a, rows=rows)
    results = build_results(rows, product, a.date)
    dest = os.path.join(SUBMISSIONS, a.out or a.id)
    emit(dest, product, results, log)
    print(f"WROTE {os.path.relpath(dest, ROOT).replace(os.sep, '/')} - "
          f"{len(results['rows'])} rows, {len(product['checks'])} check(s) claimed "
          f"({len(product['scope']['not_covered'])} declared not covered), "
          f"corpus_digest {results['corpus_digest'][:12]}...")
    print("Next: python tools/check_submission.py   # the gate decides, not the generator")
    return 0


def _today():
    import datetime
    return datetime.date.today().isoformat()


if __name__ == "__main__":
    sys.exit(main())
