"""Check every external RFC 3161 token in the corpus, offline.

    python tools/check_tsa.py

The token in `vectors/full` is the one witness in this corpus we cannot mint:
it was issued by a third party over the sealed manifest. It is also the one
artefact that can rot silently - a TSA certificate expires, a bundle goes stale,
someone re-seals the package and the digest moves on. None of that is visible
in a verdict unless somebody re-verifies, so this runs on every push.

What it asserts, per package that carries `evidence/external_anchor.json`:

* the anchored file still hashes to the digest inside the token (messageImprint)
* the signer chains to the CA bundle shipped in the package
* the signature verifies
* the token's genTime falls inside the signer certificate's validity window

What it does not assert: that the timestamp means anything about correctness.
A timestamp dates existence. It is evidence that these bytes existed at
gen_time, and nothing more.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VECTORS = os.path.join(ROOT, "vectors")


def tokens():
    for name in sorted(os.listdir(VECTORS)):
        p = os.path.join(VECTORS, name, "evidence", "external_anchor.json")
        if os.path.isfile(p):
            yield name, p


def main():
    from uibc_core import tsa

    if not tsa.HAVE_ASN1:
        print("TSA CHECK FAILED - the verifier cannot judge a token here: asn1crypto "
              "is not installed. Counting an unjudged token as checked is the "
              "overclaim this file exists to prevent.")
        return 2

    seen = 0
    problems = []
    for name, path in tokens():
        pkg = os.path.join(VECTORS, name)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        rel = doc.get("digest_of") or "manifest.json"
        with open(os.path.join(pkg, rel), "rb") as fh:
            data = fh.read()
        with open(os.path.join(pkg, doc.get("tsr") or ""), "rb") as fh:
            token = fh.read()
        with open(os.path.join(pkg, doc.get("cabundle") or ""), "rb") as fh:
            bundle = fh.read()
        seen += 1
        import hashlib
        ok, info, probs = tsa.verify_token(token, hashlib.sha256(data).digest(), bundle)
        if ok:
            print(f"[OK] {name}: token dates {rel} at {info.get('gen_time')} "
                  f"({(info.get('tsa') or {}).get('organization_name')}, "
                  f"serial {info.get('serial')})")
        else:
            problems.append((name, probs))

    if problems:
        print(f"\nTSA CHECK FAILED - {len(problems)} token(s) no longer verify:")
        for name, probs in problems:
            print(f"  !! {name}: {'; '.join(probs)[:200]}")
        print("A token that stopped verifying is not an anchor. Re-issue it with "
              "tools/make_external_anchor.py, or remove the claim.")
        return 1

    if not seen:
        print("TSA CHECK FAILED - no external token found; the corpus claims an "
              "external witness and ships none.")
        return 1

    print(f"\nTSA CHECK OK - {seen} external token(s) verify offline against their "
          f"shipped CA bundles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
