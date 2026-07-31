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
# Bug signal: a commit counts as a bug-fix when its subject matches
# ^(fix|bugfix)(:|(|!) — i.e. Conventional Commits. Override with
# HEATMAP_BUG_COMMIT_REGEX for a repo that spells its fixes differently.
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

# Conventional-commit bug-fix detection.
export HEATMAP_BUG_COMMIT_REGEX='^(fix|bugfix)(\(|:|!)'

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
echo "[3/5] join git history + size into codemap.tsv..."
python3 build_heatmap.py

# Build a data-driven subtitle, then render.
FILES=$(($(wc -l < "$HEATMAP_OUT/codemap.tsv") - 1))
COMMITS=$(git -C "$HEATMAP_REPO" rev-list --count HEAD)
BUGFIX=$(git -C "$HEATMAP_REPO" log --no-merges --pretty='%s' | grep -cE '^(fix|bugfix)(\(|:|!)' || true)
export HEATMAP_SUBTITLE="${FILES} source Java files · ${COMMITS} commits walked · ${BUGFIX} bug-fix commits (Conventional Commits 'fix:')."

echo "[4/5] render interactive HTML..."
python3 render_heatmap.py

echo "[5/6] render Code City HTML..."
HEATMAP_TITLE="$CODECITY_TITLE" python3 render_codecity.py

echo "[6/6] render combined side-by-side (2D codemap <-> 3D city)..."
python3 render_combined.py

echo "done -> $HEATMAP_OUT/codemap.html"
echo "city -> $HEATMAP_OUT/codecity.html"
echo "both -> $HEATMAP_OUT/combined.html"
