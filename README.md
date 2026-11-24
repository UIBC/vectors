# UIBC conformance vectors

Seven executable packages and ten rows that show what a UIBC verdict is allowed to mean, and where it stops. Every row is produced by `tools/make_vectors.py` / `tools/make_adverse.py` and checked by `tools/run_vectors.py` against a hand-written expectation table.

```bash
pip install uibc-core==0.5.0 asn1crypto cryptography
python tools/run_vectors.py        # exits 0 only when all ten rows hold
python tools/run_adversarial.py    # 9 must-reject cases + 3 documented gaps
python tools/check_frozen.py       # fixture bytes vs FIXTURES.sha256
```

No network, no credentials, no owner key: the seals are Ed25519, and the public key travels inside each package.

## The ten rows

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
| `full` | `--expect-head <head>` | PASS | closure, Merkle tree, receipt chain, anchor set, policy map, a **real Sectigo RFC 3161 timestamp** and an out-of-band head pin all hold (S9, S10, S13, S14, S15, S16, S17, S18) |
| `full` | `--expect-head` + `--state-file` | INCONCLUSIVE | a first freshness observation has nothing to compare against — never PASS (S19) |

The fifth row is not a defect report, it is the boundary: **unpinned verification proves internal consistency, not authorship**. Anyone quoting a UIBC PASS without saying whether the key was pinned is quoting half a result.

The last two rows are that boundary seen from the other side. A verifier that answers PASS for an unsigned package cannot tell "signed" from "declared", and a package that declares its own PASS has produced no evidence at all.

The two `full` rows exist because most checks are opt-in: they speak only when a package carries the artefact or the caller passes the flag. A matrix made of the first eight rows teaches a submission to claim ten of nineteen checks — not because it is hiding anything, but because the corpus never gave the verifier the inputs. `tools/make_full.py` builds the package; the pin is the checkpoint the package itself declares, so a drifted head breaks that row rather than passing quietly. Two limits are stated in that builder: S10 checks only that all six closure components were *declared with a digest*, and S15 resolves an anchor against the tree the package can recompute — neither is a claim about model contents or a third-party log.

**S16 is the one witness in this corpus we cannot mint.** `evidence/external_anchor.json` carries an RFC 3161 token issued by Sectigo's public TSA over the sealed `manifest.json` (gen_time is inside the token, not in the repo's prose), plus the CA bundle needed to check it. `tools/check_tsa.py` re-verifies it **offline** on every push: messageImprint, chain to the shipped bundle, signature. It dates existence, not correctness — a timestamp says these bytes existed at gen_time and says nothing about whether the checks below them pass. Network is needed once, in `tools/make_external_anchor.py`; everything after that runs without it.

## Adversarial supplement (separate from the frozen matrix)

`tools/run_adversarial.py` builds seventeen doctored packages at run time and requires them not to verify: duplicate JSON member, raw control character, undeclared root file, index path escape, byte appended after sealing, timestamp rollback, sequence gap, unsigned, self-declared PASS, a wrong head pin, an incomplete closure, non-canonical base64, a bad Merkle proof, a broken chain link, an unresolvable anchor, an unreadable freshness state, an unresolvable policy digest — and three index-metadata rewrites.

The last three are a genuine finding, not a passing test. **D-002**: the S7 index-metadata digest covers `path`, `content_hash`, `type` and `note`, but not `evidence_id`, `media_type` or `created_at` — those three can be rewritten while the verdict stays PASS. They are printed as `[DEFECT]`, the run stays green only while the defect still reproduces, and `--strict` fails until it is fixed. A gap that quietly stops reproducing turns the run red, so the ledger cannot rot.

## Files

