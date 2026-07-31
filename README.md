# Codemap

An interactive, self-contained HTML heatmap of the codebase: a **treemap** (rectangle
area = file bytes, color = a metric ratio you pick) plus a **log–log scatter**
(lines vs bug-fix commits). Open the generated page in any browser — it pulls Plotly
from a CDN and embeds all data inline, so there is no server.

Output:

- [`../../generated/codemap/codemap.html`](../../generated/codemap/codemap.html)
- [`../../generated/codemap/codecity.html`](../../generated/codemap/codecity.html) Three.js CodeCity

## Run

```bash
pip install -r requirements.txt --target .pylibs   # one-time (vendors tree-sitter)
./generate.sh
```

`generate.sh` analyzes the **whole git repo** (so commit paths line up with the file
walk) and writes all artifacts into `petclinic-backend/docs/generated/codemap/`.

## What each metric means

The treemap color is a **ratio** of any numerator over any denominator (selectable in
the page): `bugs`, `commits`, `complexity`, `fan_in`, `fan_out` over `lines`, `commits`,
etc. The scale is clamped at the p95 so a few extreme files don't wash out the rest.

**Open a file in your editor:** ⌘/Ctrl-click a file tile to jump straight to it. An
in-page picker chooses **VS Code** (`vscode://file/…`) or **IntelliJ**. IntelliJ uses its
built-in web server, so the IDE must be running with *Settings ▸ Build, Execution,
Deployment ▸ Debugger ▸ "Allow unsigned requests"* enabled. Disable the whole feature by
unsetting `HEATMAP_OPEN_IN`.

| Column | Meaning |
| --- | --- |
| `commits` | non-merge commits that touched the file (full history) |
| `bug_commits` | of those, commits whose subject is a Conventional-Commit `fix:` |
| `cognitive_complexity` | Sonar-style cognitive complexity (tree-sitter, summed over methods) |
| `fan_in` / `fan_out` | how many repo files reference this file / it references (internal coupling only) |

## Pipeline

| Step | Script | Produces |
| --- | --- | --- |
| 1 | `compute_complexity.py` | `complexity-per-{class,file}.tsv` |
| 2 | `compute_fanio.py` | `fanio-per-file.tsv` |
| 3 | `build_heatmap.py` | `codemap.tsv` (joins git history + file size + steps 1–2) |
| 4 | `render_heatmap.py` | `codemap.html` |
| 5 | `render_codecity.py` | `codecity.html` |

## CodeCity

`codecity.html` renders the same TSV as a Three.js CodeCity. Drag to pan,
Cmd/Ctrl-drag to rotate, scroll to zoom around the mouse cursor, and Cmd/Ctrl-double-click
a building to open its Java file in VS Code. The 2D city layout is computed in-browser
with D3 treemap; Three.js extrudes each file tile into a building.

**City geometry & camera** — tuned to Wettel's original CodeCity plates. The ground is
a **landscape rectangle** (1.6:1), not a square, and the opening shot is *computed* from
the city's bounding box rather than hard-coded: a long 30° lens placed far enough back
that the whole plate fits, low over the horizon and swung off-axis. There is **no fog** —
far districts stay as crisp as near ones. Three scales adapt to repo size, so a 60-file
toy and a 5000-file monster both read as cities instead of needles or flat tiles:

- **height** scales off the *median footprint* (footprints shrink as the file count
  grows on a fixed plate, so the height scale shrinks with them); above the p95 the
  curve goes logarithmic, so one monster class doesn't spike the whole skyline;
- **streets narrow with nesting depth** — boulevards between top-level modules, alleys
  between leaf packages, instead of one flat gap that eats a deep tree's plate;
- a class **name appears only once its roof is ≥ 26 px on screen**, so a huge city
  zoomed out is a clean plate and the names come back as you zoom in;
