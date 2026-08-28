#!/usr/bin/env python3
"""Profile a generated Code City page in headless Chromium.

  profile_city.py /path/to/codecity.html [label]

Reports: page errors, load time, idle FPS, FPS while orbiting, and a CPU profile
(self time per function) of the two hover overlays — Alt (coupling roads) and
Shift (co-change partners) — which are the two things that can stall a big city.
"""
import json
import sys
import time
from collections import defaultdict

from playwright.sync_api import sync_playwright

PAGE = sys.argv[1]
LABEL = sys.argv[2] if len(sys.argv) > 2 else PAGE


def fps_probe(page, seconds=2.0):
    return page.evaluate(
        """(ms) => new Promise(res => {
            let n = 0; const t0 = performance.now();
            let worst = 0, last = t0;
            (function tick() {
                const now = performance.now();
                worst = Math.max(worst, now - last); last = now; n++;
                if (now - t0 < ms) requestAnimationFrame(tick);
                else res({fps: n / ((now - t0) / 1000), worstFrameMs: worst});
            })();
        })""",
        seconds * 1000,
    )


def self_time(profile):
    """Self time in ms per function, from a CDP CPU profile."""
    by_id = {n["id"]: n for n in profile["nodes"]}
    total_us = sum(profile["timeDeltas"]) or 1
    hits = sum(n.get("hitCount", 0) for n in profile["nodes"]) or 1
    per_hit_ms = (total_us / 1000.0) / hits
    out = defaultdict(float)
    for node in profile["nodes"]:
        frame = node["callFrame"]
        name = frame.get("functionName") or "(anonymous)"
        out[name] += node.get("hitCount", 0) * per_hit_ms
    return out, total_us / 1000.0


