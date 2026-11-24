# UIBC conformance vectors

Six executable packages and eight rows that show what a UIBC verdict is allowed to mean, and where it stops. Every row is produced by `tools/make_vectors.py` / `tools/make_adverse.py` and checked by `tools/run_vectors.py` against a hand-written expectation table.

```bash
pip install uibc-core==0.5.0
python tools/run_vectors.py        # exits 0 only when all eight rows hold
python tools/run_adversarial.py    # 9 must-reject cases + 3 documented gaps
python tools/check_frozen.py       # fixture bytes vs FIXTURES.sha256
```

No network, no credentials, no owner key: the seals are Ed25519, and the public key travels inside each package.

## The eight rows

| Case | Mode | Expected | What it shows |
|---|---|---|---|
| `clean` | open | PASS | a stranger can verify without any key |
| `clean` | pinned to owner key | PASS | pinning does not break a genuine package |
| `tampered` | open | FAIL | one appended line in evidence is caught (S4) |
| `deleted` | open | FAIL | removing an evidence file is caught (S4) |
| `keyswap` | open | **PASS** | a full forgery, re-sealed by another key, verifies against itself |
| `keyswap` | pinned to owner key | FAIL | pinning is the only thing that catches it |
| `unsigned` | open | INCONCLUSIVE | no seal: consistent, unattested — never PASS |
| `unknown-upgrade` | open | INCONCLUSIVE | a manifest that *declares* PASS cannot upgrade a verdict |

The fifth row is not a defect report, it is the boundary: **unpinned verification proves internal consistency, not authorship**. Anyone quoting a UIBC PASS without saying whether the key was pinned is quoting half a result.

The last two rows are that boundary seen from the other side. A verifier that answers PASS for an unsigned package cannot tell "signed" from "declared", and a package that declares its own PASS has produced no evidence at all.

## Adversarial supplement (separate from the frozen matrix)

`tools/run_adversarial.py` builds twelve doctored packages at run time and requires them not to verify: duplicate JSON member, raw control character, undeclared root file, index path escape, byte appended after sealing, timestamp rollback, sequence gap, unsigned, self-declared PASS, and three index-metadata rewrites.

The last three are a genuine finding, not a passing test. **D-002**: the S7 index-metadata digest covers `path`, `content_hash`, `type` and `note`, but not `evidence_id`, `media_type` or `created_at` — those three can be rewritten while the verdict stays PASS. They are printed as `[DEFECT]`, the run stays green only while the defect still reproduces, and `--strict` fails until it is fixed. A gap that quietly stops reproducing turns the run red, so the ledger cannot rot.

## Files

- `vectors/` — the six packages (committed, small, plain JSON + text)
- `FIXTURES.sha256` — one digest per committed fixture file; `check_frozen.py` compares
- `keys/` — TEST-ONLY Ed25519 seeds and their public keys. The seeds are public on purpose so `keyswap` can be rebuilt by anyone. Never reuse them.
- `tools/make_vectors.py` — regenerates all four cases through the public CLI
- `tools/run_vectors.py` — the gate; six rows, exit 1 on any deviation
- `tools/make_receipt.py` — runs the six rows and writes a receipt with per-case byte digests
- `tools/check_receipt.py` — re-derives those digests from this repo and rejects a receipt whose bytes moved
- `EXPECTED.md` — the same table with the verifier version and the check that fired
- `RUNS.md` — the ledger; currently one author row, zero external runs

## Send back a receipt

```bash
pip install uibc-core==0.5.0
python tools/make_receipt.py --runner "<your handle>" --blind yes|no --code independent|author
python tools/check_receipt.py receipts/<file>.json     # must print ACCEPTABLE
```

Then open an *Independent run receipt* issue with the file. A receipt is a record that a run happened on bytes that still hash to what you recorded — it is **not** a claim that the runner exists, and it does not by itself make this project externally verified. It is how a first external row gets written down instead of asserted.

### Do not renormalise the fixtures

The committed fixture files carry CRLF (they were written on Windows), and a receipt hashes their bytes. Any renormalisation — `git add --renormalize`, or an editor that rewrites line endings and commits — moves every digest and turns a valid receipt into a rejected one. `.gitattributes` declares `vectors/`, `receipts/` and `keys/` non-text so that cannot happen by accident. If `check_receipt.py` rejects a receipt the build did not touch, suspect the working bytes before the receipt: compare `git hash-object` of the file with `git rev-parse HEAD:<path>`.

## Scope

These vectors demonstrate detection within the observed evidence boundary of `uibc-core` 0.5.0. They do not prove the absence of undetected attacks, and they are not a conformance suite for third-party implementations — that suite does not exist yet.

Licence: Apache-2.0.