- **package names are written flat on their own floor**, in a header strip the treemap
  *reserves* along each district's near edge (a share of the district's own depth, so a
  big package gets big letters). The strip is not decoration: children terraces rise
  above their parent's floor and tile all of it, so text laid anywhere else is buried.

**The control panel** stacks one knob per row, each row a single question, so the three
visual axes read as independent choices rather than one wide toolbar:

| row | what it sets |
| --- | --- |
| `FILTER` | AspectJ-style glob (`victor..*Service`, `..repo..`, `*Service`). It is a text box **with a dropdown**: the generator splits every class name on CamelCase and offers the leading word of each family that has ≥ 3 classes (`..Pet*`, `..Owner*`, …) as a ready-made glob. |
| `PRESET` | ten coloured bubbles, one click each: a saved reading of the city (overview, hotspots, bug density, complexity density, knowledge risk, coupling, instability, churn vs. team, plain size, dependencies). A bubble sets all three metrics *and* the four bits below, and lights up whenever the panel happens to show its reading. |
| `AREA` / `HEIGHT` / `COLOR` | the metric on that axis, plus a **`/kloc`** checkbox that swaps a raw count for its density twin (complexity, commits, bugfixes). Where no density exists the checkbox greys out instead of disappearing, so the rows keep their shape. Colour also carries **`lg`**, the log-vs-linear ramp: it ticks itself to what the chosen metric wants and remembers your override per metric for the session. |
| `PACKAGES` | package-name style: floating tags, on the floor, or off. |
| `CHANGES` | the change-set filter (below). |

Whatever one metric dropdown shows is greyed out in the other two — spending two of the
city's three channels on the same number says nothing twice.

**Change-set filter:** a **Change set** selector focuses the city on the files in the
*current git change set*, baked in when the page is generated. Three modes:

1. **show everything** — the normal city (default).
2. **highlight changed** — unchanged buildings drain to grey and drop to 50% opacity;
    changed buildings keep their full colour and get a thick black border so they pop.
3. **only changed** — unchanged buildings are removed from the layout entirely, so the
    treemap collapses to just the change set.

What counts as "changed" is **auto-detected** — no configuration needed (computed
against `HEATMAP_REPO`, in precedence order):

- On a **PR / feature branch** (there are commits ahead of the base branch) → the whole
  branch diff `base...HEAD` plus any uncommitted edits: *everything this PR touches*. The
  base branch is detected from `GITHUB_BASE_REF` in GitHub Actions, otherwise from the
  remote's default branch (`origin/HEAD` → `origin/main`). Sitting **on** the base branch
  (e.g. `main`) is not a PR.
- else, **uncommitted work** (staged + unstaged + untracked vs `HEAD`) *that touches a file
  the city renders* — *you haven't committed yet, so you see the files you've changed*.
- else, the **most recent commit that touches an analysed file** — usually `HEAD`, but the
  detection keeps **walking back through history** past commits that only moved docs,
  configs or non-Java tests. Without this, a repo whose last few commits were a README
  tweak and a module rename would render an empty change set: nothing highlighted, nothing
  to look at. (Merge commits are skipped; the walk gives up after 2000 commits.)

`HEATMAP_CHANGED_BASE` is **optional** — it only *overrides* the auto-detected base (e.g.
to diff against a release branch instead of `main`); you never need to set it for the
normal PR / dirty-tree / last-commit flow.

When the change set is empty the highlight/hide modes are disabled and the selector
reads "no changes".

**What am I looking at?** Picking *highlight changed* or *only changed* reveals a one-line
readout under the selector naming the **source of the diff**, because "42 changed" alone
never says *changed relative to what*:

| Source | Reads | Links to |
| --- | --- | --- |
| PR | `PR #123` + its title | the PR on GitHub |
| feature branch with no PR yet | `branch feat/x` + `all commits since origin/main …` | the GitHub `compare/` view |
| commit (incl. one found by walking back) | a **dropdown** of the last 10 commits that touched code, then `a5d03cb` + `3 days ago` | the picked commit on GitHub |
| dirty tree | `working tree` + `N uncommitted files on <branch>` | — (nothing to link to) |

