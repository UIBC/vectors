# A request to run this corpus somewhere else

Issued by UIBC maintainers on 2026-11-25.

Corpus digest: `81e31f78f106eaf6011efa00b1312b5a35ac9b732a73728cb8024c7ef306e3d9`

## What to run

```
git clone https://github.com/UIBC/vectors.git
cd vectors
python -m venv venv && . venv/bin/activate    # Windows: venv\Scripts\activate
pip install uibc-core==0.5.0 asn1crypto cryptography
python tools/stranger.py | tee run.log
```

The last line must read `STRANGER OK - every gate that ran matched`. Each gate also prints its own line; `request.json` lists them with the exact text each must contain.

## What to send back

`reply-template.json` filled in, plus `run.log` unedited. If a gate failed, send it anyway: a failure on your machine is information, and the ledger records it as a failure rather than dropping it.

## What we will do with it

`tools/check_external_runs.py` checks the log's digest, the corpus digest, and that every gate line is present. The headline number of external runs is computed from the records that pass, so it cannot be typed up by us. A run that fails is published as failed.

Nothing in this pack asks you to endorse the project, and nothing is counted as an endorsement.
