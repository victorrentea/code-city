#!/usr/bin/env python3
"""Per-file CRAP and line coverage, read out of a JaCoCo XML report.

CRAP is Alberto Savoia's Change Risk Anti-Patterns metric
(https://testing.googleblog.com/2011/02/this-code-is-crap.html):

    CRAP(m) = comp(m)^2 * (1 - cov(m))^3 + comp(m)

for a single METHOD m, where comp is cyclomatic complexity and cov is its coverage in
[0,1]. Read it as: complexity is forgivable exactly to the degree it is tested. A
straight-line method costs 1 whether or not anyone tests it; a method with a complexity
of 10 costs 10 when fully covered and 1010 when nobody ever ran it. The blog's threshold
is 30 — above that, the method is crap.

Everything the formula needs is already in a JaCoCo report and nothing else here has to
change to get it: JaCoCo emits a per-method COMPLEXITY counter whose missed+covered IS
the cyclomatic complexity, next to the LINE counter that gives the coverage. So this pass
parses one XML file rather than adding a second complexity analyser next to
compute_complexity.py — and it deliberately does NOT reuse that one's cognitive
complexity, which is a different scale on a different definition and would quietly turn
the formula into a number Savoia never defined.

Inputs:
  - CODECITY_JACOCO : one or more paths/globs to jacoco.xml, separated by ":" or ",".
    Unset, we glob the repo for the two places Maven and Gradle put it by default.
  - REPO_DIR working tree : to map JaCoCo's <package>/<sourcefilename> back to a path.

Output:
  - OUT_DIR/crap-per-file.tsv : file \t cov_covered \t cov_total \t crap_max \t
    crap_max_method \t crap_load \t crappy_methods \t methods
    Written only when a report was found; downstream every column is optional, and a
    file the report never mentions gets no row at all (see the note on absence below).

Absence is not zero. A class JaCoCo never loaded and a class with 0% coverage are very
different findings, and collapsing them would paint every unbuilt module as perfectly
crap-free (or perfectly crappy, depending on the metric). So an unmeasured file is left
OUT of this file entirely, travels to the page as null, and is painted in the "not
measured" grey rather than being given a place on the ramp it never earned.
"""
import glob
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

_here = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.environ.get("HEATMAP_REPO") or _here)
OUT_DIR = os.path.abspath(os.environ.get("HEATMAP_OUT") or REPO_DIR)
os.makedirs(OUT_DIR, exist_ok=True)
OUT_FILE = os.path.join(OUT_DIR, "crap-per-file.tsv")

# The blog's line in the sand. Kept here (not in the renderer) so the count of crappy
# methods and the colour ramp that the page pins to 30 quote the same number.
CRAP_THRESHOLD = 30.0

# Where Maven's jacoco:report and Gradle's jacocoTestReport put their XML when nobody
# has reconfigured them. Anything else is what CODECITY_JACOCO is for.
DEFAULT_GLOBS = [
    "**/target/site/jacoco/jacoco.xml",
    "**/target/site/jacoco-aggregate/jacoco.xml",
    "**/build/reports/jacoco/**/*.xml",
]
# Directories that hold a whole second copy of the repo (agent worktrees) or of its
# dependencies. A jacoco.xml found in there describes somebody else's checkout.
SKIP_SEGMENTS = {".claude", ".conductor", "node_modules", ".git"}


def report_paths():
    """Every jacoco.xml we should read, explicit setting first."""
    configured = os.environ.get("CODECITY_JACOCO", "").replace(",", ":")
    patterns = [p for p in configured.split(":") if p.strip()]
    if patterns:
        found = []
        for pat in patterns:
            pat = pat if os.path.isabs(pat) else os.path.join(REPO_DIR, pat)
            found.extend(sorted(glob.glob(pat, recursive=True)))
        return [p for p in found if os.path.isfile(p)]
    found = []
    for pat in DEFAULT_GLOBS:
        for p in sorted(glob.glob(os.path.join(REPO_DIR, pat), recursive=True)):
            rel_segments = set(os.path.relpath(p, REPO_DIR).split(os.sep))
            if rel_segments & SKIP_SEGMENTS:
                continue
            if os.path.isfile(p):
                found.append(p)
    return found


def source_index():
    """`<package path>/<File.java>` -> [repo-relative paths], for every non-test source.

    JaCoCo works on bytecode and only knows a class' package and its source FILE name;
    the city is keyed by repo-relative path. In a multi-module build the same package
    can legitimately exist under several module roots, so the value is a LIST and the
    module the report came from breaks the tie. The inclusion rule is deliberately the
    one build_heatmap.py walks with — a file this index resolves that the codemap does
    not carry would be a row nothing ever joins.
    """
    index = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(REPO_DIR):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in ("target", "build", "out", "node_modules")]
        parts = os.path.relpath(dirpath, REPO_DIR).split(os.sep)
        if any(parts[i] == "src" and i + 1 < len(parts) and parts[i + 1] in ("test", "testFixtures")
               for i in range(len(parts))):
            continue
        # The package is whatever follows the source root. Falling back to the last
        # directory segment keeps a non-Maven layout resolvable, since JaCoCo's package
        # name still has to end the same way.
        pkg = None
        for root_name in ("java", "kotlin"):
            if root_name in parts:
                pkg = "/".join(parts[parts.index(root_name) + 1:])
                break
        if pkg is None:
            pkg = "/".join(parts)
        for fn in filenames:
            if not fn.endswith(".java") or fn == "package-info.java":
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), REPO_DIR)
            index[f"{pkg}/{fn}"].append(rel)
    return index


