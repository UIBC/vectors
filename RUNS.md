# RUNS · every run that has been recorded here

One row per run. Transcribed from the receipt file, not summarised. An empty table is the honest state: it means nobody outside has run this and sent back a receipt yet.

## Rules

1. A row needs a receipt file under `receipts/` that passes `python tools/check_receipt.py receipts/<file>.json`.
2. `code` says who wrote the code that ran: `independent` (yours) or `author` (taken from this repo).
3. `blind` says whether you saw `EXPECTED.md` before running. "no" is not a failure, it just means your run was knowledge-bearing.
4. Divergences are recorded, not deleted. A receipt whose rows disagree with `EXPECTED.md` is more interesting than another clean pass, and it stays in the table with its disposition.
5. Nothing is counted as a witness. Every row here is self-reported; the check is that the bytes match, not that the person exists.

## Table

| Date | Runner | blind | code | platform / py / uibc-core | rows matched | receipt | disposition |
|---|---|---|---|---|---|---|---|
| 2026-11-23 | author-local | no | author | Windows-11 / py3.13.14 / 0.5.0 | yes (6/6) | `receipts/2026-11-23-author-local.json` | author run, not an external node |

External nodes (runners with `code: independent` who are not the author): **0**.
