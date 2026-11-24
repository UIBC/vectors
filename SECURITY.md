# Security policy · UIBC conformance vectors

This repository holds test fixtures and a gate. It does not hold the verifier — that lives in the reference implementation repository — so most protocol-level findings belong there. This file says what belongs here, and what deliberately does not.

## Reporting

Use GitHub's **private vulnerability reporting** on this repository (Security tab → *Report a vulnerability*). It opens a private channel with the maintainer; nothing is published until you agree.

Please include: the file or command, the version of `uibc-core` you ran, what you expected, what happened, and whether you are willing to be named. A reproducible command beats a description.

There is **one maintainer** at the time of writing (the organisation profile states the current count). Expect best effort, not a service level. If that is not acceptable for your use, that is a fair reason not to depend on this yet — and it is written down here rather than discovered later.

## In scope

| Class | Example |
|---|---|
| Verdict is wrong for a committed vector | `clean` returns FAIL, or `keyswap` returns UNKNOWN |
| Gate can be made to pass while a row is actually wrong | `run_vectors.py` exit 0 with a diverging row |
| Receipt check accepts bytes that moved | `check_receipt.py` prints ACCEPTABLE after a file is edited |
| Key-hygiene guard bypass | seed outside `keys/` that `check_key_hygiene.py` does not flag |
| Fixture digest divergence between the committed set and a rebuild | same verdicts, different `evidence_root` |

## Out of scope, by design

- **The two seeds in `keys/` are public on purpose.** They are test fixtures, already compromised by publication, and needed so the `keyswap` forgery can be rebuilt by anyone. Reporting "private keys are committed" is not a finding here; `keys/README.md` explains the trade and `tools/check_key_hygiene.py` pins the four files by digest so replacement is detectable.
- Limitations already stated in `EXPECTED.md` (no third-party implementation exercised, no rollback vector, the Windows `PYTHONIOENCODING` workaround) are known gaps, not vulnerabilities. A PR that closes one is welcome.
- A PASS that a reader misreads as safety. The scope statement is the mitigation; see `README.md`.

## What this is not

No certification, no accreditation, no security assessment of any agent. A clean CI run here means six rows matched on this machine with this verifier version. It says nothing about an agent's behaviour in the world.