def counter(node, kind):
    """(missed, covered) for one JaCoCo counter, or (0, 0) when it is absent."""
    for c in node.findall("counter"):
        if c.get("type") == kind:
            return int(c.get("missed", 0)), int(c.get("covered", 0))
    return 0, 0


def crap(complexity, coverage):
    """CRAP(m), with coverage as a fraction in [0,1]."""
    return complexity ** 2 * (1.0 - coverage) ** 3 + complexity


def main():
    reports = report_paths()
    if not reports:
        print("no jacoco.xml found (set CODECITY_JACOCO to point at one); "
              "CRAP and coverage will be absent from this city", file=sys.stderr)
        # An empty run must not leave a stale file from a previous one standing: the
        # page would then colour today's city with last week's coverage.
        if os.path.exists(OUT_FILE):
            os.remove(OUT_FILE)
        return
    index = source_index()

    # file -> [lines missed, lines covered, worst CRAP, worst method, CRAP sum,
    #          methods over the threshold, methods]
    per_file = defaultdict(lambda: [0, 0, 0.0, "", 0.0, 0, 0])
    unresolved = set()
    for report in reports:
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError as e:
            print(f"WARN: {report} is not parseable ({e}); skipping it", file=sys.stderr)
            continue
        # A report path like <module>/target/site/jacoco/jacoco.xml tells us which module
        # the classes in it belong to, which is how the same package name under two
        # modules stays two different files.
        module = os.path.relpath(os.path.dirname(report), REPO_DIR)
        for _ in range(3):   # strip target/site/jacoco
            module = os.path.dirname(module)
        for pkg in root.findall("package"):
            pkg_path = pkg.get("name", "")
            for cls in pkg.findall("class"):
                src = cls.get("sourcefilename")
                if not src:
                    continue   # bytecode with no source: generated, and not in the city
                rel = resolve(index, module, pkg_path, src)
                if rel is None:
                    unresolved.add(f"{pkg_path}/{src}")
                    continue
                acc = per_file[rel]
                for m in cls.findall("method"):
                    lm, lc = counter(m, "LINE")
                    cm, cc = counter(m, "COMPLEXITY")
                    complexity = cm + cc
                    if complexity <= 0:
                        continue   # nothing the formula can say about a bodiless method
                    total = lm + lc
                    # A method with no line counter at all (JaCoCo does this for some
                    # synthetics) has nothing to have covered; the branch counter is a
                    # fairer read of it than pretending the coverage is 0.
                    cov = (lc / total) if total else (cc / complexity)
                    value = crap(complexity, cov)
                    acc[0] += lm
                    acc[1] += lc
                    if value > acc[2]:
                        acc[2] = value
                        acc[3] = method_label(m)
                    acc[4] += value
                    acc[5] += 1 if value > CRAP_THRESHOLD else 0
                    acc[6] += 1

    # An interface, a marker annotation, a Spring Data repository: JaCoCo lists the class
    # but no method in it carries any complexity, because there is no body anywhere to
    # cover. A row of zeros here would render as a perfectly clean, fully covered class,
    # which is a claim about testing that nobody made. It has nothing to measure, so it
    # goes out with the unmeasured.
    per_file = {rel: acc for rel, acc in per_file.items() if acc[6]}
    rows = sorted(per_file.items(), key=lambda kv: kv[1][2], reverse=True)
    with open(OUT_FILE, "w") as f:
        f.write("file\tcov_covered\tcov_total\tcrap_max\tcrap_max_method\tcrap_load\tcrappy_methods\tmethods\n")
        for rel, (lm, lc, worst, worst_name, load, crappy, methods) in rows:
            f.write(f"{rel}\t{lc}\t{lm + lc}\t{worst:.1f}\t{worst_name}\t{load:.1f}\t{crappy}\t{methods}\n")

    covered = sum(v[1] for v in per_file.values())
    total = sum(v[0] + v[1] for v in per_file.values())
    pct = (100.0 * covered / total) if total else 0.0
    print(f"read {len(reports)} jacoco report(s): {len(rows)} files, "
          f"{pct:.1f}% line coverage overall", file=sys.stderr)
    if unresolved:
        # Loud, because the failure mode is silent otherwise: the city just looks less
        # covered than it is, and nothing on the page says which classes went missing.
        sample = ", ".join(sorted(unresolved)[:5])
        print(f"WARN: {len(unresolved)} covered classes had no source file in the walk "
              f"(generated, or outside it): {sample}", file=sys.stderr)


def method_label(m):
    """`name` for an ordinary method, spelled out for the ones JaCoCo names in bytecode."""
    name = m.get("name", "?")
    if name == "<init>":
        return "constructor"
    if name == "<clinit>":
        return "static initializer"
    return name


def resolve(index, module, pkg_path, src):
    """JaCoCo's (module, package, source file) -> the repo-relative path, or None.

    The package/filename key is normally unique and answers on its own. It is not unique
    in a multi-module build that repeats a package across modules, and there the module
    the report was found in decides. An aggregate report (one XML for the whole build)
    cannot say which module a class came from, which is exactly when the key has to be
    unique on its own — an ambiguous one is dropped rather than guessed at.
    """
    candidates = index.get(f"{pkg_path}/{src}", ())
    if len(candidates) == 1:
        return candidates[0]
    if module and module != ".":
        prefix = module.replace(os.sep, "/") + "/"
        scoped = [rel for rel in candidates if rel.startswith(prefix)]
        if len(scoped) == 1:
            return scoped[0]
    return None


if __name__ == "__main__":
    main()
