#!/usr/bin/env python3
"""Line and acceptance coverage per file, read from a JSON file somebody else measured.

generate.sh step [3] stays switched off, and for the reason it gives: a city has to build
for any checkout in thirty seconds with nothing run, and a pass that needs the repo's
tests to have passed on this machine is the reason nobody builds the city at all. That
argument is about who RUNS the tests. It says nothing against colouring by a run that has
already happened somewhere else — a CI job, a review pipeline that ran the suites for its
own reasons — and that is what this file is for: the caller hands over what it measured,
and the city reads it the way it reads the git log. Nothing is run from here.

    ./generate.sh --coverage coverage.json REPO OUT      # or CODECITY_COVERAGE=coverage.json

The format is deliberately smaller than any coverage tool's, so that every tool can be
converted into it in a dozen lines:

    {
      "files": {
        "src/main/java/com/acme/Owner.java": {
          "line":       {"covered": 31, "total": 40},
          "acceptance": {"covered": 12, "total": 40}
        }
      }
    }

  * keys are paths relative to the analysed repo's root (an absolute path inside it, a
    leading `./` and Windows separators are accepted and normalised);
  * `line` is every suite merged — "is this class tested at all";
  * `acceptance` is what the end-to-end tests alone reach — "would anything a user does
    have caught this". Optional, per file and as a whole;
  * each value is `{"covered", "total"}` (preferred: package roll-ups re-divide the
    summed counts, so a 3-line class cannot outvote a 300-line one), `[covered, total]`,
    or a bare percentage, which is weighed as 100 lines;
  * the `files` wrapper is optional: a bare `{path: entry}` object reads the same.

Absence is not zero, here as everywhere else on the plate. A file the JSON does not name,
or names with nothing executable in it (`total` 0), is NOT MEASURED and is drawn grey; a
file named with `covered` 0 is measured at 0% and is drawn red. Only the second one is a
finding about the tests.
"""
from __future__ import annotations

import json
import os
import sys


def _counts(value):
    """`(covered, total)` out of one of the three spellings, or None for "not measured"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # A bare percentage: weighed as 100 lines, the only weight that keeps it a
        # percentage when summed with others of its kind.
        pct = max(0.0, min(100.0, float(value)))
        return pct, 100.0
    if isinstance(value, dict):
        covered, total = value.get("covered"), value.get("total")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        covered, total = value
    else:
        return None
    try:
        covered, total = float(covered), float(total)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None            # nothing executable: nothing to have covered either
    return max(0.0, min(covered, total)), total


def normalise(path: str, repo_dir: str) -> str | None:
    """`path` relative to `repo_dir`, `/`-separated — or None when it lies outside it."""
    p = str(path).replace("\\", "/").strip()
    if not p:
        return None
    if os.path.isabs(p):
        root = os.path.realpath(repo_dir)
        real = os.path.realpath(p)
        if real != root and not real.startswith(root.rstrip("/") + "/"):
            # Also try the path as given: a checkout reached through a symlink
            # (/tmp -> /private/tmp) resolves to a prefix the JSON never wrote.
            plain = os.path.abspath(repo_dir).rstrip("/") + "/"
            if not p.startswith(plain):
                return None
            return p[len(plain):]
        p = os.path.relpath(real, root).replace(os.sep, "/")
    while p.startswith("./"):
        p = p[2:]
    return p or None


def parse(doc, repo_dir: str) -> tuple[dict, int]:
    """`({repo path: entry}, how many keys were dropped)` out of an already-loaded JSON.

    An entry is `{"cov_covered", "cov_total", "acc_covered", "acc_total"}` — the shape
    `compute_crap.py`'s rows already have, so everything downstream of the join reads one
    kind of thing. Acceptance travels as 0 of 0 when it was not measured, which the join
    turns into a blank and the page into "not measured", never into 0%."""
    files = doc.get("files") if isinstance(doc, dict) and isinstance(doc.get("files"), dict) \
        else doc
    if not isinstance(files, dict):
        return {}, 0
    out, dropped = {}, 0
    for key, entry in files.items():
        if str(key).startswith("//"):
            continue
        rel = normalise(key, repo_dir)
        line = _counts(entry.get("line")) if isinstance(entry, dict) else _counts(entry)
        acc = _counts(entry.get("acceptance")) if isinstance(entry, dict) else None
        if rel is None or (line is None and acc is None):
            dropped += 1
            continue
        out[rel] = {
            "cov_covered": line[0] if line else 0,
            "cov_total": line[1] if line else 0,
            "acc_covered": acc[0] if acc else 0,
            "acc_total": acc[1] if acc else 0,
        }
    return out, dropped


def load(path: str, repo_dir: str) -> dict:
    """`parse` of the file at `path`; `{}`, said aloud, when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        print(f"WARN: coverage file {path} unreadable ({e}); this city has no coverage",
              file=sys.stderr)
        return {}
    got, dropped = parse(doc, repo_dir)
    if dropped:
        print(f"WARN: {dropped} coverage entr{'y' if dropped == 1 else 'ies'} in {path} "
              "named no file of this repo, or nothing measured, and were dropped",
              file=sys.stderr)
    return got


def merge(crap_map: dict, coverage: dict) -> int:
    """Fold `coverage` into the CRAP join's map, in place; how many files it reached.

    The JSON is the caller's explicit word, so its line counts win over a JaCoCo report
    the walk happened to find — but a CRAP score that report gave is kept: it is a
    different measurement, and nothing in the JSON speaks to it. A file with coverage and
    no CRAP gets CRAP fields of None, which the join writes as blanks."""
    for rel, cov in coverage.items():
        entry = crap_map.get(rel)
        if entry is None:
            entry = crap_map[rel] = {"crap_max": None, "crap_max_method": "",
                                     "crap_load": None, "crappy_methods": None}
        entry.update(cov)
    return len(coverage)
