"""Keep a byte-for-byte copy of every document we cite, next to its digest.

A citation that only carries a URL is a claim about what a document says, and
the reader has to go and check it. A citation that carries the sentence, the
digest of that sentence, and the digest of the fetched copy is a claim the
reader can re-check offline against the same bytes we read.

    python tools/fetch_sources.py              # verify cache vs sources.json
    python tools/fetch_sources.py --refresh    # re-fetch, rewrite hashes (network)
    python tools/fetch_sources.py --rebuild-text  # re-derive .txt from cached .html

The cache is small (eleven documents, ~1 MB) and it is the *only* thing that
lets a stranger reproduce a quotation without trusting us or the network.
"""

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "basis" / "sources.json"
CACHE = ROOT / "basis" / "cache"

# URL -> stable local name. Deriving a name from the URL produces
# "www.rfc-editor.org_rfc_rfc3161.html.html", which is how the first run went.
SLUG = {
    "https://www.rfc-editor.org/rfc/rfc8785.html": "rfc8785",
    "https://www.rfc-editor.org/rfc/rfc6962.html": "rfc6962",
    "https://www.rfc-editor.org/rfc/rfc8032.html": "rfc8032",
    "https://www.rfc-editor.org/rfc/rfc4648.html": "rfc4648",
    "https://www.rfc-editor.org/rfc/rfc3161.html": "rfc3161",
    "https://datatracker.ietf.org/doc/html/draft-sharif-agent-audit-trail-03":
        "draft-sharif-agent-audit-trail-03",
    "https://datatracker.ietf.org/doc/html/draft-marques-asqav-compliance-receipts-01":
        "draft-marques-asqav-compliance-receipts-01",
    "https://datatracker.ietf.org/doc/html/draft-noa-scitt-ai-agent-receipt-00":
        "draft-noa-scitt-ai-agent-receipt-00",
    "https://datatracker.ietf.org/doc/html/draft-maintainer-1f916-agent-record-01":
        "draft-maintainer-1f916-agent-record-01",
    "https://datatracker.ietf.org/doc/html/draft-bailey-scitt-agent-session-receipt":
        "draft-bailey-scitt-agent-session-receipt",
}


def norm(s):
    """Whitespace, and the space HTML puts before punctuation, made uniform.

    Nothing else is touched: case, wording and punctuation stay exactly as the
    document has them, because the point is to check the sentence, not to
    paraphrase it.
    """
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([.,;:)\]])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    return s.strip()


def sha256_text(s):
    return hashlib.sha256(norm(s).encode("utf-8")).hexdigest()


def to_text(raw):
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return norm(html.unescape(body))


def load():
    return json.loads(SRC.read_text(encoding="utf-8"))


def save(doc):
    SRC.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def path_for(url, ext):
    return CACHE / (SLUG[url] + ext)


def refresh(doc):
    CACHE.mkdir(parents=True, exist_ok=True)
    for key, rec in doc["sources"].items():
        url = rec["url"]
        req = urllib.request.Request(url, headers={"User-Agent": "uibc-vectors/1"})
        try:
            raw = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - network shapes vary
            print(f"  !! {url}: {e}")
            return 2
        path_for(url, ".html").write_text(raw, encoding="utf-8")
        path_for(url, ".txt").write_text(to_text(raw), encoding="utf-8")
        rec["slug"] = SLUG[url]
        rec["cache"] = path_for(url, ".html").name
        rec["cache_bytes"] = len(raw.encode("utf-8"))
        rec["cache_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        print(f"  {rec['slug']}: {rec['cache_bytes']} bytes")
    save(doc)
    return 0


def rebuild_text(doc):
    for url in {r["url"] for r in doc["sources"].values()}:
        html_path = path_for(url, ".html")
        if not html_path.exists():
            print(f"  !! missing cache for {url}")
            return 2
        path_for(url, ".txt").write_text(to_text(html_path.read_text(encoding="utf-8")),
                                         encoding="utf-8")
        print(f"  text {SLUG[url]}.txt")
    return 0


def verify_one(rec):
    """0 if the cached copy still hashes to what was recorded, else 1."""
    p = path_for(rec["url"], ".html")
    if not p.exists():
        return 1
    got = hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    return 0 if got == rec.get("cache_sha256") else 1


def verify(doc):
    bad = 0
    for key, rec in doc["sources"].items():
        if verify_one(rec):
            print(f"  !! {key}: cached copy missing or digest differs from the record")
            bad += 1
    return bad


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--rebuild-text", action="store_true")
    args = ap.parse_args(argv)
    doc = load()
    for key, rec in doc["sources"].items():
        if rec["url"] not in SLUG:
            print(f"  !! {key}: url has no cache slug; add it to SLUG")
            return 2
    if args.refresh:
        rc = refresh(doc)
        if rc:
            return rc
    elif args.rebuild_text:
        rc = rebuild_text(doc)
        if rc:
            return rc
    bad = verify(doc)
    if bad:
        print(f"CACHE FAILED - {bad} problem(s)")
        return 1
    print(f"CACHE OK - {len(doc['sources'])} source(s), each cached and matching its recorded digest.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
