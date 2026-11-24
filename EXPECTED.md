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
- **Upstream defect (Windows)**: `uibc-core` 0.5.0 prints Chinese `basis.note` strings and crashes with
  `UnicodeEncodeError: 'charmap' codec` on a cp1252 console. Run 1 of this repo's CI went
  **red on both Windows jobs** for exactly this reason. Our workflow sets `PYTHONIOENCODING=utf-8`,
  which is a runner-side workaround, not a fix to the package. Reported upstream: pending.
