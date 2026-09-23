"""The axes of change: clustering a toy history the way a layered repo is actually shaped.

Four features, each touching its own controller, service and repository in every commit,
under a package-by-layer tree. The clustering must find the features (the axes) and not
the layers (the packages) — that difference is the whole point of the Change DNA colour.
"""
from change_axes import MIN_AXIS_FILES, change_axes, cochange_graph, louvain

FEATURES = ["Owner", "Pet", "Visit", "Vet"]
LAYERS = ["controller", "service", "repository"]


def path(feature, layer):
    return f"app/src/main/java/app/{layer}/{feature}{layer.capitalize()}.java"


def layered_history(commits_per_feature=5):
    return [[path(f, layer) for layer in LAYERS]
            for f in FEATURES for _ in range(commits_per_feature)]


LIVE = {path(f, layer) for f in FEATURES for layer in LAYERS}


def test_each_feature_is_one_axis_across_all_layers():
    axis_of, axes = change_axes(layered_history(), LIVE)
    assert len(axes) == len(FEATURES)
    for f in FEATURES:
        assert len({axis_of[path(f, layer)] for layer in LAYERS}) == 1, f
    assert len({axis_of[path(f, "service")] for f in FEATURES}) == len(FEATURES)


def test_an_axis_is_named_after_its_feature_not_its_layer():
    axis_of, axes = change_axes(layered_history(), LIVE)
    names = {axes[axis_of[path(f, "service")]][0] for f in FEATURES}
    assert names == set(FEATURES)


def test_a_pair_seen_once_is_a_coincidence():
    adj, _paths = cochange_graph([["a.java", "b.java"]], {"a.java", "b.java"}, min_shared=2)
    assert not adj


def test_a_big_commit_weighs_less_per_pair_than_a_small_one():
    live = {f"{c}.java" for c in "abcdef"}
    adj, paths = cochange_graph([["a.java", "b.java"]] * 2 + [sorted(live)] * 2, live)
    ids = {p: i for i, p in enumerate(paths)}
    assert adj[ids["a.java"]][ids["b.java"]] > adj[ids["c.java"]][ids["d.java"]]


def test_classes_that_only_change_alone_are_in_no_axis():
    live = LIVE | {"app/src/main/java/app/util/Loner.java"}
    history = layered_history() + [["app/src/main/java/app/util/Loner.java"]] * 5
    axis_of, _axes = change_axes(history, live)
    assert "app/src/main/java/app/util/Loner.java" not in axis_of


def test_a_group_below_the_minimum_is_not_an_axis():
    pair = ["x/A.java", "x/B.java"]
    assert len(pair) < MIN_AXIS_FILES
    axis_of, axes = change_axes([pair] * 5, set(pair))
    assert not axes and not axis_of


def test_louvain_splits_two_cliques_joined_by_one_weak_edge():
    adj = {}
    def link(u, v, w):
        adj.setdefault(u, {})[v] = w
        adj.setdefault(v, {})[u] = w
    for group in ((0, 1, 2, 3), (4, 5, 6, 7)):
        for i in group:
            for j in group:
                if i < j:
                    link(i, j, 1.0)
    link(3, 4, 0.1)
    comm = louvain(adj)
    assert len({comm[i] for i in range(4)}) == 1
    assert len({comm[i] for i in range(4, 8)}) == 1
    assert comm[0] != comm[4]
