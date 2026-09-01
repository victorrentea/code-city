#!/usr/bin/env python3
"""Compute fan-in and fan-out per non-test Java file in spring-framework.

Definitions (internal coupling — JDK/3rd-party deps not counted):
  fan_out = # distinct repo classes this file references
            (via imports + same-package siblings whose simple name appears in body)
  fan_in  = # files in the repo that reference any class declared in this file

Output: /Users/victorrentea/workspace/spring-framework/fanio-per-file.tsv
  file \t fan_in \t fan_out

...and, beside it, the EDGES those two counts are aggregates of:
  coupling-edges.tsv:  source \t target \t weight \t line
The counts answer "how coupled is this file"; the edge list answers "to WHAT", which
is what the Code City needs to draw a dependency pipe from a building to its peers.
`weight` is how many times the source names the target (comments and string literals
already stripped) — an import alone says *that* A depends on B, the count says how
hard, and it is what the pipe's thickness is drawn from.

`line` is where in the SOURCE the coupling actually lives: the first line naming the
target that is not an `import` or a `package` line. An import says the dependency
exists and nothing else — every one of them sits at the top of the file, so landing a
reader there answers "which class" and never "what for". The first real mention is
usually the injection point (a constructor parameter, a field), which is exactly the
line someone asking "why does this depend on that" wants to be standing on. 0 when the
only occurrences ARE the import — a class imported and then never used again.
"""
import bisect
import os
import re
import sys
from collections import Counter, defaultdict