- `vectors/` — the seven packages (committed, small, plain JSON + text)
- `FIXTURES.sha256` — one digest per committed fixture file; `check_frozen.py` compares
- `keys/` — TEST-ONLY Ed25519 seeds and their public keys. The seeds are public on purpose so `keyswap` can be rebuilt by anyone. Never reuse them.
- `tools/make_vectors.py` — regenerates all four cases through the public CLI
- `tools/run_vectors.py` — the gate; ten rows, exit 1 on any deviation
- `tools/make_receipt.py` — runs the six rows and writes a receipt with per-case byte digests
- `tools/check_receipt.py` — re-derives those digests from this repo and rejects a receipt whose bytes moved
- `EXPECTED.md` — the same table with the verifier version and the check that fired
- `VERSION-MATRIX.md` — the same rows answered by an older verifier (0.4.1), and why its `INCONCLUSIVE` on `clean` is the version floor working rather than a regression; `tools/run_crossversion.py` regenerates it, CI fails if it goes stale
- `RUNS.md` — the ledger; currently one author row, zero external runs

## Send back a receipt

```bash
pip install uibc-core==0.5.0 asn1crypto cryptography
python tools/make_receipt.py --runner "<your handle>" --blind yes|no --code independent|author
python tools/check_receipt.py receipts/<file>.json     # must print ACCEPTABLE
```

Then open an *Independent run receipt* issue with the file. A receipt is a record that a run happened on bytes that still hash to what you recorded — it is **not** a claim that the runner exists, and it does not by itself make this project externally verified. It is how a first external row gets written down instead of asserted.

### Do not renormalise the fixtures

The committed fixture files carry CRLF (they were written on Windows), and a receipt hashes their bytes. Any renormalisation — `git add --renormalize`, or an editor that rewrites line endings and commits — moves every digest and turns a valid receipt into a rejected one. `.gitattributes` declares `vectors/`, `receipts/` and `keys/` non-text so that cannot happen by accident. If `check_receipt.py` rejects a receipt the build did not touch, suspect the working bytes before the receipt: compare `git hash-object` of the file with `git rev-parse HEAD:<path>`.

```bash
pip install uibc-core==0.5.0 asn1crypto cryptography
python tools/stranger.py           # every gate, timed, with a machine-readable record
```

`tools/stranger.py` is the short version of this whole README: it runs each gate, compares the output against a declared line, writes `stranger-run.json`, and exits non-zero if any gate is missing or mismatched. Ten seconds from a fresh clone. Passing it means the repository is self-consistent — not that it is conformant, and not that anyone has reviewed it.

## Everything a stranger can run, and what each one proves

`python tools/stranger.py` runs all of it and writes `stranger-run.json`: each gate's argv, exit code, duration and the line that carries its promise. Measured 2026-11-25 on one machine: 14 gates, 27.8 s.

| command | expected line |
|---|---|
| `python tools/run_vectors.py` | `MATRIX GATE OK - all 10 rows match.` |
| `python tools/run_adversarial.py` | `ADVERSARIAL OK - 17/17 must-reject cases rejected; 3 documented gap(s) still reproduce.` |
| `python tools/check_frozen.py` | `FROZEN OK - 67 fixture files match FIXTURES.sha256` |
| `python tools/check_tsa.py` | `TSA CHECK OK - 1 external token(s) verify offline …` |
| `python tools/check_external_runs.py` | `EXTERNAL RUNS OK - 0 verified record(s) …` |
| `python tools/check_external_runs.py --selftest` | `EXTERNAL RUNS SELFTEST OK - 7 ledger(s) judged as expected` |
| `python tools/check_submission.py` | `SUBMISSIONS OK - 1 submission(s), all matched the frozen corpus.` |
| `python tools/check_submission.py --selftest` | `SUBMISSION SELFTEST OK - 15/15 doctored submissions rejected, 1 properly signed witness accepted.` |
| `python tools/check_report.py --selftest` | `REPORT SELFTEST OK - 4/4 doctored reports rejected, 1 honest report accepted` |
| `python tools/check_key_hygiene.py` | `KEY HYGIENE OK - … no seed outside keys/` |
| `python tools/make_submission.py --id uibc-self-20261124 --reproduce` | `SUBMISSION REPRODUCED` |
| `python tools/coverage_map.py --check` | `COVERAGE OK - 19/19 matrix, 19/19 any case, 16/19 deciding, 0 unreached.` |
| `python tools/basis_map.py --check` | `BASIS OK - 5 direct, 9 related, 5 ours; every citation resolves.` |
| `python tools/check_quotes.py --check` | `QUOTES OK - 14 quoted sentence(s) for 5 direct + 9 related check(s), verbatim in the cached copy.` |
| `python tools/run_crossversion.py --also <python-with-0.4.1>` | `CROSSVERSION OK - 2 verifier(s) x 10 rows` |

