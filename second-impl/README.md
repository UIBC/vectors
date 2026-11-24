# second-impl — a third verifier, and why it exists

**Read this first: the corpus already had a second implementation, and this
file is not it.**

`zhaoxinghua09-cell/uibc-core` has shipped `tools/verify-js/verify.mjs` since
2026-11-18: JavaScript, no shared code, covering 18 of the 19 checks, enforced
by `tools/assert_second_impl.py` and the `second-implementation` CI job, measured
at `strict 36/36, refused 30/36`. Its design notes — including the rule that
**S5 must not report PASS when S4 has failed**, which this directory's first run
re-derived the hard way — are in
[`docs/SECOND-IMPLEMENTATION.md`](https://github.com/zhaoxinghua09-cell/uibc-core/blob/main/docs/SECOND-IMPLEMENTATION.md).

So why a third one, inside the public corpus repository?

Because the public repositories could not answer the question a stranger asks
first: *"can I run this corpus with what I already have?"* The answer used to
be no — replay required Python, a `pip install uibc-core`, and reading a
different repository. `node second-impl/verify.mjs vectors/clean` answers with
Node alone, against the bytes that are public here.

| | uibc-core `verify-js` | this |
|---|---|---|
| checks covered | 18 of 19 | 10 of 19 (S1–S8, S11, S12) |
| enforced in CI | `assert_second_impl.py` | `tools/run_crossimpl.py` + `check_implementations.py` |
| corpus | the private suite, 36 packages | the public suite, 20 rows (8 frozen + 12 adversarial) |
| runtime needed | Node | Node (no Python for the verifier; Python for the runner) |
| independence | same-maintainer | same-maintainer |

Nothing here is better than `verify-js` except reachability. Two verifiers
covering different check subsets, both honest about it, beat one verifier and
a paragraph claiming the subset is fine.

## What the first run actually produced

```
CROSSIMPL OK - 20/20 verdicts agree; 182/182 per-check results agree across 10 checks.
```

Getting there took one correction. On `tampered`, `deleted` and `hash-flip`,
verdicts agreed but seven per-check cells did not: the reference reports S5 as
INCONCLUSIVE and S8 as FAIL, this implementation reported PASS for both. Both
were arithmetically defensible — and the specification text never said whether
the evidence root is computed over bytes on disk or over hashes that
`evidence/index.json` claims. The reference computes it over on-disk bytes,
because a root that matches only because the index is lying is not a PASS.

That is the same defect `uibc-core` recorded as bug 3 of four in
`docs/SECOND-IMPLEMENTATION.md`. Re-deriving it from the other side is not a
discovery; it is a check that the documentation is accurate, and it cost one
run rather than one argument.

## Scope as a list, because a percentage would hide it

S1 structure · S2 identity · S3 lifecycle chain · S4 evidence integrity ·
S5 evidence root · S6 seal (Ed25519, legacy and lifecycle-bound payloads,
`--pubkey` pinning) · S7 index metadata · S8 checkpoint · S11 strict
serialization · S12 timestamps and identifiers.

Not covered: S9, S10, S13–S19 — anchors, merkle proofs, RFC 3161 tokens and
policy artefacts, none of which appear in the committed fixtures here.

## What this is not

Not independent — same maintainer. `../implementations.json` records that field
for every implementation and `tools/check_implementations.py` refuses the word
"independent" from this organisation's own address. Independence needs a
different person; the external verifier count is still zero.
