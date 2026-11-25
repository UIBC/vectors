"""Cache the sentences our peers use to describe their own limits.

    python tools/fetch_peers.py            # verify cache vs scope/peers.json
    python tools/fetch_peers.py --refresh  # re-fetch (network)

SCOPE.md makes a claim about other projects - that each of them publishes an
explicit "what this does not guarantee" section, and that ours did not. A claim
about someone else's document has to be checkable against their bytes, not
against our memory of them: the cache here is what lets a reader confirm the
sentence without a network, and what makes a drifting page detectable.
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
SRC = ROOT / "scope" / "peers.json"
CACHE = ROOT / "scope" / "cache"

SLUG = {
    "https://c2pa.org/specifications/specifications/2.0/security/Harms_Modelling.html":
        "c2pa-harms-modelling",
    "https://docs.sigstore.dev/about/security/": "sigstore-security",
    "https://docs.sigstore.dev/about/threat-model/": "sigstore-threat-model",
    "https://opensource.contentauthenticity.org/docs/getting-started/":
        "cai-getting-started",
    "https://c2pa.ai/content-credentials-guide": "c2pa-ai-guide",
}


def norm(s):
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([.,;:)\]])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    return s.strip()


def to_text(raw):
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return norm(html.unescape(body))


def verify_one(rec):
    p = CACHE / (SLUG[rec["url"]] + ".html")
    if not p.exists():
        return 1
    # Bytes, not text: a Python text read on Windows silently rewrites CRLF to
    # LF, which would make a digest over "the bytes we read" a digest over bytes
    # nobody has. The cache is written with LF on every platform for the same
    # reason - so a clone hashes to what the record says.
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    return 0 if got == rec.get("cache_sha256") else 1


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    if args.refresh:
        CACHE.mkdir(parents=True, exist_ok=True)
        for key, rec in doc["peers"].items():
            url = rec["url"]
            if url not in SLUG:
                print(f"  !! {key}: url has no slug")
                return 2
            req = urllib.request.Request(url, headers={"User-Agent": "uibc-vectors/1"})
            raw = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
            data = raw.replace("\r\n", "\n").encode("utf-8")
            (CACHE / (SLUG[url] + ".html")).write_bytes(data)
            (CACHE / (SLUG[url] + ".txt")).write_bytes(
                to_text(raw).encode("utf-8"))
            rec["cache_bytes"] = len(data)
            rec["cache_sha256"] = hashlib.sha256(data).hexdigest()
            print(f"  {key}: {rec['cache_bytes']} bytes -> {SLUG[url]}.html")
        SRC.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    bad = 0
    for key, rec in doc["peers"].items():
        if verify_one(rec):
            print(f"  !! {key}: cached copy missing or digest differs")
            bad += 1
    if bad:
        print(f"PEERS FAILED - {bad} cached peer page(s) do not match their digest.")
        return 1
    print(f"PEERS OK - {len(doc['peers'])} peer page(s) cached, each matching its digest.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