The last line needs a **second** interpreter: with only one, the floor cannot be exercised and the tool exits 3 with `CROSSVERSION DEGENERATE`, rather than printing a green that certifies nothing. That refusal is deliberate — the same reason `run_adversarial.py` prints `[DEFECT]` instead of hiding D-002.

Three rows of machinery are **not on this branch**: the third verifier (`second-impl/verify.mjs`), the per-check cross-implementation replay, and `implementations.json`. They live on `feat/crossimpl-and-manifest` and cannot be run from `main` until that lands. Saying so here is cheaper than having a stranger discover it.

## Asking somebody else to run it, and keeping the count honest

`python tools/make_repro_request.py` writes `outreach/repro-request-<date>/`: one command to run, the exact line each gate must print, the corpus digest those lines belong to, and a `reply-template.json` with fixed fields. Nothing in it contacts anybody - issuing a request is ours, sending it is the maintainer's.

`registry/external-runs.json` is the ledger, and `python tools/check_external_runs.py` makes its headline a **derived** number: it must equal the number of records that are complete, name a log whose SHA-256 matches, carry this repository's corpus digest, and are not byte-identical to our own `submissions/*/run.log` (a re-run on another machine does not reproduce our bytes). A failing run stays in the ledger as a failure and does not raise the count. `--selftest` proves all of it on seven doctored ledgers, including one that types a headline with no record behind it.

**The number today is 0.** That is not a placeholder; it is the gate refusing to let us say anything else.

## Where the nineteen checks come from

`BASIS.md` publishes the split, per check, from the verifier's own `basis` fields: **5 direct, 9 related, 5 ours.** *Direct* means an external document states the requirement; *related* means the mechanism is borrowed and the requirement is ours; *ours* means there is no external text behind it at all.

This is the first question a corpus that grades itself has to answer, and "19 checks" alone invites the assumption that all nineteen were mandated. Each citation resolves through `basis/sources.json`, where every entry carries the URL and the date it was fetched; a citation that is not there, a `direct` claim with no citation, or a `none` claim that cites something, all fail the gate. **Six of the eleven sources are individual Internet-Drafts, not consensus standards, and eight of the nineteen checks rest on them** — `BASIS.md` says so in the same table, because citing a proposal and citing a rule are different claims.

`QUOTES.md` goes one step further for all fourteen checks that claim an external basis (5 `direct`, 9 `related`). It prints the sentence each one rests on, and `tools/check_quotes.py` matches that sentence character for character against a cached copy of the document, whose digest is recorded too. A paraphrase cannot pass as a quotation, and the check runs offline — no network, no trust in us. For a `direct` check the sentence is the requirement; for a `related` one it is only the mechanism we borrowed, and `QUOTES.md` separates the two classes rather than letting one table imply the other. The gate already earned its keep: it found that the S18 citation names §4.2.4 of a draft that has no §4.2.4 (the rule is §4.2.2). The correction is recorded in `basis/quotes.json` and printed in `QUOTES.md`; the verifier's citation string is an upstream fix.

## Scope

These vectors demonstrate detection within the observed evidence boundary of `uibc-core` 0.5.0. They do not prove the absence of undetected attacks, and they are not a conformance suite for third-party implementations — that suite does not exist yet.

Licence: Apache-2.0.