with sync_playwright() as p:
    browser = p.chromium.launch(args=[
        "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--no-sandbox",
    ])
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    problems = []
    page.on("pageerror", lambda e: problems.append(("pageerror", str(e))))
    page.on("console", lambda m: problems.append((m.type, m.text))
            if m.type in ("error",) else None)

    # Count the actual GL work: three.js issues one draw per object per pass, so this is
    # the number that decides whether a big city turns or crawls — and it is the only way
    # to see the shadow pass, which is a whole second render of everything.
    page.add_init_script("""
      (() => {
        const gl = { draws: 0, frames: 0 };
        window.__glCount = gl;
        for (const ctor of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
          if (!ctor) continue;
          for (const name of ["drawElements", "drawArrays", "drawElementsInstanced"]) {
            const original = ctor.prototype[name];
            if (!original) continue;
            ctor.prototype[name] = function (...args) { gl.draws++; return original.apply(this, args); };
          }
        }
        const raf = window.requestAnimationFrame.bind(window);
        window.requestAnimationFrame = (cb) => raf((t) => { gl.frames++; return cb(t); });
      })();
    """)

    t0 = time.time()
    page.goto("file://" + PAGE, wait_until="load")
    page.wait_for_timeout(500)
    # The city is built in-page after the module loads; give it room, then confirm.
    page.wait_for_function("() => document.querySelectorAll('canvas').length > 0", timeout=30000)
    page.wait_for_timeout(2500)
    load_ms = (time.time() - t0) * 1000

    print(f"\n=== {LABEL}")
    print(f"page              {len(open(PAGE, 'rb').read()) / 1024:.0f} KB")
    print(f"load -> first frame {load_ms:.0f} ms")
    if problems:
        print("PAGE ERRORS:")
        for kind, text in problems[:10]:
            print(f"  [{kind}] {text[:200]}")
    else:
        print("page errors       none")

    # The first-run intro returns out of every hover; a profile taken under it profiles
    # nothing. (This is how the first round of these numbers came out reassuring.)
    got_it = page.locator("button.intro-dismiss")
    if got_it.count():
        got_it.click()
        page.wait_for_timeout(400)
    print("intro              dismissed")

    idle = fps_probe(page)
    print(f"idle              {idle['fps']:.1f} fps (worst frame {idle['worstFrameMs']:.0f} ms)")
    draws = page.evaluate(
        """() => new Promise(res => {
            const g = window.__glCount, d0 = g.draws, f0 = g.frames;
            setTimeout(() => res({draws: g.draws - d0, frames: g.frames - f0}), 1500);
        })""")
    per_frame = draws["draws"] / max(1, draws["frames"])
    print(f"draw calls        {per_frame:.0f} per frame ({draws['frames']} frames sampled)")

    cdp = page.context.new_cdp_session(page)
    cdp.send("Profiler.enable")
    cdp.send("Profiler.setSamplingInterval", {"interval": 200})

    box = page.locator("canvas").first.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    spots = [(cx + dx, cy + dy) for dx, dy in
             ((0, 0), (-160, -60), (140, 40), (-60, 90), (200, -100), (80, 120))]

    def sweep(label, modifier=None, settle=260):
        if modifier:
            page.keyboard.down(modifier)
        cdp.send("Profiler.start")
        t = time.time()
        for x, y in spots:
            page.mouse.move(x, y)
            page.wait_for_timeout(settle)
        wall = (time.time() - t) * 1000
        prof = cdp.send("Profiler.stop")["profile"]
        if modifier:
            page.keyboard.up(modifier)
        times, total = self_time(prof)
        interesting = sorted(
            ((v, k) for k, v in times.items()
             if k not in ("(idle)", "(program)", "(garbage collector)", "(root)")),
            reverse=True)[:8]
        idle_ms = times.get("(idle)", 0)
        print(f"\n  {label}: {len(spots)} hovers over {wall:.0f} ms wall, "
              f"{total - idle_ms:.0f} ms on CPU ({100 * (total - idle_ms) / total:.0f}% busy)")
        for v, k in interesting:
            if v >= 1:
                print(f"    {v:8.1f} ms  {k}")

    def hovering_a_building():
        for x, y in spots:
            page.mouse.move(x, y)
            page.wait_for_timeout(200)
            if page.locator("#hover").is_visible():
                return x, y
        return None

    sweep("plain hover")
    sweep("ALT hover (coupling roads)", "Alt")

    # Prove the overlay actually engaged rather than quietly hovering empty sky: with a
    # bundle up, the tooltip's coupling lines report how many roads are on screen.
    page.keyboard.down("Alt")
    at = hovering_a_building()
    tip = page.locator("#hover").inner_html() if at else ""
    page.keyboard.up("Alt")
    roads = "road" in tip
    print(f"  roads engaged   {'yes' if roads else 'NO — nothing drawn'}"
          + (f" ({[l for l in tip.split('<li') if 'road' in l][:1]!r})" if False else ""))

    if page.locator('#colorMetric option[value="cochange_out"]').count():
        page.select_option("#colorMetric", "cochange_out")
        page.wait_for_timeout(700)
        sweep("SHIFT hover (co-change partners)", "Shift")
        # ...and prove that one engaged too: the plate visibly drains when it does.
        at = hovering_a_building()
        if at:
            before = page.screenshot()
            page.keyboard.down("Shift")
            page.mouse.move(at[0] + 1, at[1])
            page.wait_for_timeout(400)
            after = page.screenshot()
            page.keyboard.up("Shift")
            changed = sum(1 for a, b in zip(before, after) if a != b) / max(1, len(before))
            print(f"  co-change engaged {'yes' if changed > 0.05 else 'NO — city unchanged'}"
                  f" ({changed:.0%} of the frame repainted)")
    else:
        print("\n  co-change: no data in this page")

    # Orbiting is the frame-rate case that matters: the city has to keep turning.
    page.mouse.move(cx, cy)
    page.mouse.down()
    orbit = page.evaluate(
        """() => new Promise(res => {
            let n = 0, worst = 0; const t0 = performance.now(); let last = t0;
            (function tick() {
                const now = performance.now();
                worst = Math.max(worst, now - last); last = now; n++;
                window.dispatchEvent(new PointerEvent("pointermove", {
                    clientX: 800 + 200 * Math.sin(n / 6), clientY: 500 + 120 * Math.cos(n / 7),
                    bubbles: true,
                }));
                if (now - t0 < 2500) requestAnimationFrame(tick);
                else res({fps: n / ((now - t0) / 1000), worstFrameMs: worst});
            })();
        })"""
    )
    page.mouse.up()
    print(f"\n  while panning   {orbit['fps']:.1f} fps (worst frame {orbit['worstFrameMs']:.0f} ms)")

    browser.close()
