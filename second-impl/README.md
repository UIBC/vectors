# second-impl — a verifier in another language, on purpose

```
node second-impl/verify.mjs vectors/clean
node second-impl/verify.mjs vectors/clean --pubkey keys/owner.key.pub
node second-impl/verify.mjs vectors/tampered --json
```

Node 22, zero dependencies, no shared code with `uibc-core`. It reads the
package with `node:crypto` and RFC 8785 canonicalization done from scratch
(sorted `JSON.stringify`), and answers PASS / FAIL / INCONCLUSIVE with the same
exit-code convention as the reference CLI.

## Scope, stated as a list because a percentage would hide it

| check | here | note |
|---|---|---|
| S1 structure | yes | undeclared root entries rejected |
| S2 identity consistency | yes | |
| S3 lifecycle chain | yes | sequence, previous_event, monotonic timestamps |
| S4 evidence integrity | yes | hash of bytes on disk |
| S5 evidence root | yes | over bytes on disk; skipped (INCONCLUSIVE) when S4 fails |
| S6 seal signature | yes | Ed25519; legacy and lifecycle-bound payloads; `--pubkey` pinning |
| S7 index metadata digest | yes | |
| S8 checkpoint head | yes | |
| S11 strict serialization | yes | duplicate member names, raw control characters |
| S12 timestamps and ids | yes | RFC 3339 with zone, lowercase UUIDs |
| S9, S10, S13–S19 | no | anchors, merkle proofs, RFC 3161, policy artefacts — absent from the fixtures |

## What this is not

It is **not an independent implementation**. Same maintainer, different language.
`../implementations.json` records that field for both implementations and
`tools/check_implementations.py` refuses the word "independent" from this
repository's own address. Independence would mean a verifier written by someone
who never read this code; until that exists, every number quoted from
`interop-results.json` carries `same-maintainer`.

## A divergence this file caught, kept because it is the useful part

On the first cross-run, verdicts agreed 20/20 but seven per-check cells did not:
on `tampered`, `deleted` and `hash-flip`, the reference reported S5 as
INCONCLUSIVE ("skipped: evidence missing or S4 failed") and S8 as FAIL, while
this implementation reported PASS for both.

Both were arithmetically defensible — and that was the problem: the specification
text did not say whether the evidence root is computed over the bytes on disk or
over the hashes that `evidence/index.json` claims. The reference computes it over
bytes on disk, so a root that matches only because the index is lying is not a
PASS. This implementation now does the same, and the rule is stated where a
reader meets it, not only in a commit message.

A cross-implementation run that can only ever say "agree" is decoration. The
disagreement is the finding; the agreement is the regression test that keeps it
fixed.
