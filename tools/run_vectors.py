"""The gate: assertions that must hold, or this run is not evidence.

    python tools/run_vectors.py

Each assertion is a (case, mode, expected) row. A row that does not match is
printed and the process exits 1 - a vector set that "mostly" holds is worth
nothing, because the one cell that drifted is the one that matters.

Rows 7-8 are the boundary in the other direction: an unsigned package, and one
whose manifest declares PASS, must both come back INCONCLUSIVE. A verifier that
answers PASS for either is telling you it cannot tell "signed" from "declared".
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "vectors")
OWNER_PUB = os.path.join(ROOT, "keys", "owner.key.pub")

# The checkpoint `vector-full` declares after sealing. Pinning it is what makes
# S9 speak; if the vector is rebuilt, this value moves and the row fails until
# someone reads the new head out of the package - which is the point of a pin.
FULL_HEAD = "sha256:bd646e8345c011e44dde4da486d093cf472ab01baa9efc42ada067cd5a8b83eb"
# A state file the S19 row starts without. Removed before the row runs so the
# first observation is first every time; a stale watermark would silently turn
# this row into a comparison.
STATE_FILE = os.path.join(ROOT, "build", "s19-state.json")


def mode_of(extra):
    """The row's mode label, derived from its flags in one place.

    Four kinds: `open` (no flags), `pinned` (the owner key is pinned - the
    case this matrix was built for), `flags:<name>` and `flags:<a>+<b>` for
    every other flag set. The flag names are part of the label because two
    rows can share a case and differ only by which flags they pass - keying
    a row on "flags" alone let two `full` rows collide, and the submission
    gate refused its own record for "appears twice". Every consumer that keys
    rows by mode (the submission gate, the generator, the coverage map) asks
    this function instead of re-deriving it.
    """
    if not extra:
        return "open"
    names = [a[2:] if a.startswith("--") else a for a in extra if a.startswith("--")]
    if not names:
        return "open"
    if names == ["pubkey"]:
        return "pinned"
    return "flags:" + "+".join(sorted(names))

ROWS = [
    # (case, extra args, expected exit code, expected result)
    ("clean",    [],                                      0, "PASS"),
    ("clean",    ["--pubkey", OWNER_PUB],                  0, "PASS"),
    ("tampered", [],                                       1, "FAIL"),
    ("deleted",  [],                                       1, "FAIL"),
    # documented boundary: a full re-seal by another key verifies against itself,
    # and is only caught when the verifier pins the owner's public key.
    ("keyswap",  [],                                       0, "PASS"),
    ("keyswap",  ["--pubkey", OWNER_PUB],                  1, "FAIL"),
    # a package with no seal: consistent, unattested -> INCONCLUSIVE, never PASS
    ("unsigned", [],                                       1, "INCONCLUSIVE"),
    # a manifest that *declares* PASS without a seal: a declaration is not
    # evidence, and INCONCLUSIVE must not be upgradable by self-description
    ("unknown-upgrade", [],                                1, "INCONCLUSIVE"),
    # The opt-in half. These rows give the verifier the artefacts and flags the
    # checks above never receive, so a submission built on this matrix can claim
    # the rules that only speak when asked - not just the ten that always run.
    # `vector-full` carries closure, a Merkle tree, a receipt chain, an anchor
    # set and a policy map, and pins the head out of band; the pin is the
    # checkpoint the package itself declares, so a drifted head breaks this row.
    ("full",    ["--expect-head", FULL_HEAD],              0, "PASS"),
    # S19 remembers a high-water mark instead of being told the head each time.
    # A first observation is INCONCLUSIVE on purpose: there is nothing yet to
    # compare against, and "nothing compared" is not "nothing wrong".
    ("full",    ["--expect-head", FULL_HEAD,
                 "--state-file", STATE_FILE],              1, "INCONCLUSIVE"),
]


def reset_row_state(extra):
    """Clear the state file a row starts from, if it carries one.

    Every consumer of this matrix calls this before running a row: the gate
    here, the cross-version replay, the submission generator. It lives in one
    place because the cross-version replay forgot it once and read the
    watermark the gate had just written, then answered PASS where the frozen
    row says INCONCLUSIVE.
    """
    if STATE_FILE in extra:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass


def verify(case, extra):
    reset_row_state(extra)
    path = os.path.join(VECTORS, case)
    cmd = [sys.executable, "-m", "uibc_core.cli", "verify", path, *extra]
    env = dict(os.environ)
    # The verifier emits Chinese notes in its report. On Windows the default
    # console code page is cp1252, which fails to *encode* (child) and to
    # *decode* (this parent) that text. Pin UTF-8 on both sides; this is a
    # runner-side workaround for an upstream defect, documented in EXPECTED.md.
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    result = None
    try:
        result = json.loads(p.stdout).get("result")
    except Exception:
        for line in p.stdout.splitlines():
            if '"result"' in line:
                result = line.split('"')[3]
                break
    return p.returncode, result, p.stdout, p.stderr


def main():
    failures = []

    def label_part(extra):
        # The log is an artefact a reviewer reads and a stranger replays. An
        # absolute path from the machine that produced it makes it unrepeatable
        # and leaks the author's directory layout, so paths are printed
        # repo-relative: `--pubkey keys/owner.key.pub` means the same thing
        # anywhere the repo is cloned.
        out = []
        for tok in extra:
            rel = os.path.relpath(tok, ROOT) if os.path.isabs(tok) else tok
            out.append(rel.replace("\\", "/"))
        return " ".join(out)

    for case, extra, want_rc, want_result in ROWS:
        rc, result, out, err = verify(case, extra)
        label = f"{case}{' ' + label_part(extra) if extra else ''}"
        ok = (rc == want_rc and result == want_result)
        print(f"[{'OK' if ok else 'MISMATCH'}] {label:<28} rc={rc} result={result} "
              f"(expected rc={want_rc} result={want_result})")
        if not ok:
            failures.append((label, rc, result, want_rc, want_result, err.strip()))

    if failures:
        print(f"\nMATRIX GATE FAILED - {len(failures)} of {len(ROWS)} rows deviated:")
        for label, rc, result, want_rc, want_result, err in failures:
            print(f"  !! {label}: got rc={rc} result={result}, expected rc={want_rc} result={want_result}")
            if err:
                print(f"     stderr: {err.splitlines()[-1]}")
        print("A vector set whose cells drift is not evidence. Fix the vectors or the verifier.")
        return 1

    print(f"\nMATRIX GATE OK - all {len(ROWS)} rows match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
