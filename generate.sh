#!/usr/bin/env bash
# Build a Code City (and the 2D codemap next to it) for a folder of Java sources.
#
#   ./generate.sh [REPO] [OUT]
#     REPO   git checkout to analyse   (default: $PWD's git toplevel)
#     OUT    where the artifacts land  (default: REPO/.codecity)
#
# Both arguments are just friendlier spellings of HEATMAP_REPO / HEATMAP_OUT, so an
# env-var caller (the in-page "build for your own repo" recipe, CI) keeps working.
#
# Pipeline:
#   compute_complexity.py  -> complexity-per-{class,file}.tsv   (tree-sitter cognitive complexity)
#   compute_fanio.py       -> fanio-per-file.tsv                (internal fan-in / fan-out)
#   build_heatmap.py       -> codemap.tsv                       (joins git history + size + above)
#   render_heatmap.py      -> codemap.html                      (self-contained Plotly page)
#   render_codecity.py     -> codecity.html                     (Three.js CodeCity)
#   render_combined.py     -> combined.html                     (2D codemap <-> 3D city, linked)
#
# Bug signal: build_heatmap.py flags a commit as bug-linked when its subject matches a
# default heuristic (a leading "fix"/"fixed"/"fixes"/"bugfix", which covers both strict
# Conventional Commits and the plain "Fix ..." verb most repos actually use — see the
# comment above BUG_SUBJECT_RE there for why one pattern reads both). Set
# HEATMAP_BUG_COMMIT_REGEX to override it for a repo that spells fixes some other way, or
# to "" to disable the heuristic. Separately, when GITHUB_TOKEN/GH_TOKEN is set, this
# script also crawls the analysed repo's own GitHub "type: bug"/"type: regression" labels
# (fetch_bugs.py) for a second, more precise signal: a commit whose message references a
# labelled issue number ("Closes gh-N", "Fixes #N") is bug-linked regardless of its
# subject wording. That crawl is opt-in because GitHub's search API caps unauthenticated
# callers at 10 req/min, which would take hours against a history the size of Spring's.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Code under analysis = a whole git repo (so git paths line up with the file walk).
# Artifacts land beside it in .codecity/ unless told otherwise — self-contained HTML,
# so that folder can be published, zipped or thrown away without touching the sources.
export HEATMAP_REPO="${1:-${HEATMAP_REPO:-$(git rev-parse --show-toplevel)}}"
export HEATMAP_REPO="$(cd "$HEATMAP_REPO" && pwd)"
export HEATMAP_OUT="${2:-${HEATMAP_OUT:-$HEATMAP_REPO/.codecity}}"
export HEATMAP_PYLIBS="$SCRIPT_DIR/.pylibs"

# One-time: vendor the tree-sitter parsers the complexity pass needs.
if [ ! -d "$HEATMAP_PYLIBS" ]; then
  echo "[0/6] vendoring tree-sitter into $HEATMAP_PYLIBS ..."
  pip3 install -q -r "$SCRIPT_DIR/requirements.txt" --target "$HEATMAP_PYLIBS"
fi

# Exclude build outputs (Maven target/, Gradle build/out/.gradle), IDE/agent
# metadata, and git worktrees (.claude/worktrees and .conductor hold full
# duplicate copies of the repo). Honour a pre-set value so callers can tune it.
export HEATMAP_PRUNE="${HEATMAP_PRUNE:-target,build,out,.gradle,.claude,.conductor,node_modules,.idea,.venv,.codegraph,.serena,__pycache__,dist}"

# HEATMAP_BUG_COMMIT_REGEX is intentionally left unset here so build_heatmap.py's own
# default heuristic applies; a caller who has already exported it (a real override, or
# "" to disable it) is honoured as-is, the same way HEATMAP_PRUNE is above. Forcing a
# single hardcoded pattern on every repo run through this script is exactly the bug that
# made Spring's city colour flat: petclinic's Conventional Commits worked, Spring's plain
# "Fix ..." subjects never matched, and there was no way to tell the two apart from here.

