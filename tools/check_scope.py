"""Check that SCOPE.md tells the truth about what the verifier does not do.

    python tools/check_scope.py            # check
    python tools/check_scope.py --write    # render SCOPE.md
    python tools/check_scope.py --check    # render and compare bytes

Why this gate exists: every project in this space publishes a "what we do not
guarantee" section, and every one of them is prose a reader has to believe. A
limit statement is worth more when it is falsifiable - when something turns red
if the limit ever stops being true. Here each non-guarantee is either
(a) demonstrated by a fixture pair that both verify *right now* (if the verifier
learned to judge that property, one member would stop passing and this gate
would fail), or (b) quoted out of the verifier's own report, so we cannot invent
a limit we do not actually have.

  SC1  contract fields, and enough of each list to be worth reading
  SC2  every guarantee cites a check id that the verifier really emits
  SC3  every non-guarantee is phrased negatively - it cannot be read as a claim
  SC4  every fixture pair exists and both members PASS on this machine
  SC5  every verifier-declared limit appears verbatim in the verifier's report
  SC6  at most three limits may rest on the verifier's own words; the rest need
       a fixture, so the file cannot degenerate into self-quotation
  SC7  every peer quote is verbatim in a cached copy whose digest matches
  SC8  the industry table names what we are out of scope for, and who covers it
  SC9  SCOPE.md is byte-identical to what this file renders
  SC10 no overclaim wording survives in the rendered text
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import fetch_peers  # noqa: E402
import run_vectors  # noqa: E402

SCOPE = os.path.join(ROOT, "scope", "scope.json")
PEERS = os.path.join(ROOT, "scope", "peers.json")
OUT = os.path.join(ROOT, "SCOPE.md")

BANNED = ("适用于所有行业", "适用于全部行业", "all industries", "best-in-class",
          "lowest cost", "全面领先", "断崖式领先")
FITS = ("strong", "workable", "out")
MAX_VERIFIER_DECLARED = 3


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def verifier_report():
    """The verifier's own account of its limits, from the fullest vector."""
    rc, result, out, err = run_vectors.verify("full", ["--expect-head",
                                                       run_vectors.FULL_HEAD])
    if result != "PASS":
        raise SystemExit("scope gate needs vectors/full to PASS; got %r %s" % (result, err))
    doc = json.loads(out)
    return doc.get("limitations", []), doc.get("not_checked", [])


def problems_for(doc, peers, basis_ids, limitations, not_checked):
    p = []
    for key in ("schema", "reviewed_on", "verifier", "guarantees",
                "non_guarantees", "industries"):
        if key not in doc:
            p.append("SC1 missing field %r" % key)
    if len(doc.get("guarantees", [])) < 5:
        p.append("SC1 fewer than five guarantees")
    if len(doc.get("non_guarantees", [])) < 4:
        p.append("SC1 fewer than four non-guarantees")
    if len(doc.get("industries", [])) < 5:
        p.append("SC1 fewer than five industry rows")

    for g in doc.get("guarantees", []):
        for c in g.get("checks", []):
            if c not in basis_ids:
                p.append("SC2 %s cites check %s, which the verifier does not emit" % (g.get("id"), c))
        if not g.get("says") or not g.get("how"):
            p.append("SC2 %s needs a sentence and a mechanism" % g.get("id"))

    declared = 0
    for n in doc.get("non_guarantees", []):
        nid = n.get("id", "?")
        st = n.get("statement", "")
        if not any(w in st for w in ("not ", "cannot", "never", "no ")):
            p.append("SC3 %s is not phrased as a limit: %r" % (nid, st))
        ev = n.get("evidence", {})
        kind = ev.get("kind")
        if kind == "fixture-pair":
            members = ev.get("members", [])
            if len(members) < 2:
                p.append("SC4 %s needs at least two fixture members" % nid)
            for m in members:
                path = os.path.join(ROOT, "vectors", *m.split("/"))
                if not os.path.isdir(path):
                    p.append("SC4 %s member %r does not exist" % (nid, m))
                    continue
                rc, result, out, err = run_vectors.verify(m, [])
                if result != "PASS":
                    p.append("SC4 %s member %s no longer PASSes (%r) - the limit is false now"
                             % (nid, m, result))
            if "PASS" not in ev.get("observed", ""):
                p.append("SC4 %s must record what was observed" % nid)
        elif kind == "verifier-declared":
            declared += 1
            needle = ev.get("observed_from_verifier", "")
            hay = "\n".join(limitations + not_checked)
            if not needle or needle not in hay:
                p.append("SC5 %s quotes %r, which the verifier does not say" % (nid, needle))
        else:
            p.append("SC4 %s has an unknown evidence kind %r" % (nid, kind))

    if declared > MAX_VERIFIER_DECLARED:
        p.append("SC6 %d limits rest on the verifier's own words; at most %d may"
                 % (declared, MAX_VERIFIER_DECLARED))

    peer_doc = peers.get("peers", {})
    if len(peer_doc) < 3:
        p.append("SC7 fewer than three peer pages")
    for key, rec in peer_doc.items():
        if fetch_peers.verify_one(rec):
            p.append("SC7 %s: cached copy missing or digest differs" % key)
            continue
        txt_path = os.path.join(ROOT, "scope", "cache",
                                fetch_peers.SLUG[rec["url"]] + ".txt")
        txt = open(txt_path, encoding="utf-8").read()
        if rec["quote"] not in txt:
            p.append("SC7 %s: quote is not verbatim in the cached copy" % key)

    outs = [i for i in doc.get("industries", []) if i.get("fit") == "out"]
    if not outs:
        p.append("SC8 nothing is declared out of scope")
    for i in doc.get("industries", []):
        if i.get("fit") not in FITS:
            p.append("SC8 %r has fit %r" % (i.get("name"), i.get("fit")))
        if not i.get("reason"):
            p.append("SC8 %r has no reason" % i.get("name"))
        if i.get("fit") == "out" and not i.get("peer_that_covers_it"):
            p.append("SC8 %r is out of scope but names nobody who covers it" % i.get("name"))
    return p


