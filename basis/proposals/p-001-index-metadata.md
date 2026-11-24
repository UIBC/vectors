# Proposal: a digest over index metadata, not just over content

**Status:** draft, not sent. · Check affected: S7 · Filed against: SCITT agent-receipt work (`draft-noa-scitt-ai-agent-receipt`, `draft-marques-asqav-compliance-receipts`) · Date: 2026-11-25

## The problem, in one paragraph

An evidence package hashes its content and commits to those hashes. The index that *lists* the content — ids, media types, creation timestamps, sizes — is usually covered only indirectly, if at all. An attacker who can edit the index can therefore change what a verifier believes was attested without touching a single content hash: swap an `evidence_id`, relabel a `media_type`, backdate a `created_at`, and every digest in the package still recomputes exactly. The verifier reports "evidence intact" while describing different evidence.

This is not hypothetical for us: it was a real defect in our own verifier (written up as D-002 in `UIBC/vectors`), found by an adversarial case, and fixed by a second commitment over the metadata the seal never covered. Upstream fix: `zhaoxinghua09-cell/uibc-core` PR #431 (`fix/index-full-digest`).

## Why it is worth a line in a draft

Every profile that says "the receipt commits to the evidence" leaves this open, because the commitment is over bytes and the index is not bytes. Three consequences follow, and none of them is exotic:

1. Two verifiers can reach opposite verdicts on the same package if one checks index integrity and the other does not — and nothing in the text says which is right.
2. An auditor cannot tell "the evidence was not changed" from "the list of evidence was not changed", which is the question a retention regime actually asks.
3. A negative test suite cannot be written, because the requirement it would test is unstated. Our own corpus could not test it until we had written the check ourselves.

## Proposed text (for discussion, not a demand)

> Where a receipt or package commits to a set of evidence items, the commitment MUST cover, for each item, the tuple of (identifier, media type, creation timestamp, size) in addition to the content digest, or the package MUST carry a separate digest over the index that lists those tuples. A verifier that recomputes content digests without covering the index has not verified the package's evidence set.

Two shapes are offered deliberately: the first folds the metadata into the existing commitment (simplest for producers, changes the commitment's definition), the second adds an index digest (compatible with existing commitments, one more field). We implement the second and do not claim it is the better one.

## What we already have that could be donated

- A working second commitment: `closure`/`index_digest` in our package format, sealed after `submit` (a builder-ordering bug we hit and fixed — the manifest is rebuilt by `submit`, so the extra commitment must be written *after* it, not before).
- An adversarial case that fails without it: rewriting `evidence_id`, `media_type` and `created_at` while leaving content digests intact, expected to be rejected by the index check specifically.
- A demonstration that the first fix attempt can be silent: our first version wrote the commitment before the manifest was rebuilt, and the field was discarded with no error. Any proposal should require the verifier to report the *index* check as the deciding one, not merely a non-zero exit.

## What we are not claiming

We are not claiming to be first to notice metadata malleability, and we are not asking that our field names be adopted. The ask is narrower: that the requirement be *stated somewhere*, so that "index not covered" becomes a named failure rather than an implementation detail.

## What we ask

1. Whether this belongs in the agent-receipt draft as a requirement, or as a security-consideration paragraph with an example.
2. If a requirement: whether to fold metadata into the content commitment or to add a separate index digest — and whether the tuple above is the right minimum (we would accept fewer fields if the draft prefers).
3. If a consideration: whether a worked example (edit `created_at`, all digests still verify) is useful enough to include.

## Cost of being wrong

If the community decides the index is the transport's problem rather than the receipt's, we keep the check in our own corpus and record that it has no external basis — which is what `BASIS.md` already says today. Nothing here is a claim on anyone's time.
