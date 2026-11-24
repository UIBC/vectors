"""Get a real RFC 3161 timestamp from a third-party TSA for the vector it ships.

    python tools/make_external_anchor.py [--case vectors/full] [--tsa URL]

Why this is not another self-signed artefact: every other witness in this corpus
is one we can mint - our tree, our head file, our pin, our seal. An RFC 3161
token is the one witness we cannot mint. It dates a digest with a key held by
somebody else, and the token plus the TSA's CA certificates verify **offline**
against nothing but the package, so a stranger can re-derive the anchor without
trusting us or reaching the network.

The digest is over `manifest.json`: the sealed manifest carries the evidence
root, the index digest and the lifecycle head, so dating it dates the claim.

Network is needed once, here. `tools/check_tsa.py` is the offline half and is
what CI runs - a token that stops verifying turns CI red rather than quietly
aging into folklore.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_REL = "evidence/sectigo-time.token"
BUNDLE_REL = "evidence/sectigo-ca.pem"
ANCHOR_REL = "evidence/external_anchor.json"


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def ca_bundle_for(signer):
    """Follow the signer's AIA to its issuer, then to the root, and return the PEM.

    Downloaded rather than hardcoded: a copied-in bundle ages silently, and the
    signer certificates rotate. The result is written into the package, so the
    offline check needs no network at all.
    """
    chain = []
    current = signer
    for _ in range(4):
        try:
            aia = current.extensions.get_extension_for_class(
                x509.AuthorityInformationAccess).value
        except Exception:
            break
        urls = [d.access_location.value for d in aia
                if d.access_method == x509.AuthorityInformationAccessOID.CA_ISSUERS]
        if not urls:
            break
        raw = fetch(urls[0])
        try:
            nxt = x509.load_der_x509_certificate(raw)
        except Exception:
            nxt = pkcs7.load_der_pkcs7_certificates(raw)[0]
        chain.append(nxt)
        if nxt.subject == nxt.issuer:
            break
        current = nxt
    return b"".join(c.public_bytes(serialization.Encoding.PEM) for c in chain)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=os.path.join(ROOT, "vectors", "full"))
    ap.add_argument("--tsa", default="https://timestamp.sectigo.com")
    a = ap.parse_args()

    from uibc_core import tsa

    man_path = os.path.join(a.case, "manifest.json")
    with open(man_path, "rb") as fh:
        manifest_bytes = fh.read()
    digest = hashlib.sha256(manifest_bytes).digest()

    req = tsa.build_request(digest)
    r = urllib.request.Request(a.tsa, data=req,
                               headers={"Content-Type": "application/timestamp-query",
                                        "User-Agent": "uibc-vectors/1.0"})
    with urllib.request.urlopen(r, timeout=40) as resp:
        body = resp.read()
    if not body:
        raise SystemExit("TSA returned an empty body; nothing to anchor")

    signer_der = None
    from asn1crypto import tsp as atsp
    for c in atsp.TimeStampResp.load(body)["time_stamp_token"]["content"]["certificates"]:
        if c.name == "certificate":
            signer_der = c.chosen.dump()
            break
    if signer_der is None:
        raise SystemExit("token carries no signer certificate; cannot build a CA bundle")
    signer = x509.load_der_x509_certificate(signer_der)
    bundle = ca_bundle_for(signer)
    if bundle:
        bundle += signer.public_bytes(serialization.Encoding.PEM)

    os.makedirs(os.path.dirname(os.path.join(a.case, TOKEN_REL)), exist_ok=True)
    with open(os.path.join(a.case, TOKEN_REL), "wb") as fh:
        fh.write(body)
    with open(os.path.join(a.case, BUNDLE_REL), "wb") as fh:
        fh.write(bundle)

    ok, info, problems = tsa.verify_token(body, digest, bundle)
    if not ok:
        raise SystemExit("the token does not verify offline: %s" % "; ".join(problems))

    doc = {
        "digest_of": "manifest.json",
        "digest": "sha256:" + digest.hex(),
        "tsr": TOKEN_REL,
        "cabundle": BUNDLE_REL,
        "tsa_url": a.tsa,
        "tsa": info.get("tsa"),
        "gen_time": info.get("gen_time"),
        "serial": info.get("serial"),
        "policy": info.get("policy"),
        "note": ("A real RFC 3161 token from a third-party TSA over the sealed "
                 "manifest. It is the one witness in this corpus we cannot mint; "
                 "it verifies offline against the CA bundle shipped beside it. "
                 "It dates existence, not correctness: a timestamp says these "
                 "bytes existed at gen_time, and says nothing about whether the "
                 "checks below them pass."),
    }
    with open(os.path.join(a.case, ANCHOR_REL), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"wrote": ANCHOR_REL, "gen_time": doc["gen_time"],
                      "serial": doc["serial"], "tsa": doc["gen_time"] and a.tsa},
                     indent=2))


if __name__ == "__main__":
    main()
