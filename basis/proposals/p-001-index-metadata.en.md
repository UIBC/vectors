# A digest over index metadata, not just over content

**Draft for comment — not filed.** Affects: an agent-evidence package's own index. Related drafts: `draft-noa-scitt-ai-agent-receipt`, `draft-marques-asqav-compliance-receipts`. Date: 2026-11-25.

## Problem

A receipt package commits to content by hashing it. The index that *lists* that content — identifiers, media types, creation timestamps, sizes — is typically covered only indirectly. An editor who can change the index can therefore change what a verifier believes was attested without touching a single content hash: substitute an identifier, relabel a media type, backdate a creation time, and every digest still recomputes exactly. Verification reports that the evidence is intact while describing different evidence.

We did not find this in theory. It was a defect in our own verifier, found by an adversarial case, and closed by adding a second commitment over the metadata the seal never covered.

## Why it merits text

Three consequences follow, none exotic:

1. Two verifiers can reach opposite verdicts on the same package — one checks index integrity, one does not — and no published text says which is correct.
2. An auditor cannot distinguish "the evidence did not change" from "the list of evidence did not change", which is the question a retention regime actually asks.
3. A negative test cannot be written, because the requirement it would test is unstated.

## Prior art

`getaskclaw/multi-agent-dialogue-protocol` issue #5 derives an evidence index on demand and keeps a tamper canary that fails a report and a validator independently. The idea is not new and this draft does not claim it. What is absent is a normative sentence: an implementation that omits the index check fails no published requirement today.

## Proposed text (for discussion)

> Where a receipt or package commits to a set of evidence items, the commitment MUST cover, for each item, the tuple of (identifier, media type, creation timestamp, size) in addition to the content digest, **or** the package MUST carry a separate digest over the index that lists those tuples. A verifier that recomputes content digests without covering the index has not verified the package's evidence set.

Two shapes are offered deliberately: folding metadata into the existing commitment (simplest for producers; redefines the commitment) or adding an index digest (compatible with existing commitments; one more field). We implement the second and do not claim it is preferable.

## Implementation note worth carrying

Our first attempt wrote the extra commitment *before* the package builder rebuilt the manifest, and the field was discarded silently. Any requirement should therefore also say that the verifier must report the **index** check as the deciding one, not merely exit non-zero — otherwise a builder ordering bug reads as compliance.

## Open questions

1. Requirement, or a security-consideration paragraph with a worked example?
2. If a requirement: fold metadata into the content commitment, or add a separate index digest?
3. Is the tuple above the right minimum? We would accept fewer fields if the draft prefers.
4. Does any existing profile already state this under different vocabulary?

## Cost of being wrong

If the community decides the index is the transport's responsibility rather than the receipt's, we keep the check in our own corpus and record that it has no external basis — which is what our published table already says today. Nothing here is a claim on anyone's time.