export HEATMAP_TITLE="${HEATMAP_TITLE:-$(basename "$HEATMAP_REPO") Codemap}"
export CODECITY_TITLE="${CODECITY_TITLE:-Code City: $(basename "$HEATMAP_REPO")}"

# Ctrl/⌘-click a file tile to open it in an editor (in-page picker: VS Code / IntelliJ).
# REPO_ABS defaults to HEATMAP_REPO, which is what the tsv paths are relative to.
export HEATMAP_OPEN_IN="vscode"

cd "$SCRIPT_DIR"
echo "repo:  $HEATMAP_REPO"
echo "out:   $HEATMAP_OUT"
mkdir -p "$HEATMAP_OUT"

echo "[1/5] cognitive complexity (tree-sitter)..."
python3 compute_complexity.py
echo "[2/5] fan-in / fan-out..."
python3 compute_fanio.py

# Optional accurate bug signal (see the header comment above for why this is opt-in):
# crawl the analysed repo's own GitHub bug labels into bug_issues.txt before the walk
# below picks it up. Only attempted when a token is available and the repo's origin
# remote actually looks like a GitHub "owner/repo". Never fatal: a failed or skipped
# crawl just leaves build_heatmap.py with the subject heuristic alone.
if [ -n "${GITHUB_TOKEN:-}${GH_TOKEN:-}" ]; then
  ORIGIN_REPO="$(git -C "$HEATMAP_REPO" remote get-url origin 2>/dev/null \
    | sed -E 's#^(https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(\.git)?$#\2#')"
  if [ -n "$ORIGIN_REPO" ] && [[ "$ORIGIN_REPO" == */* ]]; then
    echo "[bugs] GITHUB_TOKEN set: crawling $ORIGIN_REPO's 'type: bug' / 'type: regression' issues for a precise bug signal..."
    FETCH_BUGS_REPO="$ORIGIN_REPO" python3 fetch_bugs.py \
      || echo "[bugs] fetch_bugs.py failed; continuing with the subject-regex heuristic only" >&2
  else
    echo "[bugs] origin remote ($ORIGIN_REPO) is not a github.com owner/repo; skipping the bug-label crawl" >&2
  fi
else
  echo "[bugs] no GITHUB_TOKEN/GH_TOKEN set; skipping the GitHub bug-label crawl and relying on the subject-regex heuristic" >&2
fi

echo "[3/5] join git history + size into codemap.tsv..."
# Captured (not just streamed) so the subtitle below can read the walk's own bug-commit
# count back out, rather than re-deriving it here with a second copy of the detection
# regex that could silently drift from the one build_heatmap.py actually applied.
BUILD_HEATMAP_LOG="$(python3 build_heatmap.py 2>&1 | tee /dev/stderr)"

# Build a data-driven subtitle, then render.
FILES=$(($(wc -l < "$HEATMAP_OUT/codemap.tsv") - 1))
COMMITS=$(git -C "$HEATMAP_REPO" rev-list --count HEAD)
BUGFIX="$(sed -n -E 's/.*walked [0-9]+ commits, ([0-9]+) flagged as bug-linked.*/\1/p' <<<"$BUILD_HEATMAP_LOG")"
BUGFIX="${BUGFIX:-0}"
export HEATMAP_SUBTITLE="${FILES} source Java files · ${COMMITS} commits walked · ${BUGFIX} bug-fix commits."

echo "[4/5] render interactive HTML..."
python3 render_heatmap.py

echo "[5/6] render Code City HTML..."
HEATMAP_TITLE="$CODECITY_TITLE" python3 render_codecity.py

echo "[6/6] render combined side-by-side (2D codemap <-> 3D city)..."
python3 render_combined.py

echo "done -> $HEATMAP_OUT/codemap.html"
echo "city -> $HEATMAP_OUT/codecity.html"
echo "both -> $HEATMAP_OUT/combined.html"
