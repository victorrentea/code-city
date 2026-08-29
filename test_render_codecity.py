#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
# A real (small) run of the pipeline, kept as a fixture so the renderer can be tested
# without re-analysing a checkout: the PetClinic city these generators grew up on.
SAMPLE_TSV = SCRIPT_DIR / "testdata/codemap.tsv"


def adjacency(html, name):
    """Both adjacency maps ship with their keys interned (see _pack_adjacency): most of a
    big page was the same long path written out over and over. Give the tests back the
    path-keyed map the page itself inflates on load."""
    packed = json.loads(
        re.search(r"const %s = inflateAdjacency\((\{.*?\})\);\n" % name, html, re.S).group(1)
    )
    out = {}
    for view, data in packed.items():
        keys = data["keys"]
        out[view] = {keys[int(i)]: {keys[int(j)]: v for j, v in peers.items()}
                     for i, peers in data["adj"].items()}
    return out


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
            # Just "Modules": the (Maven/Gradle) gloss only widened the title combo.
            self.assertIn('value="modules" id="moduleOpt">Modules<', html)
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
            # The recipe clones the generators from GitHub: whoever opens a published
            # city has no local checkout of them to point at.
            self.assertIn("git clone https://github.com/victorrentea/code-city", html)
            self.assertIn("/code-city/generate.sh ~/workspace/your-repo", html)
            self.assertNotIn('SCRIPTS="', html)   # ...not a path from the machine that built it
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
            # The page opens ON the diff — a generated city is nearly always read to
            # answer "what did this change?" — and an empty change set removes the row
            # rather than leaving a selector whose three modes all draw the same city.
            self.assertIn('<option value="highlight" selected>highlight changed</option>', html)
            self.assertNotIn('value="off" selected', html)
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
            # ...and among them the order is prominence, not just height: the biggest
            # block and the hottest colour of the diff get named first.
            self.assertIn("function setupChangedLabels", html)
            self.assertIn("function blockVolume", html)
            self.assertIn("Math.max(vol, col) + 0.25 * Math.min(vol, col)", html)
            self.assertIn("makeLabel(entry, priority++, true)", html)   # exempt from the roof-size gate
            self.assertIn("if (!L.ignoreRoofGate &&", html)
            # "as many as fit on the screen" excludes the space under the opaque panel.
            self.assertIn("function panelBoxes", html)
            self.assertIn("const placed = panelBoxes();", html)

    def test_generated_javascript_parses(self):
        """The page is one big inlined script: a stray redeclared identifier takes the
        WHOLE city down — no canvas, no error anyone sees until they open it. Python
        tests happily assert on the text of a page that never runs, so parse it."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(SAMPLE_TSV)],
                check=True, cwd=SCRIPT_DIR, env=env,
            )
            html = (Path(tmp) / "codecity.html").read_text()
            blocks = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
            self.assertTrue(blocks, "the page should carry an inline script")
            module = Path(tmp) / "inline.mjs"
            module.write_text(max(blocks, key=len))
            done = subprocess.run([node, "--check", str(module)],
                                  capture_output=True, text=True)
            self.assertEqual(0, done.returncode, done.stderr)

    def test_coupling_streets(self):
        """The coupling overlay: a checkbox (off by default) that lays the dependency
        EDGES across the plate as roads on hover, routed AROUND the blocks in the way."""
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(SAMPLE_TSV)],
                check=True, cwd=SCRIPT_DIR, env=env,
            )
            html = (Path(tmp) / "codecity.html").read_text()

            # HELD, not ticked: a question you ask of one building for a second, not a
            # layer you leave on — and not a checkbox you forgot you ticked.
            self.assertNotIn("couplingStreets", html)
            self.assertIn("let roadKeyHeld = false;", html)
            self.assertIn("function streetsOn", html)
            self.assertIn("function onOverlayKey", html)
            self.assertIn('window.addEventListener("keyup", onOverlayKey)', html)
            self.assertIn('id="roadsHint"', html)   # ...so the help box has to say so
            self.assertIn("if (!streetsOn() || !entry)", html)
            self.assertIn("const COUPLING = inflateAdjacency(", html)
            # ...with its keys interned: on a 5000-class repo the two adjacency
            # maps written out in full were most of the page.
            self.assertIn("function inflateAdjacency", html)
            self.assertIn("function showStreetsFor", html)
            self.assertIn("function incomingAdjacency", html)
            # The pipes UNDER the city are gone: a buried run cost a glassed plate to
            # read, and the plate is the city.
            self.assertNotIn("couplingPipes", html)
            self.assertNotIn("PIPE_DEPTH", html)
            self.assertNotIn("function addPipe", html)
            self.assertNotIn("THREE.CylinderGeometry", html)
            # A road leaves the FOOTPRINT facing its peer, not the building's centre.
            self.assertIn("function baseAnchor", html)
            # ...and gets there AROUND the blocks: the plate is gridded, footprints are
            # marked built-up, and one Dijkstra per hover serves the whole bundle.
            self.assertIn("function ensureRoadGrid", html)
            self.assertIn("function roadSweep", html)
            self.assertIn("function roadBestState", html)
            # ...and the routes that come out of it are BUNDLED: peers lying the same way
            # share a trunk that thins each time one of them branches off, instead of
            # arriving at the building as a dozen parallel bands.
            self.assertIn("function bundleRoutes", html)
            self.assertIn("carried.get(kids[0]) === carried.get(current)", html)
            self.assertIn("if (!grid.free[nIdx]) continue;", html)
            self.assertIn("const ROAD_TURN_COST = 2.4;", html)   # corners cost, so roads run straight
            self.assertIn("roadGrid = null;", html)              # ...and are re-gridded on rebuild
            # Two blues: the roadway, and the traffic that says which way the edge runs.
            self.assertIn("const ROAD_PALE = 0x93c5fd;", html)
            self.assertIn("const FLOW_BLUE = 0x1d4ed8;", html)
            self.assertNotIn("PIPE_RED", html)
            self.assertIn("function updateStreetFlow", html)
            self.assertIn("flowTex.offset.y", html)
            # Width from the edge's weight, on a scale read off the whole view.
            self.assertIn("function roadWidth", html)
            self.assertIn("function couplingWeightScale", html)
            # A capped or filtered-down bundle owns up to it in the tooltip.
            self.assertIn("function wireNote", html)
            # Eighty roads are TWO draw calls: one merged geometry per surface. A mesh
            # per straight run is a couple of thousand of them, and the city stops
            # turning on the page whose whole point is that it turns.
            self.assertIn("function roadSink", html)
            self.assertIn("function sinkMesh", html)
            self.assertIn("sinkMesh(road, roadMaterial, 0), sinkMesh(lane, flowMaterial, 1)", html)

            coupling = adjacency(html, "COUPLING")
            classes = coupling["classes"]
            self.assertTrue(classes, "the fixture's edges should reach the page")
            rest = "petclinic-backend/src/main/java/victor/training/petclinic/rest"
            domain = "petclinic-backend/src/main/java/victor/training/petclinic/domain"
            # Weighted now: peer -> how many references the pair carries.
            owner_edges = classes[f"{rest}/OwnerRestController.java"]
            self.assertIn(f"{domain}/Owner.java", owner_edges)
            self.assertGreaterEqual(owner_edges[f"{domain}/Owner.java"], 1)
            # Folded up to packages, and self-edges (a package's own internals) dropped.
            packages = coupling["packages"]
            rest_pkg = packages["victor.training.petclinic.rest"]
            self.assertIn("victor.training.petclinic.domain", rest_pkg)
            # A package pair sums its classes' references, so it outweighs a class pair.
            self.assertGreater(rest_pkg["victor.training.petclinic.domain"],
                               owner_edges[f"{domain}/Owner.java"])
            for src, targets in packages.items():
                self.assertNotIn(src, targets, "a package must not pipe to itself")

    def test_cochange_crime_scene(self):
        """Change coupling: a colour metric for how far outside its own package a
        building's commits reach, and a hover overlay naming who it reaches to."""
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(SAMPLE_TSV)],
                check=True, cwd=SCRIPT_DIR, env=env,
            )
            html = (Path(tmp) / "codecity.html").read_text()

            # A colour metric of its own: no wires, no hover needed — the city shows
            # its own misplaced classes with nobody touching anything.
            self.assertIn('<option value="cochange_out">cross-package co-change</option>', html)
            self.assertIn('{ key: "cochange_out", label: "cross-package co-change" }', html)
            # No checkbox of its own: it IS that colour metric, asked of one building,
            # so it arms itself when the metric is picked and answers on Shift+hover.
            self.assertNotIn("cochangePartners", html)
            self.assertIn('colorMetricKey() === "cochange_out"', html)
            self.assertIn("const crimeHover = coChangeOn() && hit", html)
            self.assertIn("function onOverlayKey", html)
            self.assertIn("navKeyHeld && !event.metaKey", html)
            # ...and while it is answering, Shift is not also previewing a drill-in.
            self.assertIn("if (navKey && !crimeHover)", html)
            self.assertIn("function showCoChangeFor", html)
            self.assertIn("function clearCrimeScene", html)
            # Painted, not wired: the answer is a SET of buildings, read off colour.
            self.assertIn("const CRIME_SUBJECT = 0x1e3a8a;", html)
            self.assertIn("m.color.copy(grayFor(b.colorValue, b.maxColor));", html)
            # Strength = how often they changed together x how far apart they live.
            self.assertIn("peer[0] * peer[1]", html)
            # Restoring is repainting from the canonical colour, not from a snapshot.
            self.assertIn("m.color.copy(entry.mesh.userData.baseColor);", html)

            cochange = adjacency(html, "COCHANGE")
            self.assertTrue(cochange["classes"], "the fixture's co-changes should reach the page")
            # Every pair carries [shared commits, severity] and CROSSES a package
            # boundary — same-package partners are not a smell and are never written.
            for unit, peers in cochange["classes"].items():
                for peer, (shared, severity) in peers.items():
                    self.assertGreaterEqual(shared, 2)
                    self.assertGreater(severity, 0)
                    self.assertNotEqual(unit.rsplit("/", 1)[0], peer.rsplit("/", 1)[0])
            # The same relation is folded to each lens the city can be read at.
            self.assertTrue(cochange["packages"])

    def test_cochange_absent_without_the_edge_file(self):
        """No cochange-edges.tsv (an older run of the tool) renders normally: the row
        hides itself and the colour option removes itself, rather than half-working."""
        with tempfile.TemporaryDirectory() as tmp:
            solo = Path(tmp) / "codemap.tsv"
            solo.write_text(SAMPLE_TSV.read_text())
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(solo)],
                check=True, cwd=SCRIPT_DIR, env=env,
            )
            html = (Path(tmp) / "codecity.html").read_text()
            self.assertIn("const COCHANGE = inflateAdjacency(", html)
            self.assertIn('const HAS_COCHANGE = Object.values(COCHANGE || {})', html)
            self.assertIn('if (!HAS_COCHANGE) {', html)

    def test_coupling_pipes_absent_without_the_edge_file(self):
        """A codemap.tsv from an older tool run has no coupling-edges.tsv beside it:
        the page still renders, with the whole Coupling row removed rather than broken."""
        with tempfile.TemporaryDirectory() as tmp:
            solo = Path(tmp) / "codemap.tsv"
            solo.write_text(SAMPLE_TSV.read_text())
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(solo)],
                check=True, cwd=SCRIPT_DIR, env=env,
            )
            html = (Path(tmp) / "codecity.html").read_text()
            coupling = adjacency(html, "COUPLING")
            self.assertEqual({"classes": {}, "packages": {}, "modules": {}}, coupling)
            self.assertIn("const HAS_COUPLING =", html)
            # No edges => the help box does not advertise a key that does nothing.
            self.assertIn("if (!HAS_COUPLING) {", html)
            self.assertIn('document.getElementById("roadsHint")', html)

    def test_change_set_auto_detects_pr_branch(self):
        """With NO config, a feature branch is recognised as a PR and its whole
        branch diff (vs the base branch) becomes the change set."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

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

            hdr = (
                "path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n"
            )
            row = lambda p: f"{p}\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n"
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + row("src/main/java/app/Base.java") + row("src/main/java/app/Feature.java"))

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)                 # REPO_ABS -> the temp repo
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)           # rely purely on auto-detection
            env.pop("GITHUB_BASE_REF", None)
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                check=True,
                cwd=str(repo),
                env=env,
            )

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
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

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

            hdr = (
                "path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n"
            )
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + "src/main/java/app/Base.java\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n")

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            env.pop("GITHUB_REF", None)
            env["PATH"] = "/usr/bin:/bin"                          # keep `gh` out of the picture
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                check=True,
                cwd=str(repo),
                env=env,
            )

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
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            src = repo / "src/main/java/app"
            src.mkdir(parents=True)
            (src / "Base.java").write_text("class Base {}\n")
            git("add", "-A")
            git("commit", "-m", "base")
            (src / "Base.java").write_text("class Base { int x; }\n")   # dirty Java

            hdr = (
                "path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n"
            )
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + "src/main/java/app/Base.java\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n")

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            env["PATH"] = "/usr/bin:/bin"
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                check=True,
                cwd=str(repo),
                env=env,
            )

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
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

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

            hdr = (
                "path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n"
            )
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr + "src/main/java/app/Base.java\t100\t5\t1\t0\t0\t0\t0\t0\t0\t0\t0\t1\n")

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            env.pop("GITHUB_REF", None)
            env["PATH"] = "/usr/bin:/bin"
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                check=True,
                cwd=str(repo),
                env=env,
            )

            html = (repo / "codecity.html").read_text()
            choices = json.loads(
                re.search(r"const COMMIT_CHOICES = (\[.*?\]);   //", html, re.S).group(1))
            self.assertEqual(len(choices), 10)                      # capped, docs commit skipped
            self.assertEqual(
                [c["subject"] for c in choices],
                [f"code {i}" for i in range(11, 1, -1)],  # newest first
            )
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

    def test_bakes_the_before_of_every_changed_building(self):
        """"highlight changed" only says WHICH files a diff touched. The page also bakes
        what each of them measured on the other side of that diff — recovered from the
        blob at the very ref the change set is a diff of — so a changed building can be
        sketched dashed as it was, and the reader sees the direction of the change."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            git("init", "-b", "main")
            git("config", "user.email", "t@example.com")
            git("config", "user.name", "t")
            src = repo / "src/main/java/app"
            src.mkdir(parents=True)
            (src / "Grew.java").write_text("class Grew {\n  void a() {}\n}\n")
            (src / "Same.java").write_text("class Same {}\n")
            git("add", "-A")
            git("commit", "-m", "base")
            git("checkout", "-b", "feature")
            # One class grows a branch (complexity 0 -> 1) and a lot of text...
            (src / "Grew.java").write_text(
                "class Grew {\n  void a(int n) {\n    if (n > 0) { a(n - 1); }\n  }\n}\n")
            # ...and one is brand new, so it has no "before" at all.
            (src / "Added.java").write_text("class Added {}\n")
            git("add", "-A")
            git("commit", "-m", "feat: grow one class, add another")

            hdr = (
                "path\tbytes\tlines\tcommits\tbug_commits\tcommits_per_kloc\tbugs_per_kloc\t"
                "bugs_per_commit\tcognitive_complexity\tcomplexity_per_kloc\tfan_in\tfan_out\tcommitters\n"
            )
            row = lambda p, b, l, c: f"{p}\t{b}\t{l}\t2\t0\t0\t0\t0\t{c}\t0\t0\t0\t1\n"
            tsv = repo / "codemap.tsv"
            tsv.write_text(hdr
                           + row("src/main/java/app/Grew.java", 74, 5, 1)
                           + row("src/main/java/app/Added.java", 18, 1, 0)
                           + row("src/main/java/app/Same.java", 17, 1, 0))

            env = os.environ.copy()
            env["HEATMAP_REPO"] = str(repo)
            env["HEATMAP_OUT"] = str(repo)
            env.pop("HEATMAP_CHANGED_BASE", None)
            env.pop("GITHUB_BASE_REF", None)
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(tsv)],
                check=True,
                cwd=str(repo),
                env=env,
            )

            html = (repo / "codecity.html").read_text()
            before = json.loads(re.search(r"const BEFORE = (\{.*?\});\n", html, re.S).group(1))
            grew = before["src/main/java/app/Grew.java"]
            self.assertEqual(grew["lines"], 3)                     # 3 lines before, 5 now
            self.assertEqual(grew["bytes"], len("class Grew {\n  void a() {}\n}\n"))
            self.assertEqual(grew["cognitive_complexity"], 0)      # the `if` came with the branch
            self.assertEqual(grew["commits"], 1)                   # only the base commit is behind it
            # A file the diff ADDED has no before — the whole block on screen is all it
            # has ever been, so there is nothing to sketch behind it.
            self.assertNotIn("src/main/java/app/Added.java", before)
            # ...and an untouched file is not in the change set at all.
            self.assertNotIn("src/main/java/app/Same.java", before)
            # Whole-repo metrics cannot be reconstructed from a blob and are left out on purpose.
            self.assertNotIn("fan_in", grew)
            self.assertNotIn("instability", grew)
            # The city marks them: in highlight mode a grown building carries a row of
            # black arrowheads at its old height, facing UP the wall, and another row on
            # the roof at its old footprint, facing OUT — the mark points the way the
            # building moved, in both places, instead of only saying where it stopped.
            self.assertIn("function addChangeMarks", html)
            self.assertIn("function addHeightMark", html)
            self.assertIn("function addAreaMark", html)
            self.assertIn('if (changeMode() !== "highlight") return;', html)
            self.assertIn("const MARK_COLOR = 0x000000;", html)
            # Painted ON the walls and the roof, in world units — not a screen-width
            # outline hung around the block, which reads as glass in front of the city.
            self.assertNotIn("LineSegments2", html)
            self.assertNotIn("function markRectangle", html)
            self.assertIn("plane.rotateX(-Math.PI / 2);", html)     # the roof marks lie flat
            self.assertIn("polygonOffsetFactor: -4", html)
            # Only growth is marked — a file that got smaller carries no mark at all.
            self.assertIn("geo.height - wasHeight > MARK_MIN_DELTA", html)
            self.assertIn("geo.width - wasW > MARK_MIN_DELTA || geo.depth - wasD > MARK_MIN_DELTA", html)
            # The intro explains the marks the way it explains area/height/colour: a
            # fourth card, wired to a REAL mark, naming the axis that mark measures.
            self.assertIn("function clearestChangeMark", html)
            self.assertIn('title: "CHANGED"', html)
            self.assertIn('"dashed = its old footprint" : "dashed = its old height"', html)
            # ...and it only appears when a mark is actually on screen at startup.
            self.assertIn("if (changeMark && changeSelect) {", html)

    def test_opens_on_the_diff_and_hides_the_row_without_one(self):
        """A city built from a checkout that HAS a change set is nearly always being read
        to answer "what did this change?", so the page opens in "highlight changed". With
        no change set the whole Changes row goes away — three modes that would all render
        the same city are a choice not worth offering."""
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HEATMAP_OUT"] = tmp
            subprocess.run(
                ["python3", str(SCRIPT_DIR / "render_codecity.py"), str(SAMPLE_TSV)],
                check=True, cwd=SCRIPT_DIR, env=env,
            )
            html = (Path(tmp) / "codecity.html").read_text()
            self.assertIn('<option value="highlight" selected>highlight changed</option>', html)
            self.assertIn('<option value="off">show everything</option>', html)
            self.assertIn('<span class="knob" id="changesKnob">Changes</span>', html)
            self.assertIn("if (!HAS_CHANGES) {", html)
            self.assertIn('el.style.display = "none"', html)
            # ...and the mode is wound back to "off" so a hidden selector cannot filter.
            self.assertIn('if (changeSelect) changeSelect.value = "off";', html)
            # ...measured with the building's own ruler, not a second copy of the maths.
            self.assertIn("function heightFor(", html)
            self.assertIn("function footprintFor(", html)
            self.assertIn("const [width, depth] = footprintFor(leaf.value", html)
            # ...and the numbers behind the sketch are readable in the hover.
            self.assertIn("function wasNote", html)


if __name__ == "__main__":
    unittest.main()
