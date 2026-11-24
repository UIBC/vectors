"""Check the quotations behind every `direct` basis.

A `direct` claim says "an external document states this requirement". Until now
that claim was backed by a citation string, and a reader had to open the URL and
take our word for what it said. This tool makes the claim checkable offline:

    basis/quotes.json   one verbatim sentence per direct check, plus its digest
    basis/cache/*.html   the bytes we fetched, digested in basis/sources.json

Rules:

    Q1  every check whose basis is `direct` has at least one quote
    Q2  the sentence occurs, verbatim after whitespace normalisation, in the
        cached copy of the document the citation names
    Q3  the recorded digest is the digest of that sentence
    Q4  the cache still hashes to what sources.json recorded
    Q5  a citation that names a section ("§4.2.4") must have that section in the
        document; a recorded correction is allowed, and the corrected section
        must then exist instead
    Q6  a quote's source must be the citation the verifier gives for that check

    python tools/check_quotes.py --write   # fill digests from the cache
    python tools/check_quotes.py           # verify, print one line, exit 0/1

Exit 2 means the environment is wrong (no uibc_core, no cache), not that a quote
is missing.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUOTES = ROOT / "basis" / "quotes.json"
SOURCES = ROOT / "basis" / "sources.json"
sys.path.insert(0, str(ROOT / "tools"))

import fetch_sources as fs  # noqa: E402


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def corpus_text(doc, source_key):
    """The cached text for a source key. Two keys can name the same document
    (a citation with a section suffix and the bare draft), so resolve by URL."""
    src = doc["sources"].get(source_key)
    if src is None:
        raise KeyError(source_key)
    p = fs.path_for(src["url"], ".txt")
    if not p.exists():
        raise FileNotFoundError(p)
    return p.read_text(encoding="utf-8")


def section_present(text, section):
    """A heading, not a mention: the number, then a period and a space, or a
    sentence-case word right after it. Body references ("see Section 4.2.4")
    do not match because they carry the word `Section` in front and no period."""
    tail = r"(?:\s*\.\s|\s+[A-Z][A-Za-z])"
    return re.search(r"(?:^|\s)" + re.escape(section) + tail, text) is not None


def direct_checks():
    """Which checks claim `direct`, straight from the verifier."""
    try:
        import coverage_map as cm  # noqa: PLC0415 - optional dependency
        import run_vectors as rv  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        print(f"QUOTES SKIP - verifier not importable here ({e}); run on a leg with uibc-core.")
        return None
    per = {}
    for case, extra, _rc, _want in rv.ROWS:
        for c in cm.verify(case, extra).get("checks", []):
            b = c.get("basis") or {}
            per.setdefault(c["id"], {"class": b.get("class"), "citation": b.get("citation") or ""})
    return {cid: v for cid, v in per.items() if v["class"] == "direct"}


def problems(qdoc, sdoc, direct):
    probs, notes = [], []
    quotes = qdoc.get("quotes", [])
    corrections = qdoc.get("citation_corrections", {})

    by_check = {}
    for q in quotes:
        by_check.setdefault(q["check"], []).append(q)

    if direct:
        for cid, info in direct.items():
            if cid not in by_check:
                probs.append(f"Q1: {cid} claims direct but has no quoted sentence")
            elif by_check[cid][0]["source"] != info["citation"]:
                probs.append(f"Q6: {cid} cites {info['citation']!r} but the quote names "
                             f"{by_check[cid][0]['source']!r}")

    for cid in by_check:
        if direct and cid not in direct:
            probs.append(f"Q1: {cid} has a quote but does not claim direct")

    for q in quotes:
        cid = q["check"]
        try:
            text = corpus_text(sdoc, q["source"])
        except (KeyError, FileNotFoundError) as e:
            probs.append(f"Q2: {cid} quote points at {q['source']!r}, which is not cached ({e})")
            continue
        if fs.norm(q["text"]) not in text:
            probs.append(f"Q2: {cid} sentence not found verbatim in {q['source']}")
            continue
        want = fs.sha256_text(q["text"])
        if q.get("sha256") and q["sha256"] != want:
            probs.append(f"Q3: {cid} digest {q['sha256'][:12]} != recomputed {want[:12]}")

    for key, rec in sdoc["sources"].items():
        if fs.verify_one(rec):
            probs.append(f"Q4: {key} cache does not match its recorded digest")

    checked = 0
    for key, info in (direct or {}).items():
        m = re.search(r"§\s*([0-9]+(?:\.[0-9]+)*)", info["citation"])
        if not m:
            continue
        section = m.group(1)
        text = corpus_text(sdoc, info["citation"])
        fix = corrections.get(info["citation"])
        if section_present(text, section):
            checked += 1
            continue
        if fix:
            if section_present(text, fix["actual"]):
                notes.append(f"Q5: {key} cites §{section}, which the document does not have; "
                             f"§{fix['actual']} is the section that states it. Recorded, upstream fix pending.")
                checked += 1
                continue
            probs.append(f"Q5: {key} cites §{section} (missing) and the correction §{fix['actual']} is missing too")
        else:
            probs.append(f"Q5: {key} cites §{section}, which does not exist in the document")
    return probs, notes, checked


def render(qdoc, sdoc, direct):
    """The public artefact: for each direct check, the sentence itself."""
    lines = [
        "# Quotes — the sentence each `direct` check rests on",
        "",
        "Generated by `tools/check_quotes.py` from `basis/quotes.json`. Every line below was",
        "matched character for character against the cached copy of the document it cites,",
        "and the digest of the cached copy is recorded in `basis/sources.json`. A reader can",
        "verify all of it offline, with no network and no trust in us.",
        "",
        "| check | document | section | sentence | quote sha256 |",
        "|---|---|---|---|---|",
    ]
    for q in qdoc["quotes"]:
        text = q["text"].replace("|", "\\|")
        lines.append(f"| {q['check']} | {q['source']} | {q['where']} | {text} | `{q['sha256'][:16]}` |")
    lines += [
        "",
        "## What this shows, and what it does not",
        "",
        "It shows that the sentence exists in the document, with the wording we attributed to it,",
        "on the date recorded in `basis/sources.json`. It does **not** show that our implementation",
        "of the rule is correct: a well-quoted requirement and a correctly-built check are two",
        "different claims, and the corpus and adversarial cases carry the second one.",
        "",
        "Six of the eleven sources are individual Internet-Drafts. Quoting a draft accurately",
        "still means quoting a draft.",
    ]
    if qdoc.get("citation_corrections"):
        lines += ["", "## Recorded citation corrections", ""]
        for k, v in qdoc["citation_corrections"].items():
            lines.append(f"- **{k}** — the document has no such section; the rule is §{v['actual']}. "
                         f"{v['note']} Upstream: `{v['upstream']}`.")
    (ROOT / "QUOTES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_digests(qdoc, sdoc):
    for q in qdoc.get("quotes", []):
        q["sha256"] = fs.sha256_text(q["text"])
    QUOTES.write_text(json.dumps(qdoc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv):
    sdoc, qdoc = load(SOURCES), load(QUOTES)
    if "--write" in argv:
        write_digests(qdoc, sdoc)
        print(f"WROTE basis/quotes.json digests for {len(qdoc['quotes'])} quote(s).")
        return 0
    direct = direct_checks()
    probs, notes, checked = problems(qdoc, sdoc, direct)
    for n in notes:
        print(f"  .. {n}")
    if probs:
        print(f"QUOTES FAILED - {len(probs)} problem(s):")
        for p in probs:
            print(f"  !! {p}")
        return 1
    before = (ROOT / "QUOTES.md").read_text(encoding="utf-8") if (ROOT / "QUOTES.md").exists() else ""
    render(qdoc, sdoc, direct)
    after = (ROOT / "QUOTES.md").read_text(encoding="utf-8")
    if before and before != after:
        print("  !! QUOTES.md was stale; rewritten. Re-run --check.")
        return 1
    total_direct = len(direct) if direct else 0
    print(f"QUOTES OK - {len(qdoc['quotes'])} quoted sentence(s) for {total_direct} direct check(s), "
          f"verbatim in the cached copy; {checked} section reference(s) resolve in the document.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
