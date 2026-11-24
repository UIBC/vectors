# EXPECTED · the matrix behind the gate

Verifier: `uibc-core` 0.5.0 [PROPOSAL]. Generated: 2026-11-23 by `tools/make_vectors.py`.
Gate: `tools/run_vectors.py` — exit 1 on any deviation from the rows below.

| Case | Mode | Result | Check that fires | Meaning |
|---|---|---|---|---|
| clean | open | PASS | — (all checks PASS) | Byte-level structure, identity, lifecycle, evidence hashes, root and Ed25519 seal all hold. |
| clean | `--pubkey keys/owner.key.pub` | PASS | — | Pinning the owner's public key accepts an honest package. |
| tampered | open | FAIL | S4 evidence integrity | One line appended to `evidence/files/report.txt` after sealing. |
| deleted | open | FAIL | S4 evidence integrity | `evidence/files/report.txt` removed; the index still declares it. |
| keyswap | open | PASS | — | Attacker-built package, sealed with the attacker key: internally consistent, so it verifies against itself. |
| keyswap | `--pubkey keys/owner.key.pub` | FAIL | S6 seal signature | The seal's key does not match the pinned owner key. |
| unsigned | open | INCONCLUSIVE | S6 seal signature | No seal: internally consistent, provenance unattested. A verifier that says PASS here cannot tell signed from unsigned. |
| unknown-upgrade | open | INCONCLUSIVE | S6 seal signature | The manifest declares `status: PASS` and there is no seal. Self-declaration is not evidence and must not upgrade a verdict. |
| full | `--expect-head sha256:bd646e83…` | PASS | S9, S10, S13, S14, S15, S16, S17, S18 | The package carries all six closure components, a Merkle tree with proofs for both leaves, a two-receipt chain, an anchor that resolves against its own tree, and a policy digest over the JCS of the shipped artefact; the head is pinned out of band. The external timestamp is a real RFC 3161 token from Sectigo, verified offline by `tools/check_tsa.py` against the CA bundle shipped in the package; it dates existence, not correctness. |

## Why row 5 is written as PASS

A verifier that cannot be fooled costs nothing to trust; a verifier that can be fooled, and says so in a row of its own matrix, tells you exactly which question it answers. Open-mode PASS answers "these bytes are consistent with each other". It does not answer "the owner produced them".

## Reproduction

```bash
python tools/make_vectors.py --work vectors   # rebuild (hashes change; timestamps differ)
python tools/run_vectors.py                   # confirm the six rows still hold
```

Rebuilding rewrites the packages, so committed hashes and a fresh rebuild will not match byte for byte — timestamps are real. The gate compares verdicts, not bytes.

Committed bytes, however, must be stable, because receipts hash them. The fixture files carry CRLF, so a renormalisation would move every digest. `.gitattributes` declares `vectors/`, `receipts/` and `keys/` non-text: no platform re-encodes them, and `git add --renormalize` cannot silently rewrite the fixtures the receipts describe.

## Known gaps

- No third-party implementation has been run against these vectors. The only verifier exercised here is the reference one.
- No reordering or rollback vector yet; rollback needs an external monotonic anchor (`--expect-head`) and cannot be shown inside one package.
- **D-002, verified 2026-11-24**: the S7 index-metadata digest covers `path`, `content_hash`, `type` and `note`, but **not** `evidence_id`, `media_type` or `created_at`. Rewriting any of those three in `evidence/index.json` leaves the verdict at **PASS**. Consequence: evidence can be backdated and its identifier swapped without detection. Reproduce with `python tools/run_adversarial.py` (rows `index-metadata-drift`, `evidence-id-drift`, `media-type-drift`); `--strict` fails until it is fixed. Filed against `uibc-core` 0.5.0.
- **Upstream defect (Windows)**: `uibc-core` 0.5.0 prints Chinese `basis.note` strings and crashes with
  `UnicodeEncodeError: 'charmap' codec` on a cp1252 console. Run 1 of this repo's CI went
  **red on both Windows jobs** for exactly this reason. Our workflow sets `PYTHONIOENCODING=utf-8`,
  which is a runner-side workaround, not a fix to the package. Reported upstream: pending.

## Cross-version: what an older verifier says

The rows above are the answer **at or above the declared floor** (`min_verifier_version: 0.5.0` in every manifest). Below the floor the corpus accepts two answers, `INCONCLUSIVE` and `FAIL`, because both are honest; it refuses only `PASS`. `VERSION-MATRIX.md` is the generated table, `crossversion-results.json` the machine copy.

```bash
python tools/run_crossversion.py --also /path/to/python-with-0.4.1
```

Measured on 2026-11-24: `uibc-core` 0.4.1 answers `INCONCLUSIVE` on `clean` in both modes. That is not a regression — it is the floor working. An old verifier declining to call the corpus's own positive anchor healthy is the behaviour a version floor exists to produce; the cell that would be alarming is `PASS` there.

## Frozen fixtures

`FIXTURES.sha256` records one SHA-256 per committed fixture file across the six packages. `python tools/check_frozen.py` recomputes them; CI runs it on every push. Adding or changing a fixture therefore requires an explicit `--write` and a visible diff, which is the point: a vector set that changes silently is not a vector set.

## Claim checking

`tools/check_report.py` applies four rules to any verifier report before it is quoted: PASS over a FAIL/INCONCLUSIVE check (R1), `assurance=attested` without S6 PASS (R2), `trust_level=anchored|witnessed` without S6 PASS (R3), and a package whose `manifest.status` claims PASS while the verdict is not (R4). `--selftest` builds four doctored reports and one honest one; the four must be rejected.

## Adversarial supplement

Twelve doctored packages, built at run time from `vectors/clean`, never committed (so the freeze above is untouched):

| Case | Expected | Defect |
|---|---|---|
| dup-json-member | FAIL | S11 |
| control-char | FAIL | S11 |
| extra-root-file | FAIL | S1 |
| index-path-escape | FAIL | S1/S4 |
| hash-flip | FAIL | S4 |
| ts-rollback | FAIL | S3 |
| seq-gap | FAIL | S3 |
| unsigned | INCONCLUSIVE | S6 |
| status-upgrade | INCONCLUSIVE | declaration ≠ evidence |
| index-metadata-drift | **PASS today** | D-002 |
| evidence-id-drift | **PASS today** | D-002 |
| media-type-drift | **PASS today** | D-002 |

Nine must be rejected. Three reproduce D-002 and are reported as defects, not counted as passes.