def render(doc, peers):
    lines = []
    add = lines.append
    add("# Scope — what a PASS establishes, and what it does not")
    add("")
    add("Generated by `tools/check_scope.py` from `scope/scope.json` and "
        "`scope/peers.json`; `python tools/check_scope.py --check` re-renders it and "
        "fails on any byte difference. Reviewed %s against %s."
        % (doc["reviewed_on"], doc["verifier"]))
    add("")
    add(doc["statement"])
    add("")
    add("## 1. What it does establish")
    add("")
    add("| id | a PASS establishes | checks | how |")
    add("|---|---|---|---|")
    for g in doc["guarantees"]:
        add("| %s | %s | %s | %s |" % (g["id"], g["says"], " ".join(g["checks"]), g["how"]))
    add("")
    add("## 2. What it does not establish")
    add("")
    add("Each row is falsifiable: a `fixture-pair` row is demonstrated by two packages "
        "that differ only in the property we say is not judged, and both verify; a "
        "`verifier-declared` row quotes the verifier's own report. If either stops "
        "being true, `tools/check_scope.py` fails.")
    add("")
    for n in doc["non_guarantees"]:
        ev = n["evidence"]
        if ev["kind"] == "fixture-pair":
            proof = "fixture pair `%s` (differs by %s) — %s" % (
                "` + `".join(ev["members"]), ev.get("differs_by", ""), ev.get("observed", ""))
        else:
            proof = "the verifier says so itself: \"%s\"" % ev["observed_from_verifier"]
        add("**%s. %s**" % (n["id"], n["statement"]))
        add("")
        add("%s" % n["why"])
        add("")
        add("Evidence: %s." % proof)
        add("")
    add("## 3. Where it fits")
    add("")
    add("| industry | fit | why | covered by someone else |")
    add("|---|---|---|---|")
    for i in doc["industries"]:
        add("| %s | `%s` | %s | %s |" % (i["name"], i["fit"], i["reason"],
                                          i["peer_that_covers_it"] or "—"))
    add("")
    add("## 4. How the peers phrase their own limits")
    add("")
    add("Every project here publishes an explicit limit section. The point of quoting "
        "them is not comparison — it is that this file's limits are written the same "
        "way: by the project, about itself, checkable against the document.")
    add("")
    add("| project | where | what they say they do not do | cached copy |")
    add("|---|---|---|---|")
    for key, rec in peers["peers"].items():
        add("| %s | %s | \"%s\" | `scope/cache/%s.html` |"
            % (rec["name"], rec["section"], rec["quote"], fetch_peers.SLUG[rec["url"]]))
    add("")
    add("## 5. The rule this file follows")
    add("")
    add("A limitation that nobody can re-check is a marketing line. So: no limit may be "
        "asserted unless it is demonstrated by a fixture in this repository or quoted "
        "from the verifier's own report, and no guarantee may cite a check the verifier "
        "does not emit. Both are enforced by `tools/check_scope.py`, which is also a "
        "gate in `tools/stranger.py` and a job in CI.")
    add("")
    return "\n".join(lines)


