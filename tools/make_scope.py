"""Build the fixtures that prove what verification does *not* establish.

    python tools/make_scope.py

Why fixtures and not prose: every serious project in this space writes a
"what this does not guarantee" section - C2PA says its manifests carry no value
judgment about truth, Sigstore says a signature does not mean the software is
good. Those are claims about their own limits, and a reader has to take their
word for it. A limit can instead be *demonstrated*: build two packages that
differ only in the thing the format is said not to judge, verify both, and let
the two PASSes be the evidence. If the verifier ever starts judging that
property, one of the two turns red and the claim in SCOPE.md stops being true -
which is the only way a limitation statement can be kept honest over time.

Four limits are built here:

  scope/identity/a, scope/identity/b
      the same signing key, two unrelated owners ("alice", "acme-medical-
      devices-gmbh"). Both verify. Verification binds a package to a key, not
      to a legal entity, and nothing in the package can distinguish the two.

  scope/completeness/two, scope/completeness/three
      two and three evidence entries, both sealed. Both verify. The verifier
      can prove an entry was not altered after sealing; it cannot say whether
      the set is the complete set, because there is nothing to compare it to.

  scope/closure/plausible, scope/closure/placeholder
      the same closure block, once with a file that looks like model weights
      and once with a file that says it is not. Both verify. S10 checks that
      six components were declared with digests, not that the bytes behind
      them are what the field name says.

  author-time (prose only)
      an anchor with `anchored_at` set by the author is the author's word. The
      distinction needs a second external timestamp to show, and that needs a
      TSA key this repository does not hold, so this one stays prose.
"""

import base64
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from uibc_core.signing import ed_seal_sign  # noqa: E402

import make_vectors as mv  # noqa: E402

OWNER_KEY = os.path.join(ROOT, "keys", "owner.key")
CLOSURE_FIELDS = ("model_weights", "tokenizer", "chat_template",
                  "engine_build", "decoding", "numeric_env")


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def reseal(tmp):
    """Recompute the seal over identity + manifest + lifecycle, as the CLI does."""
    with open(OWNER_KEY, "r", encoding="ascii") as fh:
        seed = bytes.fromhex(fh.read().strip().split("ed25519:")[1])
    identity = read_json(os.path.join(tmp, "identity.json"))
    man = read_json(os.path.join(tmp, "manifest.json"))
    lifecycle = read_json(os.path.join(tmp, "lifecycle.json"))
    sig_b64, _pub = ed_seal_sign(seed, identity, man, lifecycle)
    seal_path = os.path.join(tmp, "signatures", "seal.json")
    seal = read_json(seal_path)
    seal["signature"] = sig_b64
    write_json(seal_path, seal)


def finish(tmp, dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(tmp, dest)
    shutil.rmtree(tmp, ignore_errors=True)


def base(work, name, owner=None):
    tmp = os.path.join(work, "_scope_" + name)
    if owner is None:
        mv.build_base(tmp, OWNER_KEY)
        return tmp
    # `mv.build_base` hardcodes the owner "alice". Rewriting identity.json
    # afterwards does not work - S3 refuses events whose actor is no longer an
    # authorised principal - so the second owner has to be registered as itself,
    # from an empty package, with the same key. That is the honest form of the
    # limitation: one key, two self-consistent packages, two unrelated owners.
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    mv.cli("init", tmp)
    mv.cli("register", "--agent-id", "vec-agent-001", "--owner", owner, tmp)
    mv.cli("event", "--type", "ACTIVATE", "--actor", owner, tmp)
    src = tmp + "_src"
    os.makedirs(src, exist_ok=True)
    for name_, body, kind, note in (("report.txt", mv.REPORT, "ACTION", "tool call log"),
                                    ("run.txt", mv.RUN, "OUTPUT", "run summary")):
        p = os.path.join(src, name_)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        mv.cli("evidence", "--file", p, "--type", kind, "--note", note, tmp)
    shutil.rmtree(src, ignore_errors=True)
    mv.cli("submit", "--key", OWNER_KEY, tmp)
    return tmp


def identity_pair(work):
    a = base(work, "id_a")
    b = base(work, "id_b", owner="acme-medical-devices-gmbh")
    finish(a, os.path.join(ROOT, "vectors", "scope", "identity", "a"))
    finish(b, os.path.join(ROOT, "vectors", "scope", "identity", "b"))


def completeness_pair(work):
    two = base(work, "cmp_two")
    three = base(work, "cmp_three")
    src = os.path.join(work, "_scope_third.txt")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("third action: one more tool call, not in the two-entry set\n")
    mv.cli("evidence", "--file", src, "--type", "ACTION",
           "--note", "a third action", three)
    mv.cli("submit", "--key", OWNER_KEY, three)
    os.remove(src)
    finish(two, os.path.join(ROOT, "vectors", "scope", "completeness", "two"))
    finish(three, os.path.join(ROOT, "vectors", "scope", "completeness", "three"))


def closure_pair(work):
    bodies = {
        "plausible": "uibc-scope placeholder artefact shaped like weights\n",
        "placeholder": "this file is not model weights and is not a tokenizer\n",
    }
    for kind, body in bodies.items():
        tmp = base(work, "cl_" + kind)
        closure = {}
        for field in CLOSURE_FIELDS:
            rel = "closure/%s.txt" % field
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
            closure[field] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        man = read_json(os.path.join(tmp, "manifest.json"))
        man["closure"] = closure
        man["note_b64"] = base64.b64encode(
            b"canonical base64, not permissive").decode("ascii")
        write_json(os.path.join(tmp, "manifest.json"), man)
        reseal(tmp)
        dest = os.path.join(ROOT, "vectors", "scope", "closure", kind)
        finish(tmp, dest)

    # The declared digest is never compared to the file that ships beside it:
    # rewriting the closure file after sealing leaves the manifest's digest
    # pointing at bytes that are not there, and the package still verifies.
    # Probed by hand first ("a shopping list still passes"), then frozen here so
    # the claim in SCOPE.md N3 goes red the day S10 starts comparing them.
    src = os.path.join(ROOT, "vectors", "scope", "closure", "placeholder")
    dest = os.path.join(ROOT, "vectors", "scope", "closure", "wrong-digest")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    with open(os.path.join(dest, "closure", "model_weights.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("actually a shopping list; the declared digest is of other bytes\n")


def main(work):
    os.makedirs(work, exist_ok=True)
    identity_pair(work)
    completeness_pair(work)
    closure_pair(work)
    print(json.dumps({"built": ["identity/a", "identity/b",
                                "completeness/two", "completeness/three",
                                "closure/plausible", "closure/placeholder"]},
                     indent=2))


if __name__ == "__main__":
    main(os.path.join(ROOT, "build"))
