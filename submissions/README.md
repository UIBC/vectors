# submissions — where a stranger's run becomes a row

A submission is judged by `tools/check_submission.py`, not by whoever reads the
pull request first. Add one directory here; CI runs the same script.

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
  different statements.
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

`python tools/check_submission.py --selftest` breaks the format nine ways and
requires all nine to be caught.

## What is in here now

One directory: `uibc-self-20261124`, by this corpus's own author, labelled
`same-maintainer`. It exists so the format is exercised by a real run instead of
by an empty directory, and so the first row in the table is honestly ours.

**External submissions: 0.** That number is the one that matters, and nothing in
this directory changes it.

## What acceptance means

That the bytes you shipped describe the same verdicts this corpus records, against
the corpus version you named. It does not certify your product, and it is not a
badge. There is no badge.