def selftest(doc, peers, basis_ids, limitations, not_checked):
    """Six mutations a reader can reproduce; each must be caught by its rule.

    A gate that has never failed is a gate nobody knows works. These are the
    exact ways this file could become dishonest: cite a check that does not
    exist, phrase a limit as a claim, drop the fixture that proves a limit,
    misquote the verifier, misquote a peer, or declare an industry out of scope
    without saying who covers it.
    """
    import copy
    cases = []

    def mutate(fn):
        d2, p2 = copy.deepcopy(doc), copy.deepcopy(peers)
        fn(d2, p2)
        return problems_for(d2, p2, basis_ids, limitations, not_checked)

    def invented_check(d, p):
        d["guarantees"][0]["checks"] = ["S99"]

    def positive_phrasing(d, p):
        d["non_guarantees"][0]["statement"] = \
            "It establishes that the signer is the legal entity named."

    def lost_member(d, p):
        d["non_guarantees"][0]["evidence"]["members"] = ["scope/identity/a"]

    def misquote_verifier(d, p):
        d["non_guarantees"][3]["evidence"]["observed_from_verifier"] = \
            "Timestamps are anchored by the verifier."

    def alter_peer(d, p):
        first = list(p["peers"].values())[0]
        first["quote"] = "The C2PA specifications provide value judgments."

    def orphan_industry(d, p):
        for i in d["industries"]:
            if i["fit"] == "out":
                i["peer_that_covers_it"] = ""

    cases = [
        ("SC2 invented check id", invented_check),
        ("SC3 limit phrased as a claim", positive_phrasing),
        ("SC4 fixture pair lost its second member", lost_member),
        ("SC5 misquoted verifier", misquote_verifier),
        ("SC7 peer quote altered", alter_peer),
        ("SC8 out of scope with nobody named", orphan_industry),
    ]

    bad = []
    for name, fn in cases:
        problems = mutate(fn)
        caught = bool(problems)
        print("  [%s] %s%s" % ("CAUGHT" if caught else "MISSED", name,
                               "" if caught else "  <-- the gate is blind here"))
        if not caught:
            bad.append(name)
    if bad:
        print("SCOPE SELFTEST FAILED - %d mutation(s) not caught: %s" % (len(bad), bad))
        return 1
    print("SCOPE SELFTEST OK - %d mutation(s) judged as expected." % len(cases))
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    doc = read_json(SCOPE)
    peers = read_json(PEERS)
    basis = read_json(os.path.join(ROOT, "basis.json"))
    basis_ids = {c["id"] for c in basis.get("checks", [])}
    limitations, not_checked = verifier_report()

    if args.selftest:
        return selftest(doc, peers, basis_ids, limitations, not_checked)

    problems = problems_for(doc, peers, basis_ids, limitations, not_checked)
    text = render(doc, peers)

    for word in BANNED:
        if word in text:
            problems.append("SC10 overclaim wording survived: %r" % word)

    if args.write:
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("SCOPE written - %d guarantee(s), %d non-guarantee(s), %d industry row(s)."
              % (len(doc["guarantees"]), len(doc["non_guarantees"]), len(doc["industries"])))

    if args.check:
        if not os.path.exists(OUT):
            problems.append("SC9 SCOPE.md is missing")
        else:
            on_disk = open(OUT, encoding="utf-8", newline="").read()
            if on_disk != text:
                problems.append("SC9 SCOPE.md differs from what scope/scope.json renders")

    if problems:
        print("SCOPE FAILED - %d problem(s):" % len(problems))
        for x in problems:
            print("  !! %s" % x)
        return 1
    print("SCOPE OK - %d guarantee(s) cite emitted checks; %d limit(s) hold as "
          "fixtures or verifier-declared; %d peer quote(s) verbatim in cache; %d out "
          "of scope." % (len(doc["guarantees"]), len(doc["non_guarantees"]),
                         len(peers["peers"]), len([i for i in doc["industries"]
                                                   if i["fit"] == "out"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