The line truncates with an ellipsis to the panel width; **hovering** shows the full commit
message / PR body, and **clicking** opens it on GitHub. The PR number comes from
`GITHUB_REF` on CI, else from `gh pr view` locally (both best-effort — with neither, a
branch falls back to the compare link).

**Stepping back through history.** When the diff comes from a commit, being pinned to
whatever landed last is arbitrary — so the generator bakes the **last 10 commits that
really touched rendered code** (same walk, same docs-only skipping) into a dropdown.
Picking one re-flags the whole city against that commit and updates the id next to the
combo, which links to it on GitHub. Each entry carries its change scope pre-computed in
the three key spaces the datasets use — file path, dotted package, module dir — so
switching is a `Set` lookup per row and the Classes / Packages / Modules lenses all stay
correct without re-deriving any path logic in the browser.

**First-run intro:** on initial load the page draws a one-time overlay that annotates a
single "hero" building to make the three selectors concrete — the hatched **roof** = the
*area* metric, the **height** dimension line = the *height* metric, the **colour swatch** =
the *colour* metric — each tied by a connector line to the `<select>` that drives it.
Dismissed on the first drag/scroll/metric-change (or the "Got it" button).

**Build it for your own repo:** the page has a compact **"⚒ Build for your repo"** button
in the **bottom-left corner**. It opens a copy-pasteable recipe that re-runs this exact
pipeline against any other folder of Java sources and opens the resulting city — just edit
`REPO`.
The recipe drives `generate.sh` via `HEATMAP_REPO` / `HEATMAP_OUT` / `CODECITY_TITLE`
overrides, which `generate.sh` now honours (falling back to the PetClinic defaults when
unset).

`fetch_bugs.py` is the Spring-specific GitHub bug-label crawler from the original; it is
kept for provenance but **not** used here (PetClinic has no `type: bug` labels, so the
bug signal comes from Conventional-Commit `fix:` subjects instead — see `generate.sh`).

## Configuration (env vars)

Every script is repo-agnostic and driven by env vars (`generate.sh` sets them):

| Var | Purpose |
| --- | --- |
| `HEATMAP_REPO` | repo root to analyze (default: git toplevel of the script) |
| `HEATMAP_OUT` | directory for all `.tsv` / `.html` output (default: `HEATMAP_REPO`) |
| `HEATMAP_PRUNE` | comma-separated dir names to skip (build output, worktrees, …) |
| `HEATMAP_PYLIBS` | path to vendored tree-sitter (for `compute_complexity.py`) |
| `HEATMAP_BUG_COMMIT_REGEX` | regex on the commit subject that flags a bug-fix commit |
| `HEATMAP_BUG_FILE` | optional file of bug **issue numbers** (Spring mode; matched via `gh-NNN`/`#NNN` refs) |
| `HEATMAP_TITLE` / `HEATMAP_SUBTITLE` | page heading text |
| `HEATMAP_OPEN_IN` | `vscode` / `intellij` to enable ⌘/Ctrl-click-to-open (empty = off) |
| `HEATMAP_REPO_ABS` | absolute repo root for editor links (default: `HEATMAP_REPO`) |
| `HEATMAP_CHANGED_BASE` | **optional** override of the auto-detected base ref for the change-set filter (e.g. `origin/release-1.x`); unset = auto-detect PR base → uncommitted work → last commit |

## Provenance

These generators were originally written ad-hoc to produce the
[Spring Framework codemap](https://github.com/spring-projects/spring-framework) and
were recovered from a Claude Code session transcript, then parameterized (paths/title via
env, plus a Conventional-Commit bug mode) without changing their analysis logic. The
recovered generators were verified to reproduce the original Spring artifacts
byte-for-byte (`codemap.html`, both complexity TSVs, and `fanio-per-file.tsv`), and
every deterministic column of `codemap.tsv`.
