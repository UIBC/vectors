#!/usr/bin/env python3
"""Key hygiene guard for this repository.

Three rules, each with a reason:

1. No private key material outside `keys/`. A seed committed next to
   `tools/` or `vectors/` would look like a fixture and behave like a
   credential; nothing downstream can tell the difference.

2. `keys/` holds exactly the four pinned fixture files, by name and by
   SHA-256. The fixtures are public on purpose (see `keys/README.md`),
   which makes "quietly replace them with a real key" the only way this
   directory could become harmful. A digest pin turns that into a red build.

3. No PEM private-key headers anywhere, including `keys/`. There is no
   fixture that needs one, so a hit is always a mistake.

Run: `python tools/check_key_hygiene.py` (exit 0 clean, 1 on any violation).
"""

import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PINNED = {
    "keys/owner.key": "87ca9915e596b2d53da73d637e1e5f0f36fbed5ace6f9d98090a759fa2cc19b7",
    "keys/owner.key.pub": "e847ad8641f6fb038329767d8796e0607625ccc3fbbdea935a7d9ec807ee3be9",
    "keys/attacker.key": "5385ddf38bc14cdb5162d80adc2b2fc04e1c5a77cc751aa55a02636807aebdab",
    "keys/attacker.key.pub": "2a73165783d408be9df13a81e8c4956da66505bce3d4f5b6910c2183bcaa9250",
}

SEED_RE = re.compile(rb"ed25519:[0-9a-fA-F]{64}")
PEM_RE = re.compile(rb"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PGP) PRIVATE KEY-----")
KEYS_DIR = "keys"
# Documentation lives here too; it carries no key material and is not a fixture.
KEYS_ALLOWED_EXTRA = {"keys/README.md"}


def tracked_files():
    """Tracked files plus untracked-not-ignored ones.

    Ignored scratch work is excluded because it is not what a reader clones;
    a file that git would happily commit is included, because that is exactly
    the shape a leak takes before anyone notices it.
    """
    try:
        out = subprocess.run(
            ["git", "-C", ROOT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=True,
        ).stdout
        return [p for p in out.decode("utf-8").split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        found = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "build", "regen")]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, "/")
                found.append(rel)
        return found


def main():
    failures = []
    files = tracked_files()

    for rel in files:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            failures.append(f"{rel}: unreadable ({exc})")
            continue

        if PEM_RE.search(data):
            failures.append(f"{rel}: PEM private-key header (no fixture needs one)")

        if rel.startswith(KEYS_DIR + "/") or rel == KEYS_DIR:
            continue

        for m in SEED_RE.finditer(data):
            line = data[: m.start()].count(b"\n") + 1
            failures.append(
                f"{rel}:{line}: ed25519 seed outside keys/ "
                f"({m.group(0)[:16].decode()}...) - generate at run time instead"
            )

    present = {p for p in files if p.startswith(KEYS_DIR + "/")} - KEYS_ALLOWED_EXTRA
    if present != set(PINNED):
        missing = sorted(set(PINNED) - present)
        extra = sorted(present - set(PINNED))
        if missing:
            failures.append(f"keys/: pinned fixture missing: {', '.join(missing)}")
        if extra:
            failures.append(f"keys/: unpinned file present: {', '.join(extra)}")

    for rel, digest in PINNED.items():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != digest:
            failures.append(
                f"{rel}: digest changed (pinned {digest[:16]}..., found {actual[:16]}...) - "
                f"the public fixtures are not replaceable"
            )

    if failures:
        print("KEY HYGIENE FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(f"KEY HYGIENE OK - {len(files)} tracked files, "
          f"{len(PINNED)} pinned fixtures unchanged, no seed outside keys/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
