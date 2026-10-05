"""Coverage handed over as JSON: the spellings it accepts, and the one distinction it keeps.

Run with:  python3 -m pytest test_coverage_input.py
"""
import json

import coverage_input as ci


def test_counts_are_kept_as_counts_so_roll_ups_can_re_divide_them():
    got, dropped = ci.parse({"files": {
        "src/A.java": {"line": {"covered": 3, "total": 4}, "acceptance": {"covered": 1, "total": 4}},
        "src/B.java": {"line": [0, 10]},
    }}, "/repo")
    assert dropped == 0
    assert got["src/A.java"] == {"cov_covered": 3, "cov_total": 4, "acc_covered": 1, "acc_total": 4}
    assert got["src/B.java"]["cov_covered"] == 0 and got["src/B.java"]["cov_total"] == 10


def test_a_bare_percentage_weighs_as_a_hundred_lines():
    got, _ = ci.parse({"src/A.java": {"line": 87.5}}, "/repo")      # no `files` wrapper
    assert (got["src/A.java"]["cov_covered"], got["src/A.java"]["cov_total"]) == (87.5, 100.0)


def test_zero_covered_is_measured_and_nothing_executable_is_not():
    """0 of 10 is a finding (red); 0 of 0 is a class with nothing to run (grey)."""
    got, dropped = ci.parse({"files": {
        "src/Untested.java": {"line": {"covered": 0, "total": 10}},
        "src/Marker.java": {"line": {"covered": 0, "total": 0}},
        "src/Null.java": {"line": None},
    }}, "/repo")
    assert got["src/Untested.java"]["cov_total"] == 10
    assert "src/Marker.java" not in got and "src/Null.java" not in got
    assert dropped == 2


def test_acceptance_not_measured_travels_as_zero_of_zero():
    got, _ = ci.parse({"files": {"src/A.java": {"line": {"covered": 2, "total": 4}}}}, "/repo")
    assert (got["src/A.java"]["acc_covered"], got["src/A.java"]["acc_total"]) == (0, 0)


def test_paths_are_normalised_to_the_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    got, dropped = ci.parse({"files": {
        str(repo / "src/Abs.java"): {"line": [1, 2]},
        "./src/Dot.java": {"line": [1, 2]},
        "src\\Win.java": {"line": [1, 2]},
        "/elsewhere/Out.java": {"line": [1, 2]},
        "//": "a comment key",
    }}, str(repo))
    assert set(got) == {"src/Abs.java", "src/Dot.java", "src/Win.java"}
    assert dropped == 1


def test_load_says_so_and_returns_nothing_for_an_unreadable_file(tmp_path, capsys):
    bad = tmp_path / "c.json"
    bad.write_text("{not json")
    assert ci.load(str(bad), str(tmp_path)) == {}
    assert "unreadable" in capsys.readouterr().err
    good = tmp_path / "g.json"
    good.write_text(json.dumps({"files": {"A.java": {"line": [1, 2]}}}))
    assert ci.load(str(good), str(tmp_path))["A.java"]["cov_total"] == 2


def test_merge_keeps_a_crap_score_and_gives_none_where_there_is_none():
    crap = {"A.java": {"cov_covered": 1, "cov_total": 9, "crap_max": 20.0,
                       "crap_max_method": "tangle", "crap_load": 20.0, "crappy_methods": 0,
                       "acc_covered": 0, "acc_total": 0}}
    n = ci.merge(crap, {"A.java": {"cov_covered": 9, "cov_total": 9, "acc_covered": 0, "acc_total": 0},
                        "B.java": {"cov_covered": 2, "cov_total": 4, "acc_covered": 1, "acc_total": 4}})
    assert n == 2
    assert crap["A.java"]["cov_covered"] == 9 and crap["A.java"]["crap_max"] == 20.0
    assert crap["B.java"]["crap_max"] is None and crap["B.java"]["acc_covered"] == 1
