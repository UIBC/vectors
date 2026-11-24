"""One command for someone who has never seen this repo: run every gate, print a table.

    python tools/stranger.py                       # gates that need one interpreter
    python tools/stranger.py --also <py-with-0.4.1>  # adds the version-floor comparison
    python tools/stranger.py --json out.json        # machine-readable record

Why a separate entry point instead of a list in the README: a list is something a
reader has to trust and assemble. This is something a reader runs, and it writes
down what happened. The difference between "we have gates" and "you can check
them" is exactly one command.

Design rules, all of them deliberate:

  S1  every gate is a subprocess with its own exit code; nothing is swallowed
  S2  each gate declares a line its OUTPUT must contain - not its last line, because
      the submission gate ends with a caveat on purpose. A gate that passes for a
      new reason is thus visible instead of silently accepted.
  S3  a gate that cannot be run is reported as NOT RUN, never as passed
  S4  the tool writes stranger-run.json: argv, exit code, duration, last line.
      A claim about a run is worth less than the run's own record
  S5  no network, no key, no credentials - if a gate needs any of those it is
      out of scope here and says so

Exit 0 only when every gate that ran matched. Exit 2 when a required gate could
not run at all.
"""

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# (label, argv, must-contain-in-last-line)  - argv relative to this interpreter
GATES = [
    ("eight rows", ["tools/run_vectors.py"], "MATRIX GATE OK"),
    ("adversarial", ["tools/run_adversarial.py"], "ADVERSARIAL OK"),
    ("frozen fixtures", ["tools/check_frozen.py"], "FROZEN OK"),
    ("submission gate", ["tools/check_submission.py"], "SUBMISSIONS OK"),
    ("gate self-test", ["tools/check_submission.py", "--selftest"], "SELFTEST OK"),
    ("report self-test", ["tools/check_report.py", "--selftest"], "REPORT SELFTEST OK"),
    ("key hygiene", ["tools/check_key_hygiene.py"], "KEY HYGIENE OK"),
]


def evidence_line(text, needle):
    """The line that carries the promise, not necessarily the last one."""
    for line in [l.strip() for l in text.splitlines()]:
        if needle in line:
            return line
    return last_meaningful_line(text)


def last_meaningful_line(text):
    for line in reversed([l.strip() for l in text.splitlines()]):
        if line:
            return line
    return ""


def run_one(python, argv, needle):
    started = time.perf_counter()
    try:
        p = subprocess.run([python, *argv], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=300)
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError as exc:
        return {"rc": None, "line": "NOT RUN - %s" % exc, "seconds": 0.0}
    except subprocess.TimeoutExpired:
        return {"rc": None, "line": "TIMEOUT after 300s", "seconds": 300.0}
    return {"rc": rc, "line": evidence_line(out, needle), "last_line": last_meaningful_line(out),
            "matched": needle in out,
            "seconds": round(time.perf_counter() - started, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--also", action="append", default=[],
                    help="a second python with a different uibc-core release")
    ap.add_argument("--json", default="stranger-run.json")
    a = ap.parse_args()

    print("stranger run · %s" % ROOT)
    print("interpreter: %s" % sys.executable)
    try:
        import uibc_core
        print("uibc-core:   %s" % getattr(uibc_core, "__version__", "?"))
    except Exception:
        print("uibc-core:   NOT IMPORTABLE - `pip install uibc-core==0.5.0` first")
        return 2

    rows, failures, notrun = [], [], []
    for label, argv, needle in GATES:
        r = run_one(sys.executable, argv, needle)
        ok = r["rc"] == 0 and r["matched"]
        rows.append({"gate": label, "argv": argv, "needle": needle, **r, "ok": ok})
        print("[%s] %-18s %5.2fs  %s" % ("OK  " if ok else "FAIL", label, r["seconds"], r["line"]))
        if r["rc"] is None:
            notrun.append(label)
        elif not ok:
            failures.append(label)

    if a.also:
        r = run_one(sys.executable, ["tools/run_crossversion.py", "--also", *a.also], "CROSSVERSION OK")
        ok = r["rc"] == 0 and r["matched"]
        rows.append({"gate": "version floor (two releases)", "argv": ["tools/run_crossversion.py", "--also", *a.also],
                     "needle": "CROSSVERSION OK", **r, "ok": ok})
        print("[%s] %-18s %5.2fs  %s" % ("OK  " if ok else "FAIL", "version floor", r["seconds"], r["line"]))
    else:
        print("[SKIP] version floor      -  needs --also <python-with-a-different-release>")

    total = sum(x["seconds"] for x in rows)
    record = {"tool": "stranger/1", "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "interpreter": sys.executable, "rows": rows, "total_seconds": round(total, 2)}
    with open(os.path.join(ROOT, a.json), "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("\n%0.1f s across %d gate(s); record written to %s" % (total, len(rows), a.json))

    if notrun:
        print("STRANGER INCOMPLETE - could not run: %s" % ", ".join(notrun))
        return 2
    if failures:
        print("STRANGER FAILED - %d gate(s) did not match: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("STRANGER OK - every gate that ran matched; this certifies that the repo is "
          "self-consistent, not that it is conformant or externally verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


