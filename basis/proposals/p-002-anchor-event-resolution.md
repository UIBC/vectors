# Proposal: how a verifier resolves an anchor event

**Status:** draft, not sent. · Check affected: S15 · Filed against: SCITT time-anchor work (`draft-fassbender-scitt-time-anchor`) · Date: 2026-11-25

## The problem

Time-anchor drafts say why you anchor and what an anchor proves. They are much quieter about the step between: given an anchor that points at a transaction, how does a verifier turn that into "the root I hold is the root that was anchored"? In practice each implementation invents this, and the inventions disagree in ways that matter:

- Does the verifier trust the anchor service to hand it the transaction, or must it re-derive the commitment from the transaction itself?
- What is the identity of the anchored object — a file digest, a Merkle root, a serialized manifest, or a commitment to one of those? Two implementations can anchor "the same" package and produce anchors that neither can verify.
- When the transaction contains several outputs or a payload commitment, which field is the commitment, and what happens when none of them matches?
- Is a resolved-but-mismatched anchor an error, a refusal, or an inconclusive verdict?

Our verifier had to answer all four for itself. The answers are ours, which is why S15 is `none` in `BASIS.md` — and the fact that the answer had to be invented is the argument for saying it somewhere.

## Proposed text (for discussion)

> An anchor is *resolved* when the verifier, without trusting the anchor service's summary, derives the anchored commitment from the anchor artefact itself and compares it to the commitment it computed over its own object. A verifier MUST treat a resolved anchor whose commitment does not match as a failure of that object, not as a missing anchor. A verifier MUST NOT treat an unresolvable anchor as evidence that the object is unanchored; the verdict is "not established", and the three states (anchored, mismatch, not established) MUST be distinguishable in the verification result.

The last sentence is the part we would most like to see somewhere. Collapsing "could not resolve" into "failed" is convenient and wrong in the direction that matters: it lets a broken anchor feed read as tampering, and a tampering feed read as a network problem.

## What we already have that could be donated

- An offline resolver that walks the anchor artefact and recomputes the commitment, with a shipped CA bundle and an RFC 3161 token from a public TSA (`vectors/full/evidence/external_anchor.json`).
- A three-valued verdict in the corpus: the same package reads PASS, FAIL or INCONCLUSIVE depending on what the anchor can establish, and the INCONCLUSIVE row is a first observation rather than a pass (`vectors/full` + `--state-file`).
- A negative case where the anchor is present but points at a different root — rejected by the anchor check specifically, not by a generic signature failure.

## What we are not claiming

Not that OpenTimestamps or RFC 3161 verification is unspecified — both specify their own verification. The gap is the *binding* step between "this transaction is confirmed" and "this root is what the transaction commits to", which is where implementations diverge and where a test suite has nothing to assert.

## What we ask

1. Whether anchor resolution deserves a normative paragraph, or a short "verification considerations" section with the three states named.
2. Whether the three-state vocabulary (anchored / mismatch / not established) is acceptable, or whether existing SCITT verdict terminology already covers it under another name.
3. Whether a small worked example (anchor present, commitment differs, verdict is mismatch rather than not-established) would help.

## Cost of being wrong

If the community says this is the anchor format's business rather than the receipt's, S15 stays `none` in our table and the proposal stays a proposal. We would rather have asked than have four implementations answer differently and call it interoperability.
