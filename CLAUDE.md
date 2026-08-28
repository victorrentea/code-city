# Working on Code City

## Every change is tried on a BIG repo, not just a small one

A city of 90 classes hides almost everything that goes wrong in a city of 5000. Layout,
label density, page weight, and above all the per-hover cost behave nothing alike at the
two sizes — and the small one always looks fine.

So: **generate both, every time**, before calling anything done.

```bash
export CODECITY_BIG_REPO=~/path/to/spring-framework    # any large Java checkout
./generate.sh "$CODECITY_BIG_REPO" /tmp/cc-big
./generate.sh ~/path/to/petclinic   /tmp/cc-small
```

Spring Framework is the reference big case: 5003 classes, 565 packages, 23 modules, 31509
commits. Generation takes ~30 s and ~400 MB of RSS; if a change makes either much worse,
that is the finding.

## Then measure it, do not eyeball it

```bash
./profile_city.py /tmp/cc-big/codecity.html "spring"   # errors, first frame, draw calls, CPU profile
./hover_cost.py   /tmp/cc-big/codecity.html "spring"   # what ONE hover costs, inside the handler
```

**Dismiss the first-run intro before measuring anything.** While the intro overlay is up,
`onPointerMove` returns early — no picking, no tooltip, no overlay, no work. A probe that
skips it measures an early return and reports every overlay as free. Both scripts here
click "Got it" first; anything new you write must too. This mistake once shipped a hover
that locked the tab for 22 seconds under a set of numbers saying it was instant.

Budgets that have to hold on the big city:

| | budget |
| --- | --- |
| one hover, worst | < 50 ms — anything more and a held key freezes the tab |
| page | a few MB; inline JSON is downloaded *and* parsed before the first frame |
| draw calls / frame | it is already ~10k; do not add per-object meshes |

Whatever you add to a hover runs on the main thread between two frames. Per-hover work
that scales with the size of the city (a sweep over the plate, a pass over every building)
needs a cap, an early exit, or both — and the cap belongs in the code, not in the
reviewer's hope that nobody hovers a god class.

## Overlays: hold a key, do not tick a box

Both overlays are questions asked of one building for a second — what does this sit on,
what changes with this — not layers to leave switched on. A checkbox someone forgot they
ticked is a city that cannot be read any more, and on a big plate it is also a city that
does not turn. Held keys: ⌥ for the coupling roads, ⇧ for the co-change partners (the
latter only while COLOR is on `cross-package co-change`, since it *is* that metric asked
of one building).

Neither key announces itself with a pointer event, so both are tracked and the last hover
is replayed on keydown and keyup. A live pointermove re-syncs them, which heals a keyup
that never arrived.

## Voice

Comments explain **why**, in full sentences, including what was tried and rejected and
what it measured. The README argues for the design rather than listing features. Match
what is already there before writing a line of it.

## Do not

- Do not put personal paths, client names or credentials in this repo — it is public.
- Do not add a `version` field to any plugin/marketplace manifest here.
- Do not commit generated cities; `generate.sh` writes them outside the repo.
