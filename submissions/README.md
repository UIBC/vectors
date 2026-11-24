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
  "contact": "security@example.com",
  "independence": "independent",
  "submitted_at": "2026-11-25"
}
```

`independence` is one of two words. `independent` means a different maintainer
wrote the verifier from the specification text; `same-maintainer` means one of
us. The validator refuses `independent` from this organisation's own legal
entity, because a self-submission is not a second opinion.

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

`python tools/check_submission.py --selftest` breaks the format six ways and
requires all six to be caught.

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
