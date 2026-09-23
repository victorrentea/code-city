"""Axes of change: which classes the history keeps changing TOGETHER, as groups.

The "Change DNA" colour reads these. A package is cohesive when the commits that touch it
land on one axis; a layered package — controller/, service/, repository/ — is crossed by
every feature, so it carries every axis in the repo, and the same colours come back in
each of its siblings. The co-change metric already says how often a class leaves its
package; this says what the package would be made of if the history had drawn it.

Groups, not pairs, because the question is about the whole plate at once: "which of my
packages is really four features stacked in a layer" is a question about sets, and a
pair list has to be clustered in the reader's head to answer it.

Pure functions, no I/O: build_heatmap.py feeds the commits it already walks and writes the
result; the tests drive them with toy histories.
"""
import math
import re
from collections import defaultdict

# Below this many classes a community is noise — two files renamed together, a class and
# its builder — and a colour spent on it is a colour the real axes do not get.
MIN_AXIS_FILES = 3


def cochange_graph(commits, live, min_shared=2):
    """Weighted co-change graph over the `live` paths.

    Each commit adds 1/(n-1) to every pair of the n live files it touched, so a file's
    total weight from one commit is 1 whatever the commit's size: a 25-file commit says
    much less about any one pair in it than a 2-file commit does. Pairs seen together in
    fewer than `min_shared` commits are dropped — once is a coincidence.

    Returns ({node: {neighbour: weight}}, [paths]) keyed by integer ids, to keep the pair
    table affordable on a history the size of Spring's.
    """
    ids, paths = {}, []
    weight = defaultdict(float)
    count = defaultdict(int)
    for touched in commits:
        nodes = set()
        for p in touched:
            if p not in live:
                continue
            if p not in ids:
                ids[p] = len(paths)
                paths.append(p)
            nodes.add(ids[p])
        nodes = sorted(nodes)
        n = len(nodes)
        if n < 2:
            continue
        share = 1.0 / (n - 1)
        for i, u in enumerate(nodes):
            for v in nodes[i + 1:]:
                key = (u, v)
                weight[key] += share
                count[key] += 1
    adj = defaultdict(dict)
    for (u, v), w in weight.items():
        if count[(u, v)] < min_shared:
            continue
        adj[u][v] = w
        adj[v][u] = w
    return adj, paths


def _one_level(adj, order):
    """Louvain's local-moving phase: move each node to the neighbouring community that
    raises modularity most, until a whole pass moves nobody. Returns node -> community."""
    degree = {u: sum(nbrs.values()) for u, nbrs in adj.items()}
    m2 = sum(degree.values())
    comm = {u: u for u in order}
    tot = dict(degree)
    if m2 == 0:
        return comm
    for _ in range(50):          # converges in a handful; the cap is for pathological input
        moved = False
        for u in order:
            ku = degree[u]
            here = comm[u]
            links = defaultdict(float)
            for v, w in adj[u].items():
                if v != u:
                    links[comm[v]] += w
            tot[here] -= ku
            best, best_gain = here, links.get(here, 0.0) - tot[here] * ku / m2
            for c in sorted(links):
                gain = links[c] - tot[c] * ku / m2
                if gain > best_gain + 1e-12:
                    best, best_gain = c, gain
            tot[best] += ku
            if best != here:
                comm[u] = best
                moved = True
        if not moved:
            break
    return comm


def louvain(adj):
    """Communities of a weighted undirected graph (Blondel et al. 2008), deterministic.

    Hand-rolled rather than imported because this repo's pipeline installs nothing but
    tree-sitter, and a city has to build on any checkout with no pip step in between.
    Returns {node: community index}.
    """
    member = {u: u for u in adj}        # original node -> current super-node
    graph = {u: dict(nbrs) for u, nbrs in adj.items()}
    while True:
        comm = _one_level(graph, sorted(graph))
        if len(set(comm.values())) == len(graph):
            break                       # nobody merged: this is the final partition
        member = {u: comm[s] for u, s in member.items()}
        folded = defaultdict(lambda: defaultdict(float))
        for u, nbrs in graph.items():
            for v, w in nbrs.items():
                folded[comm[u]][comm[v]] += w
        graph = {u: dict(nbrs) for u, nbrs in folded.items()}
    return member


_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# Words every Java codebase is made of. An axis named "Impl" or "Service" names a layer —
# the exact thing this view exists to see past.
_STOP = {
    "abstract", "impl", "default", "simple", "base", "util", "utils", "support", "config",
    "configuration", "service", "services", "controller", "repository", "dao", "dto",
    "factory", "handler", "exception", "test", "tests", "helper", "manager", "provider",
    "resolver", "adapter", "bean", "mapper", "entity", "model", "request", "response",
    "resource", "rest", "api", "web", "jpa", "jdbc", "spring", "java", "type", "types",
    "i", "to", "of", "a", "an", "and", "or", "for", "by", "in", "on", "with",
}


def _words(path):
    name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return {w.lower() for w in _CAMEL.findall(name)} - _STOP


def name_axis(members, word_df, total):
    """The word that most sets this group of classes apart: frequent inside it, rare
    outside it (tf-idf over class names). Falls back to the most common package leaf,
    which is the answer when a group shares a package and nothing in its names."""
    tf = defaultdict(int)
    for p in members:
        for w in _words(p):
            tf[w] += 1
    best, best_score = None, 0.0
    for w, n in tf.items():
        if n < 2 and len(members) > 2:
            continue
        score = (n / len(members)) * math.log(total / word_df[w])
        if score > best_score or (score == best_score and best is not None and w < best):
            best, best_score = w, score
    if best:
        return best[:1].upper() + best[1:]
    leaves = defaultdict(int)
    for p in members:
        parts = p.split("/")
        leaves[parts[-2] if len(parts) > 1 else "root"] += 1
    return max(sorted(leaves), key=lambda k: leaves[k])


def change_axes(commits, live, min_shared=2):
    """Cluster the live classes into axes of change.

    Returns (axis_of, axes): axis_of maps a path to its axis index, axes is a list of
    (name, file count) sorted biggest first — index 0 is the axis most of the repo's
    history ran along. Classes that never co-changed, or landed in a group smaller than
    MIN_AXIS_FILES, are in no axis at all: "changes alone" is an answer too, and colouring
    it would claim a pattern where the history shows none.
    """
    adj, paths = cochange_graph(commits, live, min_shared)
    groups = defaultdict(list)
    for node, c in louvain(adj).items():
        groups[c].append(paths[node])
    kept = [sorted(m) for m in groups.values() if len(m) >= MIN_AXIS_FILES]
    kept.sort(key=lambda m: (-len(m), m[0]))
    word_df = defaultdict(int)
    for p in live:
        for w in _words(p):
            word_df[w] += 1
    total = max(1, len(live))
    axis_of, axes = {}, []
    for i, members in enumerate(kept):
        axes.append((name_axis(members, word_df, total), len(members)))
        for p in members:
            axis_of[p] = i
    return axis_of, axes
