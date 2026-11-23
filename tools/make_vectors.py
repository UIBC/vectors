"""Rebuild the committed vector set from scratch.

Every vector in this repository is produced by this script from the public
`uibc-core` CLI, so a reader can regenerate the same shapes and compare.

    python tools/make_vectors.py --work build

The keys under `keys/` are TEST-ONLY Ed25519 seeds committed on purpose:
anyone can re-sign with them, which is exactly what makes the `keyswap` vector
reproducible. Never use these seeds for anything real.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPORT = "action log: three tool calls, one refusal, one retry\n"
RUN = "run summary: tools=3 refusals=1 retries=1 exit=0\n"
REPORT_FORGED = "action log: attacker-controlled bytes, internally consistent\n"


def cli(*args):
    cmd = [sys.executable, "-m", "uibc_core.cli", *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def build_base(path, owner_key, report=REPORT):
    if os.path.isdir(path):
        shutil.rmtree(path)
    cli("init", path)
    # `register` already writes the REGISTER lifecycle event; adding one by hand
    # would make S3 fail with "duplicate REGISTER".
    cli("register", "--agent-id", "vec-agent-001", "--owner", "alice", path)
    cli("event", "--type", "ACTIVATE", "--actor", "alice", path)

    # Source files live OUTSIDE the package: `evidence` copies them into
    # evidence/files/, and anything else left at the package root is undeclared.
    src = path + "_src"
    if os.path.isdir(src):
        shutil.rmtree(src)
    os.makedirs(src)
    with open(os.path.join(src, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    with open(os.path.join(src, "run.txt"), "w", encoding="utf-8") as f:
        f.write(RUN)

    cli("evidence", "--file", os.path.join(src, "report.txt"), "--type", "ACTION",
        "--note", "tool call log", path)
    cli("evidence", "--file", os.path.join(src, "run.txt"), "--type", "OUTPUT",
        "--note", "run summary", path)
    shutil.rmtree(src, ignore_errors=True)
    cli("submit", "--key", owner_key, path)


def copy_case(base, dest, name):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(base, dest)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.join(ROOT, "vectors"))
    args = ap.parse_args()

    owner_key = os.path.join(ROOT, "keys", "owner.key")
    attacker_key = os.path.join(ROOT, "keys", "attacker.key")
    for k in (owner_key, attacker_key):
        if not os.path.exists(k):
            raise SystemExit(f"missing test key: {k}")

    base = os.path.join(args.work, "_base")
    build_base(base, owner_key)

    clean = copy_case(base, os.path.join(args.work, "clean"), "clean")

    tampered = copy_case(base, os.path.join(args.work, "tampered"), "tampered")
    with open(os.path.join(tampered, "evidence", "files", "report.txt"), "a", encoding="utf-8") as f:
        f.write("tampered: one line appended after sealing\n")

    deleted = copy_case(base, os.path.join(args.work, "deleted"), "deleted")
    os.remove(os.path.join(deleted, "evidence", "files", "report.txt"))

    # A full forgery: the attacker builds a package that is internally
    # consistent and seals it with their own key. Unpinned verification accepts
    # it (it verifies against itself); pinning the owner's public key rejects it.
    keyswap = os.path.join(args.work, "keyswap")
    build_base(keyswap, attacker_key, report=REPORT_FORGED)

    shutil.rmtree(base, ignore_errors=True)

    print(json.dumps({"built": ["clean", "tampered", "deleted", "keyswap"],
                      "work": args.work}, indent=2))


if __name__ == "__main__":
    main()
