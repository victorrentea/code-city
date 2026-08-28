#!/usr/bin/env python3
"""How long ONE hover costs, in the handler itself.

onPointerMove is a synchronous window listener, so dispatching the event from inside the
page and timing around it measures exactly what the browser's main thread is asked to do
when the mouse crosses one building — which is the thing that freezes or does not.
"""
import statistics
import sys

from playwright.sync_api import sync_playwright

PAGE, LABEL = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")

PROBE = """(alt) => new Promise(res => {
  const canvas = document.querySelector("canvas");
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const samples = [], hits = [];
  // A raster over the plate: most points hit a building, and every new building is a
  // fresh route bundle — which is exactly what dragging the mouse across the city does.
  const points = [];
  for (let i = 1; i < 9; i++) for (let j = 1; j < 7; j++) {
    points.push([w * i / 9, h * j / 7]);
  }
  let k = 0;
  (function step() {
    if (k >= points.length) return res({samples, hits: hits.length});
    const [x, y] = points[k++];
    const t0 = performance.now();
    window.dispatchEvent(new PointerEvent("pointermove", {
      clientX: x, clientY: y, altKey: alt, bubbles: true,
    }));
    samples.push(performance.now() - t0);
    if (document.getElementById("hover").classList.contains("visible")) hits.push(1);
    requestAnimationFrame(step);   // one frame between, like a real mouse
  })();
})"""

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("file://" + PAGE, wait_until="load")
    page.wait_for_function("() => document.querySelectorAll('canvas').length > 0", timeout=30000)
    page.wait_for_timeout(3000)
    # The first-run intro swallows every hover ("no tooltips while it is up"), so a probe
    # that does not dismiss it measures an early return and calls it fast.
    got_it = page.locator("button.intro-dismiss")
    if got_it.count():
        got_it.click()
        page.wait_for_timeout(400)
    print("intro dismissed:", got_it.count() == 0 or not got_it.first.is_visible())

    print(f"\n=== {LABEL or PAGE}")
    for label, alt in (("plain hover", False), ("ALT hover (roads)", True)):
        page.evaluate(PROBE, False)          # warm up / settle
        result = page.evaluate(PROBE, alt)
        samples, hits = result["samples"], result["hits"]
        samples.sort()
        n = len(samples)
        print(f"  {label:20s} n={n} ({hits} on a building)  median {statistics.median(samples):7.1f} ms   "
              f"p90 {samples[int(n * 0.9)]:7.1f} ms   worst {samples[-1]:7.1f} ms   "
              f"total {sum(samples):7.0f} ms")
    if errors:
        print("  page errors:", errors[:3])
    browser.close()
