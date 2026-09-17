#!/usr/bin/env python3
"""Which files are IN the repo under analysis — asked of git, not of the filesystem.

Every pass here used to walk the tree with `os.walk` and prune what it recognised as
noise. There were four such walks — modules and sources in build_heatmap.py, sources in
compute_fanio.py, sources in compute_complexity.py — and they had drifted into four
different denylists: one knew about `.pylibs` and `.idea`, the others did not; one
pruned on any path segment, another only on directory names; all four shared the
`HEATMAP_PRUNE` env list on top.

A denylist is always one name behind. The failure that ended this arrangement: a
human-review run left the base copy of a changed file in `.human-review/.diffbase/<sha>/`
(named `VisitRestController@9edd4dd5.java`, so the editor tab reads as a comparison), and
the city drew it as a second `VisitRestController` — a class nobody wrote, in a package
it does not belong to, next to the real one. `.human-review` was not on the list. Nor is
`.cursor`, `.aider`, or whatever writes Java-shaped files into a checkout next year.

So ask the repo instead. `git ls-files` answers with the repo's own definition of what
belongs to it, which is a definition the repo maintains — every generated, vendored and
scratch directory is already in a `.gitignore` somebody keeps current, because the same
answer is what makes `git status` usable. `.human-review/` is ignored at petclinic
(`.gitignore:105`) and would never have been offered.

Two consequences worth naming, because they are behaviour changes:

  * A file that is not in the repo is not in the city, even when it is sitting right
    there on disk. That is the entire point, but it means a city of a directory that is
    not a git checkout is now an error rather than a wrong answer. The pipeline already
    required git for the history walk, so nothing that used to work stops working.

  * `--others --exclude-standard` is deliberate: untracked-but-not-ignored files ARE
    included. A reviewer building a city of a working tree with a brand-new class in it
    should see that class; it is `.gitignore`, not the index, that says what is noise.

`HEATMAP_PRUNE` survives as a second filter over the answer, for the repo that commits
its own `target/` or vendors a copy of somebody else's sources. It is no longer load
bearing, and no longer the only thing standing between the city and a stray file.
"""
from __future__ import annotations

import os
import subprocess
import sys

# One `git ls-files` per repo per process. build_heatmap.py asks twice — once at import
# time to find the modules, once for the sources — and on a repo the size of Spring the
# call is ~11k paths; doing it twice is not expensive, but it is also not free and the
# two answers must not be able to disagree.
_CACHE: dict[str, list[str]] = {}


def is_java_source(rel: str) -> bool:
    """The pipeline's one inclusion rule: non-test .java, and not a package-info.

    `package-info.java` holds only package annotations and Javadoc — a building with no
    behaviour in it, which reads as a class that someone forgot to fill in.

    Takes a repo-relative, slash-separated path, so it applies unchanged to a path that
    came out of `git log` for a revision where no file exists on disk any more.
    """
    if not rel.endswith(".java"):
        return False
    if rel.rsplit("/", 1)[-1] == "package-info.java":
        return False
    segs = rel.split("/")
    return not any(segs[i] == "src" and segs[i + 1] in ("test", "testFixtures")
                   for i in range(len(segs) - 1))


def prune_set() -> set[str]:
    """The extra directory names HEATMAP_PRUNE asks to drop on top of git's answer."""
    return {d for d in os.environ.get("HEATMAP_PRUNE", "").split(",") if d}


def _is_pruned(rel: str, prune: set[str]) -> bool:
    # Directory segments only: a FILE called `target` is a file called `target`, and the
    # walks this replaces pruned directories too. `[:-1]` drops the basename.
    return any(seg in prune for seg in rel.split("/")[:-1])


def tracked_paths(repo: str) -> list[str]:
    """Every file the repo claims, repo-relative and slash-separated, sorted.

    Sorted because the walks this replaces were not, and two runs over the same repo
    produced the same city only by accident of directory order — which differs between
    filesystems, and so between a developer's machine and CI.
    """
    repo = os.path.abspath(repo)
    if repo in _CACHE:
        return _CACHE[repo]
    proc = subprocess.run(
        ["git", "-C", repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        sys.exit(f"{repo} is not a git checkout, and the city is built from what git "
                 f"says the repo contains: {err or 'git ls-files failed'}")
    # -z so a path with a space, a quote or a newline in it arrives as it is, instead of
    # in git's quoted-and-escaped spelling. surrogateescape because a repo is allowed to
    # hold a filename that is not valid UTF-8, and losing the pipeline over one would be
    # absurd — such a path round-trips back to the same bytes when it is opened.
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    prune = prune_set()
    paths = sorted({n for n in names if n and not _is_pruned(n, prune)})
    # `--cached` lists what the INDEX holds, which includes a file deleted from the
    # working tree but not yet staged as deleted. Everything downstream reads bytes off
    # disk, so such a path would be an open() that throws halfway through a run.
    paths = [p for p in paths if os.path.isfile(os.path.join(repo, p))]
    _CACHE[repo] = paths
    return paths


def java_sources(repo: str) -> list[str]:
    """Absolute paths of the Java sources the city is made of.

    Absolute, because that is the shape the three walks this replaces produced and what
    their callers go on to do relpath() against.
    """
    repo = os.path.abspath(repo)
    return [os.path.join(repo, rel) for rel in tracked_paths(repo) if is_java_source(rel)]
