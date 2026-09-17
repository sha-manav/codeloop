import pytest

from codeloop.scoring import aggregate, canonicalize, score_encounter
from codeloop.scoring.scorer import pair_lines
from tests.scoring_fixtures import TEST_SCOPE, dx, line, pkg


def score(gold, pred, eid="E1"):
    return score_encounter(eid, canonicalize(gold, TEST_SCOPE), canonicalize(pred, TEST_SCOPE))


def refs(result, correct=None):
    return [f.ref for f in result.fields if correct is None or f.correct is correct]


def test_perfect_agreement():
    g = pkg([dx("M1711", True), dx("R509")], [line("96372", ["RT"], 1, ["A"])])
    r = score(g, g)
    assert r.n_fields == 7 and r.n_correct == 7 and r.agreement == 1.0
    assert r.tiers == {"t75": True, "t90": True, "t100": True} and not r.no_in_scope_fields
    assert refs(r) == ["dx:M1711", "dx:R509", "first_listed", "line:96372", "line:96372:modifiers", "line:96372:units", "line:96372:pointers"]


def test_extra_and_missing_diagnoses():
    g = pkg([dx("M1711", True), dx("R509")])
    p = pkg([dx("M1711", True), dx("E119")])
    r = score(g, p)
    assert refs(r, True) == ["dx:M1711", "first_listed"] and refs(r, False) == ["dx:E119", "dx:R509"]
    assert r.agreement == pytest.approx(2 / 4)
    assert r.per_type["dx"].model_dump() == {"tp": 1, "fp": 1, "fn": 1, "n": 0, "correct": 0}


def test_first_listed_none_equals_none_and_mismatch():
    assert score(pkg([dx("M1711")]), pkg([dx("M1711")])).agreement == 1.0
    r = score(pkg([dx("M1711", True), dx("R509")]), pkg([dx("M1711"), dx("R509", True)]))
    assert refs(r, False) == ["first_listed"] and r.agreement == pytest.approx(2 / 3)


def test_partial_line_match():
    g = pkg([dx("M1711", True)], [line("96372", ["RT"], 1, ["A"])])
    p = pkg([dx("M1711", True)], [line("96372", ["RT"], 2, ["A"])])
    r = score(g, p)
    assert refs(r, False) == ["line:96372:units"]
    assert r.agreement == pytest.approx(5 / 6) and r.tiers == {"t75": True, "t90": False, "t100": False}
    assert r.per_type["units"].model_dump()["correct"] == 0 and r.per_type["modifiers"].correct == 1


def test_unmatched_lines_each_cost_one_field():
    g = pkg([dx("M1711", True)], [line("96372", pointers=["A"])])
    p = pkg([dx("M1711", True)], [line("20610", pointers=["A"])])
    r = score(g, p)
    assert refs(r, False) == ["line:20610", "line:96372"] and r.agreement == pytest.approx(2 / 4)
    assert r.per_type["line"].fp == 1 and r.per_type["line"].fn == 1


def test_merged_duplicates_score_as_one_line():
    g = pkg([dx("E119", True)], [line("J1100", ["JW"], 15, ["A"])])
    p = pkg([dx("E119", True)], [line("J1100", ["JW"], 10, ["A"]), line("J1100", ["JW"], 5, ["A"])])
    assert score(g, p).agreement == 1.0


def test_multi_line_same_code_greedy_pairing_and_indexed_refs():
    g = pkg([dx("M1711", True), dx("M1712")], [line("20610", ["RT"], 1, ["A"]), line("20610", ["LT"], 1, ["B"])])
    p = pkg([dx("M1711", True), dx("M1712")], [line("20610", ["LT"], 1, ["B"]), line("20610", ["RT"], 2, ["A"])])
    r = score(g, p)
    assert [f.ref for f in r.fields if f.type == "line"] == ["line:20610:0", "line:20610:1"]
    assert refs(r, False) == ["line:20610:1:units"]
    pairs, ug, up = pair_lines(canonicalize(g, TEST_SCOPE).lines, canonicalize(p, TEST_SCOPE).lines)
    assert len(pairs) == 2 and not ug and not up
    assert all(gl.modifiers == pl.modifiers for gl, pl in pairs)


def test_empty_encounters():
    r = score(pkg(), pkg())
    assert r.agreement == 1.0 and r.hier_agreement == 1.0 and r.no_in_scope_fields and r.n_fields == 0
    r = score(pkg([dx("M1711")]), pkg())
    # first_listed is None on both sides and counts as correct (spec §5.2 item 2)
    assert r.agreement == 0.5 and r.fields[0].ref == "dx:M1711" and refs(r) == ["dx:M1711", "first_listed"]
    r = score(pkg([dx("M1711", True)]), pkg())
    assert r.agreement == 0.0 and refs(r, False) == ["dx:M1711", "first_listed"]
    r = score(pkg(), pkg([dx("M1711", True)]))
    assert r.agreement == 0.0 and r.per_type["dx"].fp == 1


def test_scope_stripping_makes_em_and_off_modifiers_invisible():
    g = pkg([dx("M1711", True)], [line("99213", ["25"], 1, ["A"]), line("96372", ["59"], 1, ["A"])])
    p = pkg([dx("M1711", True)], [line("96372", [], 1, ["A"])])
    assert score(g, p).agreement == 1.0


def test_pointer_letter_resolution_scores_equal_to_codes():
    g = pkg([dx("M1711", True), dx("R509")], [line("96372", pointers=["A", "B"])])
    p = pkg([dx("R50.9"), dx("M17.11", True)], [line("96372", pointers=["M17.11", "R50.9"])])
    assert score(g, p).agreement == 1.0


def test_hierarchical_credit_for_same_category():
    r = score(pkg([dx("M1711")]), pkg([dx("M1712")]))
    assert r.agreement == pytest.approx(1 / 3)  # first_listed None == None
    assert r.hier_agreement == pytest.approx(2 / 3)
    credited = {f.ref: f.credit for f in r.fields}
    assert credited == {"dx:M1711": 0.5, "dx:M1712": 0.5, "first_listed": 1.0}
    # one-to-one: two pred codes in the category share credit with only one gold code
    r = score(pkg([dx("M1711")]), pkg([dx("M1712"), dx("M1710")]))
    assert sum(f.credit for f in r.fields if f.type == "dx") == 1.0
    # no credit across categories
    r = score(pkg([dx("M1711")]), pkg([dx("M1811")]))
    assert r.hier_agreement == r.agreement


def test_aggregate_tiers_and_per_type():
    g1 = pkg([dx("M1711", True)], [line("96372", pointers=["A"])])
    results = [score(g1, g1, "A"), score(g1, pkg([dx("M1711", True)]), "B"), score(pkg(), pkg(), "C")]
    b = aggregate(results)
    assert b.n == 3 and b.no_in_scope_fields == 1
    assert b.tiers["t100"].count == 2 and b.tiers["t75"].count == 2
    assert 0 < b.tiers["t100"].wilson_low < b.tiers["t100"].share < b.tiers["t100"].wilson_high <= 1
    assert b.per_type["line"] == {"tp": 1, "fp": 0, "fn": 1, "precision": 1.0, "recall": 0.5}
    assert b.per_type["dx"]["recall"] == 1.0 and b.per_type["first_listed"]["accuracy"] == 1.0
    assert b.mean_agreement == pytest.approx((1.0 + 2 / 3 + 1.0) / 3)
