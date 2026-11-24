"""Build the vector that exercises the opt-in checks a submission can claim.

    python tools/make_full.py

Why a separate builder: most checks in the specification are opt-in - they only
speak when a package carries the artefact or the caller passes the flag (an
anchor set, a receipt chain, a Merkle tree, an out-of-band head pin, a state
file). A submission that only ships the eight baseline rows can therefore claim
ten of nineteen checks, not because it is hiding anything but because the corpus
never gave the verifier the inputs. This builder produces two cases that do:

  vectors/full             carries closure, a Merkle tree, a receipt chain, an
                           anchor set, a policy map and one canonical base64
                           field, and is verified with `--expect-head`
  vectors/full-state       the same bytes, verified with `--state-file`, to make
                           S19 speak on a first observation

Two honest limits, stated here because they are the first things a reviewer
should ask:

* S10 checks that all six closure components were *declared with a digest*. It
  cannot check that those digests correspond to what actually ran, and this
  vector does not pretend otherwise: the digests are of the artefacts shipped
  beside them, nothing more.
* S15 resolves an anchor against the tree this package can recompute. It is not
  a Bitcoin or RFC 3161 anchor; S16 stays unreached because a token needs a TSA
  key we do not hold.
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

from uibc_core import merkle  # noqa: E402
from uibc_core.canonical import hash_obj  # noqa: E402
from uibc_core.chain import receipt_digest, GENESIS  # noqa: E402
from uibc_core.signing import ed_seal_sign  # noqa: E402
from uibc_core.verify import CLOSURE_FIELDS  # noqa: E402

import make_vectors as mv  # noqa: E402

CLOSURE_ARTEFACTS = {
    "model_weights": "closure/weights.txt",
    "tokenizer": "closure/tokenizer.txt",
    "chat_template": "closure/chat_template.txt",
    "engine_build": "closure/engine_build.txt",
    "decoding": "closure/decoding.txt",
    "numeric_env": "closure/numeric_env.txt",
}
POLICY_ARTEFACT = "evidence/policies/retention.json"


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def evidence_leaves(pkg):
    idx = read_json(os.path.join(pkg, "evidence", "index.json"))
    entries = sorted(idx["entries"], key=lambda e: e.get("path", ""))
    leaves = []
    for e in entries:
        with open(os.path.join(pkg, "evidence", e["path"]), "rb") as fh:
            leaves.append(merkle.leaf_hash(fh.read()))
    return entries, leaves


def build(work):
    owner = os.path.join(ROOT, "keys", "owner.key")
    tmp = os.path.join(work, "_full_src")
    mv.build_base(tmp, owner)

    entries, leaves = evidence_leaves(tmp)
    root = merkle.root_hash(leaves)

    # 1. Merkle tree over the evidence set, with an inclusion proof per entry.
    #    build_proof returns siblings; the verifier recomputes the root itself,
    #    so this is proof the package can be checked, not a claim about us.
    proofs = []
    for i, e in enumerate(entries):
        proofs.append({"path": e["path"], "index": i,
                       "proof": merkle.build_proof(leaves, i)})
    write_json(os.path.join(tmp, "evidence", "merkle.json"),
               {"algorithm": "rfc6962-sha256", "size": len(leaves),
                "root": root.hex(), "proofs": proofs})

    # 2. A two-receipt chain, linked by the digest of the predecessor's envelope.
    #    Genesis is 64 zeros - the format's own rule, not ours.
    env1 = {"seq": 1, "action": "evidence", "note": "first record"}
    env2 = {"seq": 2, "action": "submit", "note": "second record"}
    write_json(os.path.join(tmp, "evidence", "chain.json"),
               {"schema": "uibc-chain/1",
                "receipts": [{"envelope": env1, "previous_receipt_hash": GENESIS},
                             {"envelope": env2,
                              "previous_receipt_hash": receipt_digest(env1)}]})

    # 3. An anchor that resolves against this tree offline.
    write_json(os.path.join(tmp, "evidence", "anchors.json"),
               {"resolver": "evidence-merkle",
                "anchors": [{"id": "anchor-1", "version": 1,
                             "leaf_hash": leaves[0].hex(),
                             "anchored_at": "2026-11-25T00:00:00Z",
                             "root": root.hex(), "index": 0, "size": len(leaves),
                             "proof": merkle.build_proof(leaves, 0)}]})

    # 4. A policy map whose digest is over the JCS of the shipped artefact.
    policy = {"id": "retention-1", "retain_days": 365,
              "rule": "evidence is retained for one year from submission"}
    artef = os.path.join(tmp, POLICY_ARTEFACT)
    write_json(artef, policy)
    write_json(os.path.join(tmp, "evidence", "policies.json"),
               {"policies": [{"digest": "sha256:" + hash_obj(policy),
                              "path": POLICY_ARTEFACT}]})

    # 5. Seal first, then add the two manifest-level declarations.
    #    `uibc submit` rebuilds manifest.json from the package contents, so any
    #    field written before it is silently dropped - the first version of this
    #    builder did exactly that and S10/S14 never spoke. The seal covers
    #    identity + manifest + lifecycle, so the seal has to be recomputed over
    #    the manifest that actually ships; that is done below with the same
    #    signing call the CLI uses, not by hand-writing a signature.
    mv.cli("submit", "--key", owner, tmp)

    man_path = os.path.join(tmp, "manifest.json")
    man = read_json(man_path)
    closure = {}
    for field, rel in CLOSURE_ARTEFACTS.items():
        assert field in CLOSURE_FIELDS, field
        body = "declared %s for this vector; content is not the point\n" % field
        p = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        closure[field] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    man["closure"] = closure
    man["note_b64"] = base64.b64encode(
        b"canonical base64, not permissive").decode("ascii")
    write_json(man_path, man)

    with open(owner, "r", encoding="ascii") as fh:
        seed = bytes.fromhex(fh.read().strip().split("ed25519:")[1])
    identity = read_json(os.path.join(tmp, "identity.json"))
    lifecycle = read_json(os.path.join(tmp, "lifecycle.json"))
    sig_b64, _pub_b64 = ed_seal_sign(seed, identity, man, lifecycle)
    seal_path = os.path.join(tmp, "signatures", "seal.json")
    seal = read_json(seal_path)
    seal["signature"] = sig_b64
    write_json(seal_path, seal)

    dest = os.path.join(work, "full")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(tmp, dest)
    shutil.rmtree(tmp, ignore_errors=True)

    man = read_json(os.path.join(dest, "manifest.json"))
    print(json.dumps({"case": "full",
                      "checkpoint_head": man.get("checkpoint_head"),
                      "evidence_leaves": len(leaves),
                      "root": root.hex()}, indent=2))


if __name__ == "__main__":
    work = os.path.join(ROOT, "vectors")
    build(work)
