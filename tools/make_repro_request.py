"""Build the pack somebody else needs to run this corpus and hand back a record.

    python tools/make_repro_request.py [--out outreach/repro-request-YYYYMMDD]

Why this exists: "no external run has been done" was a sentence in our docs.
A sentence cannot be answered. A pack can: it names one command, states the
output lines that command must print, records the corpus digest those lines
belong to, and ships a reply template whose fields the ledger checks. Nothing
here contacts anybody - issuing a request is our act, sending it is the
maintainer's, and a tool that mailed itself would be the wrong kind of
automation.

The reply template is deliberately not a free-form paragraph. A record that
cannot be machine-checked becomes an anecdote, and the ledger's rule is that
the headline count is *derived* from checked records, never typed by us.
"""

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

REPLY_TEMPLATE = {
    "contract": "uibc-external-run/1",
    "id": "<your handle or organisation>-<yyyymmdd>",
    "runner": "<name or organisation that ran it>",
    "independent_of_maintainer": "true | false - false is accepted and counted separately",
    "date": "<YYYY-MM-DD>",
    "verifier_version": "<what `python -m uibc_core.cli --version` printed>",
    "python": "<python -V>",
    "os": "<uname -a / Windows build>",
    "corpus_digest": "<from request.json; do not edit>",
    "gates": [{"name": "<gate label>", "ok": "true | false",
               "evidence_line": "<the line the gate printed>"}],
    "log_path": "logs/<id>.log",
    "note": "<anything a reader should know: what surprised you, what failed>",
}


def corpus_digest():
    with open(os.path.join(ROOT, "FIXTURES.sha256"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--issuer", default="UIBC maintainers")
    a = ap.parse_args()

    import run_vectors as rv
    import stranger as st

    digest = corpus_digest()
    out = a.out or os.path.join(ROOT, "outreach",
                                "repro-request-" + time.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)

    gates = [{"label": label, "command": "python " + " ".join(argv),
              "must_contain": needle} for label, argv, needle in st.GATES]

    request = {
        "contract": "uibc-repro-request/1",
        "issued_by": a.issuer,
        "issued_at": time.strftime("%Y-%m-%d"),
        "repository": "https://github.com/UIBC/vectors",
        "corpus_digest": digest,
        "rows": len(rv.ROWS),
        "gates": gates,
        "what_we_ask": [
            "clone the repository at the commit named in this directory",
            "create a fresh virtualenv and run exactly: "
            "pip install uibc-core==0.5.0 asn1crypto cryptography",
            "run `python tools/stranger.py` and paste its log, unedited",
            "fill reply-template.json and return it with the log",
        ],
        "what_this_proves": (
            "That the corpus reproduces on a machine we do not control, and that a "
            "verifier we did not build agrees with the verdicts. It does not make "
            "the corpus conformant, and it does not make the submitter independent "
            "unless they say so and the ledger can see it."
        ),
        "what_it_does_not_prove": [
            "conformance of anything to the specification's intent",
            "that a second implementation exists (this is still the reference verifier)",
            "that the checks are correct, only that they answer the same way twice",
        ],
    }

    with open(os.path.join(out, "request.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(request, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(out, "reply-template.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(REPLY_TEMPLATE, fh, indent=2)
        fh.write("\n")

    lines = [
        "# A request to run this corpus somewhere else",
        "",
        "Issued by %s on %s." % (request["issued_by"], request["issued_at"]),
        "",
        "Corpus digest: `%s`" % digest,
        "",
        "## What to run",
        "",
        "```",
        "git clone https://github.com/UIBC/vectors.git",
        "cd vectors",
        "python -m venv venv && . venv/bin/activate    # Windows: venv\\Scripts\\activate",
        "pip install uibc-core==0.5.0 asn1crypto cryptography",
        "python tools/stranger.py | tee run.log",
        "```",
        "",
        "The last line must read `STRANGER OK - every gate that ran matched`. "
        "Each gate also prints its own line; `request.json` lists them with the "
        "exact text each must contain.",
        "",
        "## What to send back",
        "",
        "`reply-template.json` filled in, plus `run.log` unedited. If a gate "
        "failed, send it anyway: a failure on your machine is information, and "
        "the ledger records it as a failure rather than dropping it.",
        "",
        "## What we will do with it",
        "",
        "`tools/check_external_runs.py` checks the log's digest, the corpus "
        "digest, and that every gate line is present. The headline number of "
        "external runs is computed from the records that pass, so it cannot be "
        "typed up by us. A run that fails is published as failed.",
        "",
        "Nothing in this pack asks you to endorse the project, and nothing is "
        "counted as an endorsement.",
        "",
    ]
    with open(os.path.join(out, "INSTRUCTIONS.md"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("\n".join(lines))

    print(json.dumps({"out": os.path.relpath(out, ROOT), "corpus_digest": digest,
                      "gates": len(gates), "rows": len(rv.ROWS)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
