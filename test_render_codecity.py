#!/usr/bin/env python3
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
SAMPLE_TSV = REPO_ROOT / "petclinic-backend/docs/generated/codemap/codemap.tsv"


class RenderCodecityTest(unittest.TestCase):
    def test_renders_standalone_threejs_codecity(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            env["HEATMAP_TITLE"] = "Code City"
            subprocess.run(
                [
                    "python3",
                    str(SCRIPT_DIR / "render_codecity.py"),
                    str(SAMPLE_TSV),
                ],
                check=True,
                cwd=SCRIPT_DIR,
                env=env,
            )

            html_path = Path(tmp) / "codecity.html"
            html = html_path.read_text()

            self.assertIn("<title>Code City</title>", html)
            self.assertIn("three.module.js", html)
            self.assertIn("OrbitControls", html)
            self.assertIn("d3@7", html)
            self.assertIn('id="scene"', html)
            self.assertIn("__CODEMAP_3D_READY__", html)
            self.assertIn("const FILES =", html)
            self.assertIn('id="areaMetric"', html)
            self.assertIn("const areaSelect", html)
            self.assertIn("areaMetric", html)
            self.assertIn("cognitive complexity", html)
            self.assertNotIn("cyclomatic", html)   # the metric is Sonar cognitive complexity, not cyclomatic
            self.assertIn(">committers</option>", html)   # committers-per-file metric (short label)
            # Persistent labels show ONLY the class name now — the commits sub-line is gone.
            self.assertNotIn("by ${devs} devs", html)
            self.assertIn("Persistent labels show ONLY the class name", html)
            # View switch (Classes / Packages / Modules) now lives INLINE in the title
            # row (h1), not on a separate "Code City of:" row under the title.
            h1 = html[html.index("<h1>"):html.index("</h1>")]
            self.assertIn('<select id="viewMode"', h1)
            self.assertNotIn("Code City of:", html)
            self.assertIn('value="classes" selected', html)
            self.assertIn('value="packages" id="packageOpt"', html)
            self.assertIn('value="modules" id="moduleOpt">Modules (Maven/Gradle)', html)
            self.assertIn("const PACKAGES =", html)
            self.assertIn("const MODULES =", html)
            self.assertIn("function activeDataset", html)
            self.assertIn('id="shortcuts"', html)   # controls help pinned bottom-right
            self.assertIn("Drag to pan<br>", html)  # shortcuts one-per-line
            # Hover: a bullet list of every metric, with area/height/colour markers.
            self.assertIn('class="props"', html)
            self.assertIn("const HOVER_PROPS", html)
            self.assertIn("function marksFor", html)
            self.assertIn("mk-area", html)
            self.assertIn("mk-height", html)
            self.assertIn("&#x2194;&#xFE0F;", html)   # area marker is the left/right arrow now
            self.assertNotIn("&#x1F7E7;", html)        # not the old orange square
            self.assertIn("&#x2195;&#xFE0F;", html)   # height marker unchanged (up/down arrow)
            self.assertIn("cbar-mark", html)
            # Per-KLOC densities are folded onto their base metric's line, dimmed.
            self.assertIn('class="perkloc"', html)
            self.assertIn("/ KLOC)", html)
            # Colour ramp can be linear or log; skewed /KLOC metrics default to log.
            # One bit, so it is a checkbox that re-ticks itself when the metric changes,
            # while a manual tick is remembered per metric for the session.
            self.assertIn('id="colorLog"', html)
            self.assertNotIn('id="colorScale"', html)
            self.assertIn("const colorLogOverrides = new Map()", html)
            self.assertIn("function syncColorLogCheck", html)
            self.assertIn("colorLogOverrides.set(colorMetricKey(), colorLogCheck.checked)", html)
            self.assertIn("function wantsLog", html)
            self.assertIn("function colorT", html)
            self.assertIn("Math.log1p", html)
            self.assertIn("LOG_DEFAULT_METRICS", html)
            # Tooltip title is the real filename, incl. extension.
            self.assertIn("file.path.slice(file.path.lastIndexOf", html)
            # Package labels now default to on-the-floor edges.
            self.assertIn('value="floor" selected', html)
            # Package-pattern filter (victor..*Service · ..repo.. · *Service).
            self.assertIn('id="pkgFilter"', html)
            self.assertIn("function patternToRegExp", html)
            self.assertIn("function filteredDataset", html)
            # Package-name labels: switchable floating tags vs. on-the-floor edges.
            self.assertIn('id="pkgLabelMode"', html)
            self.assertIn("on the floor (edges)", html)
            self.assertIn("district-label", html)
            self.assertIn("function addFloorName", html)
            self.assertIn("function addPackageLabel", html)
            self.assertIn("function placeFloorLabelMesh", html)   # global no-overlap floor-label guard
            self.assertIn("instability", html)           # Ce/(Ce+Ca) metric
            # One knob per row, each dropdown followed by its own /kloc checkbox:
            #   AREA   [ dropdown ] [ ] /kloc
            #   HEIGHT [ dropdown ] [ ] /kloc
            #   COLOR  [ dropdown ] [x] /kloc [ ] lg
            self.assertIn("grid-template-columns: auto 1fr auto auto;", html)
            self.assertNotIn('class="sep" aria-hidden="true">/</span>', html)
            self.assertIn("> /kloc\n", html)
            self.assertIn("> lg\n", html)
            for base in ("area", "height", "color"):
                self.assertIn('id="%sKloc"' % base, html)
            self.assertNotIn("/ KLOC</option>", html)   # density lives in the checkbox, not the titles
            self.assertLess(html.index('id="areaMetric"'), html.index('id="areaKloc"'))
            self.assertLess(html.index('id="areaKloc"'), html.index('id="heightMetric"'))
            self.assertLess(html.index('id="heightMetric"'), html.index('id="heightKloc"'))
            self.assertLess(html.index('id="heightKloc"'), html.index('id="colorMetric"'))
            self.assertLess(html.index('id="colorMetric"'), html.index('id="colorKloc"'))
            self.assertLess(html.index('id="colorKloc"'), html.index('id="colorLog"'))
            # A ticked /kloc swaps the raw metric for its density twin.
            self.assertIn("const PER_KLOC = {", html)
            self.assertIn("function syncKlocChecks", html)
            self.assertIn("const areaMetricKey = ", html)
            # A metric taken by one dropdown is greyed out in the other two.
            self.assertIn("function syncMetricOptions", html)
            self.assertIn("const metricSelects = [areaSelect, heightSelect, colorSelect]", html)
            self.assertIn("PetClinicMcp.java", html)
            self.assertIn('"district": "victor.training.petclinic.mcp"', html)
            self.assertIn("new THREE.BoxGeometry", html)
            self.assertIn("controls.mouseButtons.LEFT = THREE.MOUSE.PAN", html)
            self.assertIn("event.metaKey", html)
            self.assertIn("event.ctrlKey", html)
            self.assertIn("CSS2DRenderer", html)
            # Class labels: up to MAX_LABELS candidates, de-overlapped in screen space each frame.
            self.assertIn("setupLabels", html)
            self.assertIn("updateLabelVisibility", html)
            self.assertIn("city-label", html)
            # Drill-down: Shift-click a floor/building to scope in, breadcrumb / ground to step out.
            self.assertIn('id="breadcrumb"', html)
            self.assertIn("let scopePath", html)
            self.assertIn("function targetAtPointer", html)
            self.assertIn("function scopeUp", html)
            self.assertIn("districtStep", html)
            self.assertIn('rel="icon"', html)
            self.assertIn("formatDistrictHover", html)
            self.assertIn("insertPackage", html)
            self.assertIn("for (const node of root.descendants())", html)
            self.assertIn('userData.kind = "package"', html)
            self.assertIn("controls.zoomToCursor = true", html)
            self.assertIn("function openInEditor", html)
            self.assertIn("vscode://file", html)
            self.assertIn('window.addEventListener("dblclick", onDoubleClick)', html)
            # Hover UI: metrics box pinned top-right, now led by a 3-line identity
            # header (class name / folder / package). The old top-center FQN banner
            # (#classTitle) is gone; its info lives in the header instead.
            self.assertNotIn('id="classTitle"', html)          # banner element removed
            self.assertNotIn("#classTitle {", html)            # and its CSS rule
            self.assertIn("function folderPrefix", html)       # dir minus package = module+source root
            self.assertIn("function identityHeader", html)
            self.assertIn("function hoverHeaderForFile", html)
            self.assertIn('class="idhdr"', html)
            self.assertIn('class="cls"', html)                 # bold simple class name
            self.assertIn('class="folder"', html)              # dimmer module/source-root prefix
            self.assertIn('class="pkg"', html)                 # dotted package
            self.assertIn("hoverHeaderForFile(file) +", html)  # header sits above the metrics list
            # The long dotted package MUST wrap inside the panel, never widen it.
            self.assertIn("overflow-wrap: anywhere", html)
            self.assertIn("word-break: break-word", html)
            self.assertNotIn("positionHoverNearObject", html)   # tooltip is CSS-pinned, not cursor-following
            self.assertIn("setRotationPivotToViewportCenter", html)
            self.assertIn("new THREE.Plane", html)
            # Cross-view link with the 2D codemap when embedded side by side: announce the
            # hovered file to the parent hub and spotlight the file the codemap points back at.
            self.assertIn("function postCityHover", html)
            self.assertIn("function applyExternalHighlight", html)
            self.assertIn('codemapLink: true, from: "city"', html)
            self.assertIn('d.from === "city"', html)             # ignore our own echoes
            # "Build this for your own repo" recipe: button, overlay, baked-in command.
            self.assertIn('id="howtoToggle"', html)
            self.assertIn("Build a Code City for any source folder", html)
            self.assertIn("const BUILD_CMD =", html)
            # BUILD_CMD is JSON-embedded, so quotes are backslash-escaped in the HTML.
            self.assertIn(r'HEATMAP_REPO=\"$REPO\" HEATMAP_OUT=\"$REPO/.codecity\"', html)
            self.assertIn(str(SCRIPT_DIR), html)
            # First-run intro: an annotated hero building wired to the metric selectors,
            # with AREA drawn on the roof (top face), not the base.
            self.assertIn("function buildIntro", html)
            self.assertIn("What each building tells you", html)
            self.assertIn("introHatch", html)
            self.assertIn("top face = footprint, drawn on the roof", html)
            # Change-set filter: off / highlight changed / only changed. Each file row
            # carries a boolean `changed` flag computed from the current git change set.
            self.assertIn('id="changeMode"', html)
            self.assertIn('value="highlight"', html)
            self.assertIn('>only changed</option>', html)
            self.assertIn("const HAS_CHANGES =", html)
            self.assertIn('"changed":', html)                 # baked per-building flag
            self.assertIn("function styleForChanges", html)   # grey-out pass
            self.assertIn("function grayFor", html)           # grey ramp for unchanged
            self.assertIn("function changeMode", html)
            self.assertIn('changeMode() === "hide"', html)    # "only changed" filters the dataset
            # Translucency alone carries the signal — no border shell around changed
            # buildings, which only crowded the city.
            self.assertNotIn("addChangeOutline", html)
            self.assertNotIn("THREE.BackSide", html)
            # The change set now defaults to "show everything" (was "highlight changed"):
            # the city opens fully coloured, and the filter is opt-in.
            self.assertIn('<option value="off" selected>show everything</option>', html)
            self.assertNotIn('value="highlight" selected', html)
            # An empty change set still disables the changed-only modes and stays on "off".
            self.assertIn('changeSelect.value = "off"', html)
            # Cursor: hand over a building, arrow over empty space, 4-way move while dragging.
            self.assertIn('hoverCursor = hit ? "pointer" : "default"', html)
            self.assertIn("function applyCursor", html)
            self.assertIn("let isDragging", html)
            # Flat floor package labels are spun to face the camera each frame (no upside-down text).
            self.assertIn("function updateFloorLabelFacing", html)
            self.assertIn("floorLabelMeshes", html)
            # Unchanged buildings are not label candidates in highlight mode.
            self.assertIn("entry.file.changed)", html)
            self.assertIn("const labelPool", html)

    def test_change_set_auto_detects_pr_branch(self):
        """With NO config, a feature branch is recognised as a PR and its whole
        branch diff (vs the base branch) becomes the change set."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            git("init", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            src = repo / "src/main/java/app"
            src.mkdir(parents=True)
            (src / "Base.java").write_text("class Base {}\n")
            git("add", "-A")
            git("commit", "-m", "base")
            git("checkout", "-b", "feature")               # a PR-like feature branch
            (src / "Feature.java").write_text("class Feature {}\n")
            git("add", "-A")
            git("commit", "-m", "feat")

            hdr = ("path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                   "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n")
            row = lambda p: f"{p}\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n"
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + row("src/main/java/app/Base.java") + row("src/main/java/app/Feature.java"))

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)                 # REPO_ABS -> the temp repo
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)           # rely purely on auto-detection
            env.pop("GITHUB_BASE_REF", None)
            subprocess.run(["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                           check=True, cwd=str(repo), env=env)

            html = (repo / "codecity.html").read_text()
            import json
            import re
            files = json.loads(re.search(r"const FILES = (\[.*?\]);\nconst PACKAGES", html, re.S).group(1))
            by_path = {f["path"]: f for f in files}
            self.assertTrue(by_path["src/main/java/app/Feature.java"]["changed"])   # branch-only file
            self.assertFalse(by_path["src/main/java/app/Base.java"]["changed"])     # also on the base
            self.assertIn("const HAS_CHANGES = true", html)

    def test_walks_back_to_the_last_commit_that_touches_analysed_files(self):
        """No PR, no Java edits in the working tree, and the recent commits only
        moved docs -> the change set must walk BACK through history to the last
        commit that really touched an analysed class, and name it (hash, subject,
        GitHub link) so the page can say what the delta is."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            git("init", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            git("remote", "add", "origin", "git@github.com:acme/demo.git")
            src = repo / "src/main/java/app"
            src.mkdir(parents=True)
            (src / "Base.java").write_text("class Base {}\n")
            git("add", "-A")
            git("commit", "-m", "base")
            (src / "Base.java").write_text("class Base { int x; }\n")
            git("add", "-A")
            git("commit", "-m", "fix: the only commit that touches code\n\nlong body here")
            wanted = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                    check=True, capture_output=True, text=True).stdout.strip()
            (repo / "README.md").write_text("docs\n")             # two commits that touch
            git("add", "-A")                                      # nothing the city renders
            git("commit", "-m", "docs: readme")
            (repo / "notes.txt").write_text("notes\n")
            git("add", "-A")
            git("commit", "-m", "chore: notes")
            (repo / "scratch.txt").write_text("dirty\n")           # dirty tree, but no Java

            hdr = ("path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                   "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n")
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + "src/main/java/app/Base.java\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n")

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            env.pop("GITHUB_REF", None)
            env["PATH"] = "/usr/bin:/bin"                          # keep `gh` out of the picture
            subprocess.run(["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                           check=True, cwd=str(repo), env=env)

            html = (repo / "codecity.html").read_text()
            import json
            import re
            source = json.loads(re.search(r"const CHANGE_SOURCE = (\{.*?\});", html, re.S).group(1))
            self.assertEqual(source["kind"], "commit")             # not "working tree"
            self.assertEqual(source["label"], "commit: " + wanted[:7])
            self.assertEqual(source["detail"], "fix: the only commit that touches code")
            self.assertIn("long body here", source["tooltip"])     # full message on hover
            self.assertEqual(source["url"], f"https://github.com/acme/demo/commit/{wanted}")
            files = json.loads(re.search(r"const FILES = (\[.*?\]);\nconst PACKAGES", html, re.S).group(1))
            self.assertTrue(files[0]["changed"])                   # that commit's file lights up
            self.assertIn("const HAS_CHANGES = true", html)
            # the one-line "what am I looking at" readout under the change-set selector
            self.assertIn('id="changeSourceRow"', html)
            self.assertIn("function renderChangeSource", html)
            self.assertIn('changeMode() !== "off" && HAS_CHANGES', html)
            # ...and the row's own `display: flex` must not outrank the hidden attribute,
            # or "show everything" keeps showing a diff it is not using.
            self.assertIn(".changeSourceRow[hidden] { display: none; }", html)

    def test_dirty_java_working_tree_wins_over_history(self):
        """An uncommitted edit to an analysed class is still the change set — the
        history walk-back is a fallback, not a replacement."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            git("init", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            src = repo / "src/main/java/app"
            src.mkdir(parents=True)
            (src / "Base.java").write_text("class Base {}\n")
            git("add", "-A")
            git("commit", "-m", "base")
            (src / "Base.java").write_text("class Base { int x; }\n")   # dirty Java

            hdr = ("path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                   "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n")
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + "src/main/java/app/Base.java\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n")

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            env["PATH"] = "/usr/bin:/bin"
            subprocess.run(["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                           check=True, cwd=str(repo), env=env)

            html = (repo / "codecity.html").read_text()
            import json
            import re
            source = json.loads(re.search(r"const CHANGE_SOURCE = (\{.*?\});", html, re.S).group(1))
            self.assertEqual(source["kind"], "working")
            self.assertEqual(source["label"], "working tree")
            self.assertIn("uncommitted file", source["detail"])
            self.assertIn("on main", source["detail"])
            self.assertIn("src/main/java/app/Base.java", source["tooltip"])
            self.assertEqual(source["url"], "")                     # nothing to link to on GitHub

    def test_offers_the_last_ten_commits_that_touched_code(self):
        """The history diff is not pinned to whatever landed last: the page bakes a
        dropdown of the recent commits that really touched analysed classes — capped
        at ten, newest first, docs-only commits skipped — each carrying its own change
        scope and a GitHub link, so the reader can step back through the deltas."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            git("init", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            git("remote", "add", "origin", "git@github.com:acme/demo.git")
            src = repo / "src/main/java/app"
            src.mkdir(parents=True)
            for i in range(12):                                    # twelve code commits...
                (src / "Base.java").write_text(f"class Base {{ int x{i}; }}\n")
                git("add", "-A")
                git("commit", "-m", f"code {i}")
            (repo / "README.md").write_text("docs\n")              # ...under a docs-only one
            git("add", "-A")
            git("commit", "-m", "docs: readme")

            hdr = ("path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                   "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n")
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + "src/main/java/app/Base.java\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n")

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            env.pop("GITHUB_REF", None)
            env["PATH"] = "/usr/bin:/bin"
            subprocess.run(["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                           check=True, cwd=str(repo), env=env)

            html = (repo / "codecity.html").read_text()
            choices = json.loads(
                re.search(r"const COMMIT_CHOICES = (\[.*?\]);   //", html, re.S).group(1))
            self.assertEqual(len(choices), 10)                      # capped, docs commit skipped
            self.assertEqual([c["subject"] for c in choices],
                             [f"code {i}" for i in range(11, 1, -1)])   # newest first
            self.assertTrue(all(c["url"].startswith("https://github.com/acme/demo/commit/")
                                for c in choices))
            self.assertTrue(all(len(c["short"]) >= 7 for c in choices))
            self.assertTrue(all(c["when"] for c in choices))         # relative date for the tooltip
            # every entry carries the row keys for all three datasets, so switching
            # commits in the browser is a Set lookup and re-flags packages/modules too
            self.assertEqual(choices[0]["files"], ["src/main/java/app/Base.java"])
            self.assertIn("app", choices[0]["districts"])
            self.assertIn("src/main/java/app", choices[0]["dirs"])
            self.assertIn(".", choices[0]["dirs"])                   # the repo-root module row
            # the combo itself, and the commit id linking to GitHub next to it
            self.assertIn('<select id="commitPick"', html)
            self.assertIn("function applyCommitChoice", html)
            self.assertIn("hasCommitHistory", html)


if __name__ == "__main__":
    unittest.main()
