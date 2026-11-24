# submissions — where a stranger's run becomes a row

A submission is judged by `tools/check_submission.py`, not by whoever reads the
pull request first. Add one directory here; CI runs the same script.

You do not have to assemble the directory by hand:

```
python tools/make_submission.py --id <legal-entity>-<impl>-<date> \
    --legal-entity "Example Devices GmbH" --implementation example-verifier \
    --language Rust --repository https://github.com/example/verifier \
    --contact security@example.com --date 2026-11-25 \
    --competence "Test laboratory: TÜV Example, ISO/IEC 17025 accredited, cert 12345"
python tools/check_submission.py
```

The generator runs the matrix gate itself and copies its stdout into `run.log`
verbatim; it refuses to write anything when that gate fails, because a
submission built from a run that disagrees with the corpus is a record of
nothing. It does not decide independence or competence for you — a generator
that filled those in would be the disease, not the cure.

The first row here was written by hand once, and that was the last time:

```
python tools/make_submission.py --id uibc-self-20261124 --reproduce
SUBMISSION REPRODUCED - the committed files are byte-identical to a fresh run of this corpus.
```

`--reproduce` rebuilds the submission from the corpus as committed and compares
bytes. A hand-edited verdict, a stale log, a corpus that moved under a
committed row — all three show up as `SUBMISSION STALE`, and CI runs it.

```
submissions/<legal-entity>-<impl>-<date>/
├── product.json     who is accountable, what was run, and how independent it is
├── results.json     one row per frozen case, plus the corpus digest it ran against
└── run.log          the unedited stdout of the runner
```

## product.json

```json
{
  "legal_entity": "Example Devices GmbH",
  "implementation": "example-verifier",
  "version": "1.4.0",
  "language": "Rust",
  "repository": "https://github.com/example/verifier",
  "checks": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S11", "S12"],
  "scope": {"not_covered": ["S9", "S10", "S13", "S14", "S15", "S16", "S17", "S18", "S19"]},
  "contact": "security@example.com",
  "independence": "independent",
  "competence_basis": "Test laboratory: TÜV Example, ISO/IEC 17025 accredited, cert 12345",
  "witness": {"name": "A. Reviewer", "role": "notified body reviewer", "independent_of_submitter": true},
  "submitted_at": "2026-11-25"
}
```

`independence` is one of two words. `independent` means a different maintainer
wrote the verifier from the specification text; `same-maintainer` means one of
us. The validator refuses `independent` from this organisation's own legal
entity, because a self-submission is not a second opinion.

Three fields exist because a reviewer asks them before asking whether anything
passed. They are required to be **answered**, not to be favourable:

- `competence_basis` — who ran it and on what standing. A laboratory with an
  accreditation number, a named individual with a qualification, or the literal
  `none`. Omitting the field is refused; writing `none` is accepted, because an
  honest absence is checkable and an omission is not.
- `witness` — `null` or an object naming who watched. The **key** must be present
  even when the value is `null`: "no witness" and "we did not think about it" are
  different statements. When it is an object, it must also ship a signed
  statement — see below.
- `scope.not_covered` — every check id you do not claim. Silence about a check
  reads as coverage, so the validator requires all of S1–S19 to be either
  claimed or disclaimed, exactly once.

## results.json

```json
{
  "contract_version": "uibc-submission-results/1",
  "corpus_digest": "<sha256 of FIXTURES.sha256 as committed>",
  "verifier": {"id": "...", "version": "...", "command": "..."},
  "rows": [{"case": "clean", "mode": "open", "verdict": "PASS", "exit_code": 0}]
}
```

The digest ties a result set to a corpus version, not to a date. A submission
produced against an older corpus is not refused for being old; it is refused for
claiming a digest it did not run against.

## A witness is a signed statement, not a name

A name in a JSON field costs nothing to type, so naming a witness and stopping
there is refused. If `witness` is an object, the submission carries:

```
submissions/<id>/witness/
├── statement.json     what the witness says they watched, signed by them
└── witness.key.pub    their 32-byte Ed25519 public key, hex
```

```json
{
  "contract": "uibc-witness-statement/1",
  "witness": "D. Reviewer",
  "role": "notified-body reviewer",
  "attests": "Watched the eight-row run reproduce on this corpus and read the log as it was produced.",
  "corpus_digest": "<the same digest as results.json>",
  "witness_pubkey": "<64 hex characters, matching witness.key.pub>",
  "observed_at": "2026-11-25T09:12:00Z",
  "signature": "<128 hex characters over the canonical bytes of this object without 'signature'>"
}
```

Four things are checked: the signature verifies against the shipped key, the
statement names the same person as `product.json`, it attests to the **same**
`corpus_digest` as the results it accompanies, and its `attests` text says what
was watched rather than that something was. A witness to a different run is a
witness to nothing here.

The witness key may not be one of the keys this repository publishes, and may
not be the submitter's declared key. **Identity is checked before the
signature**, because the attack this rule exists for is a submitter signing for
their own witness.

What this proves: the statement came from a key the submitter does not hold.
What it does not prove: that the named person exists, watched anything, or is
accredited. A signature is an identity, not a credibility. We can refuse
self-witnessing; we cannot turn a stranger into a notified body.

## The rules the script enforces

| rule | what it refuses |
|---|---|
| S1 | a missing `product.json`, `results.json` or `run.log` |
| S2 | a product record missing legal entity, version, contact, checks |
| S3 | `independent` claimed by this organisation's own entity |
| S4 | a corpus digest that does not match the corpus committed here |
| S5 | a missing case, a re-scored case, a duplicated case, an invented case |
| S6 | a log under 200 bytes, or one that does not name the cases it ran |
| S7 | a check id outside S1–S19 |
| S8 | `competence_basis` missing, empty, or too short to identify a standing |
| S9 | the `witness` key absent, or a witness without a name or an independence flag |
| S10 | a check neither claimed nor disclaimed, or claimed twice, or a disclaimed id that does not exist |
| S11 | a named witness without a signed statement, a bad signature, a statement naming another person, or one attesting to a different corpus |
| S12 | a witness key that this repository publishes, or that equals the submitter's own key |

Rule numbers here are the script's namespace; the `checks` array uses the
verifier's ids (`S1`–`S19`). They share digits and nothing else.

`python tools/check_submission.py --selftest` breaks the format thirteen ways
and requires all thirteen to be caught — plus one properly signed witness that
must still be accepted, so the rule is a check and not a wall.

## What is in here now

One directory: `uibc-self-20261124`, by this corpus's own author, labelled
`same-maintainer`. It exists so the format is exercised by a real run instead of
by an empty directory, and so the first row in the table is honestly ours.

**External submissions: 0.** That number is the one that matters, and nothing in
this directory changes it. The one row ships `witness: null`, which is the only
honest value it can ship: we have no signed statement from anyone outside this
organisation, and a name typed into the field would have been refused.

## What acceptance means

That the bytes you shipped describe the same verdicts this corpus records, against
the corpus version you named. It does not certify your product, and it is not a
badge. There is no badge.
