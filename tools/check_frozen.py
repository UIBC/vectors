"""Freeze the committed fixture bytes, the way a normative vector set is frozen.

    python tools/check_frozen.py            # verify against FIXTURES.sha256
    python tools/check_frozen.py --write    # rewrite the manifest (maintainers)

Why this exists: a vector set that changes silently is not a vector set. The
manifest records a digest per fixture file, so "the bytes you ran against" and
"the bytes in the repository" can be compared by a third party without trusting
us. Reviewer-facing text lives in EXPECTED.md; this file is the machine half.
"""

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "FIXTURES.sha256")
TREES = ["vectors/clean", "vectors/tampered", "vectors/deleted", "vectors/keyswap",
         "vectors/unsigned", "vectors/unknown-upgrade", "vectors/full",
         # The scope fixtures are pinned for the same reason as the rest: SCOPE.md
         # claims two packages differing only in one property both verify, and a
         # silent edit to either member would make that claim describe bytes that
         # no longer exist.
         "vectors/scope"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk():
    out = []
    for tree in TREES:
        base = os.path.join(ROOT, tree.replace("/", os.sep))
        if not os.path.isdir(base):
            continue
        for root, _dirs, names in os.walk(base):
            for n in sorted(names):
                p = os.path.join(root, n)
                rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
                out.append((rel, sha256(p)))
    return sorted(out)


def write():
    rows = walk()
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        for rel, dig in rows:
            fh.write("%s  %s\n" % (dig, rel))
    print("FROZEN WRITTEN - %d files -> %s" % (len(rows), os.path.basename(MANIFEST)))
    return 0


def verify():
    if not os.path.exists(MANIFEST):
        print("FROZEN FAIL - FIXTURES.sha256 missing")
        return 1
    expect = {}
    with open(MANIFEST, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            dig, rel = line.split("  ", 1)
            expect[rel] = dig
    cur = dict(walk())
    bad = []
    for rel, dig in expect.items():
        if rel not in cur:
            bad.append("missing: %s" % rel)
        elif cur[rel] != dig:
            bad.append("changed: %s" % rel)
    for rel in cur:
        if rel not in expect:
            bad.append("unlisted: %s" % rel)
    if bad:
        print("FROZEN FAIL - %d deviation(s)" % len(bad))
        for x in bad:
            print("  [FAIL] %s" % x)
        return 1
    print("FROZEN OK - %d fixture files match FIXTURES.sha256" % len(expect))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return write() if a.write else verify()


if __name__ == "__main__":
    sys.exit(main())
