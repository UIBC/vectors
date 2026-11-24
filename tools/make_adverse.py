"""Derive the two boundary fixtures from `clean`: unsigned, and a package whose
manifest *declares* PASS while nothing attests it.

    python tools/make_adverse.py

Both are byte-for-byte derived from `vectors/clean`, so a reader can recompute
them without a private key. Neither can be produced by accident: `unsigned`
has the seal removed, `unknown-upgrade` additionally rewrites the manifest
status. The point of the second one is that a self-declaration is not evidence:
the verifier must still answer INCONCLUSIVE.
"""

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "vectors", "clean")


def derive(name, drop_seal=True, rewrite_status=None):
    dst = os.path.join(ROOT, "vectors", name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst)
    if drop_seal:
        seal = os.path.join(dst, "signatures", "seal.json")
        if os.path.exists(seal):
            os.remove(seal)
    if rewrite_status:
        p = os.path.join(dst, "manifest.json")
        with open(p, "rb") as fh:
            b = fh.read()
        if b'"status": "SUBMITTED"' not in b:
            raise SystemExit("cannot find status field in manifest.json")
        b = b.replace(b'"status": "SUBMITTED"', ('"status": "%s"' % rewrite_status).encode())
        with open(p, "wb") as fh:
            fh.write(b)
    print("built vectors/%s" % name)


def main():
    # A package with no seal: internally consistent, provenance unattested.
    derive("unsigned", drop_seal=True)
    # The same package, but its manifest claims PASS. A declaration must not
    # be able to upgrade an INCONCLUSIVE verdict.
    derive("unknown-upgrade", drop_seal=True, rewrite_status="PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