import subprocess
_here = os.path.dirname(os.path.abspath(__file__))
def _git_root(start):
    try:
        return subprocess.check_output(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return start
REPO = os.path.abspath(os.environ.get("HEATMAP_REPO") or _git_root(_here))
OUT_DIR = os.path.abspath(os.environ.get("HEATMAP_OUT") or REPO)
EXTRA_PRUNE = {d for d in os.environ.get("HEATMAP_PRUNE", "").split(",") if d}
CLASS_TSV = os.path.join(OUT_DIR, "complexity-per-class.tsv")
OUT = os.path.join(OUT_DIR, "fanio-per-file.tsv")
EDGES_OUT = os.path.join(OUT_DIR, "coupling-edges.tsv")

def strip_comments_and_strings(src):
    """Java source with every comment and string literal blanked out (newlines kept, so
    line-anchored regexes still line up).

    A `{@link SpecialtyRestController}` in a Javadoc block is a cross-reference for a
    human reader, NOT a compile-time dependency — counting it inflates fan-out and, worse,
    draws a coupling wire between two classes that never call each other. Same for a name
    that only appears inside a string literal or a commented-out line. The sibling scan
    below is a plain regex over the file, so the only place to draw that line is here.

    Written as a scanner rather than a regex because the cases nest the wrong way round:
    `"http://x"` is a string, not a comment, and `// says "hi` is a comment with an
    unterminated string in it.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif ch == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(c if c == "\n" else " " for c in src[i:j]))
            i = j
        elif src.startswith('"""', i):                     # text block (Java 15+)
            j = src.find('"""', i + 3)
            j = n if j < 0 else j + 3
            out.append("".join(c if c == "\n" else " " for c in src[i:j]))
            i = j
        elif ch in "\"'":
            j = i + 1
            while j < n and src[j] != ch:
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append("".join(c if c == "\n" else " " for c in src[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;", re.MULTILINE)


def load_class_map():
    """Return dict: fqn (dot form, outer class only) -> file path. Plus per-package class list."""
    fqn_to_file = {}
    pkg_to_classes = defaultdict(list)  # 'org.springframework.x' -> [(simple_name, file), ...]
    with open(CLASS_TSV) as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            file, fqn = parts[0], parts[1]
            # fqn uses '$' for nesting; flatten to outer dot-form for import resolution
            if not fqn or "." not in fqn:
                continue
            outer_dollar = fqn.split("$", 1)[0]  # outer only
            outer_dot = outer_dollar
            # also register the inner (some imports point at inner classes)
            inner_dot = fqn.replace("$", ".")
            for key in {outer_dot, inner_dot}:
                fqn_to_file.setdefault(key, file)
            pkg = outer_dot.rsplit(".", 1)[0]
            simple = outer_dot.rsplit(".", 1)[1]
            pkg_to_classes[pkg].append((simple, file))
    return fqn_to_file, pkg_to_classes


def list_java_files():
    out = []
    for root, dirs, files in os.walk(REPO):
        parts = root.split(os.sep)
        if any(p == ".git" for p in parts) or any(p in EXTRA_PRUNE for p in parts):
            dirs[:] = []
            continue
        if any(parts[i] == "src" and parts[i + 1] in ("test", "testFixtures") for i in range(len(parts) - 1)):
            dirs[:] = []
            continue
        for fn in files:
            if fn.endswith(".java"):
                out.append(os.path.join(root, fn))
    return out


def main():
    fqn_to_file, pkg_to_classes = load_class_map()
    print(f"loaded {len(fqn_to_file)} FQN entries across {len(pkg_to_classes)} packages", file=sys.stderr)

    java_files = list_java_files()
    print(f"scanning {len(java_files)} java files", file=sys.stderr)

    fan_out = defaultdict(dict)  # file -> {target file: how many times it is named}
    fan_sites = defaultdict(dict)  # file -> {target file: the line that couples them}

    for ap in java_files:
        rel = os.path.relpath(ap, REPO)
        try:
            with open(ap, encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue
        src = strip_comments_and_strings(src)
        pkg_m = PACKAGE_RE.search(src)
        pkg = pkg_m.group(1) if pkg_m else None

        # Simple name -> the target file(s) it would resolve to. Imports and
        # same-package siblings are both just candidate names to look for in the body;
        # the single scan below decides which of them are real references, and how many.
        candidates = defaultdict(set)
        for imp in IMPORT_RE.findall(src):
            # static import targets a method/field; the class is everything before the last dot
            # but our regex already trimmed the .* wildcard; for static, the last segment is member name
            # we don't reliably distinguish here — try the full path first, then strip last segment
            for candidate in (imp, imp.rsplit(".", 1)[0] if "." in imp else imp):
                tf = fqn_to_file.get(candidate)
                if tf and tf != rel:
                    candidates[candidate.rsplit(".", 1)[-1]].add(tf)
                    break
        if pkg and pkg in pkg_to_classes:
            for simple, tf in pkg_to_classes[pkg]:
                if tf != rel:
                    candidates[simple].add(tf)

        # The lines the `import`s and the `package` declaration sit on. A name found on
        # one of them is the dependency being DECLARED, not used, and it is the one place
        # a reader learns nothing by being sent to.
        declaration_lines = set()
        line_starts = [0]
        for i, ch in enumerate(src):
            if ch == "\n":
                line_starts.append(i + 1)

        def line_of(offset):
            return bisect.bisect_right(line_starts, offset)      # 1-based

        for m in list(PACKAGE_RE.finditer(src)) + list(IMPORT_RE.finditer(src)):
            declaration_lines.add(line_of(m.start()))

        # ONE regex pass for every candidate name at once — per-name scans turn a big
        # repo into an O(classes x filesize) crawl. A sibling that never appears scores
        # zero and is simply not a dependency; an imported class always scores at least
        # the one occurrence on its own import line.
        targets = {}
        sites = {}
        if candidates:
            pattern = r"\b(?:" + "|".join(re.escape(n) for n in sorted(candidates)) + r")\b"
            hits = Counter()
            first = {}            # candidate name -> its first line outside the declarations
            for m in re.finditer(pattern, src):
                name = m.group(0)
                hits[name] += 1
                if name not in first:
                    line = line_of(m.start())
                    if line not in declaration_lines:
                        first[name] = line
            for name, n in hits.items():
                for tf in candidates[name]:
                    targets[tf] = targets.get(tf, 0) + n
                    # Two names can resolve to one file (an import plus a same-package
                    # sibling of the same simple name); the earliest of them is the site.
                    line = first.get(name)
                    if line and line < sites.get(tf, 1 << 30):
                        sites[tf] = line

        fan_out[rel] = targets
        fan_sites[rel] = sites

    # reverse to fan-in
    fan_in = defaultdict(int)
    for src_file, tgts in fan_out.items():
        for tf in tgts:
            fan_in[tf] += 1        # DISTINCT dependants, as before — not their reference counts

    rows = []
    all_files = set(fan_out.keys()) | set(fan_in.keys())
    for f in all_files:
        rows.append((f, fan_in.get(f, 0), len(fan_out.get(f, {}))))
    rows.sort()

    with open(OUT, "w") as f:
        f.write("file\tfan_in\tfan_out\n")
        for r in rows:
            f.write(f"{r[0]}\t{r[1]}\t{r[2]}\n")
    print(f"wrote {len(rows)} rows to {OUT}", file=sys.stderr)

    # The same relation, un-aggregated. Sorted so a rebuild of an unchanged repo
    # produces a byte-identical file and the diff stays about the code.
    edges = 0
    with open(EDGES_OUT, "w") as f:
        f.write("source\ttarget\tweight\tline\n")
        for src_file in sorted(fan_out):
            sites = fan_sites.get(src_file, {})
            for tf in sorted(fan_out[src_file]):
                f.write(f"{src_file}\t{tf}\t{fan_out[src_file][tf]}\t{sites.get(tf, 0)}\n")
                edges += 1
    print(f"wrote {edges} edges to {EDGES_OUT}", file=sys.stderr)

    # quick sanity report
    top_out = sorted(rows, key=lambda r: r[2], reverse=True)[:5]
    top_in = sorted(rows, key=lambda r: r[1], reverse=True)[:5]
    print("\ntop fan_out:", file=sys.stderr)
    for r in top_out:
        print(f"  {r[2]:4d}  {r[0]}", file=sys.stderr)
    print("\ntop fan_in:", file=sys.stderr)
    for r in top_in:
        print(f"  {r[1]:4d}  {r[0]}", file=sys.stderr)


if __name__ == "__main__":
    main()
