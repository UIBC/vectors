# UIBC conformance vectors

Four executable cases that show what a UIBC verdict is allowed to mean, and where it stops. Every row below is produced by `tools/make_vectors.py` and checked by `tools/run_vectors.py` against a hand-written expectation table.

```bash
pip install uibc-core==0.5.0
python tools/run_vectors.py        # exits 0 only when all six rows hold
```

No network, no credentials, no owner key: the seals are Ed25519, and the public key travels inside each package.

## The six rows

| Case | Mode | Expected | What it shows |
|---|---|---|---|
| `clean` | open | PASS | a stranger can verify without any key |
| `clean` | pinned to owner key | PASS | pinning does not break a genuine package |
| `tampered` | open | FAIL | one appended line in evidence is caught (S4) |
| `deleted` | open | FAIL | removing an evidence file is caught (S4) |
| `keyswap` | open | **PASS** | a full forgery, re-sealed by another key, verifies against itself |
| `keyswap` | pinned to owner key | FAIL | pinning is the only thing that catches it |

The fifth row is not a defect report, it is the boundary: **unpinned verification proves internal consistency, not authorship**. Anyone quoting a UIBC PASS without saying whether the key was pinned is quoting half a result.

## Files

- `vectors/` — the four packages (committed, small, plain JSON + text)
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

## Scope

These vectors demonstrate detection within the observed evidence boundary of `uibc-core` 0.5.0. They do not prove the absence of undetected attacks, and they are not a conformance suite for third-party implementations — that suite does not exist yet.

Licence: Apache-2.0.
