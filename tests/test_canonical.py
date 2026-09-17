from codeloop.scoring import Canonical, CanonicalLine, canonicalize, to_package_like
from codeloop.scoring.scope import Scope, code_in_ranges, parse_range
from tests.scoring_fixtures import TEST_SCOPE, dx, line, pkg


def test_codes_normalized_and_pointer_letters_resolved():
    c = canonicalize(pkg([dx("m17.11", True), dx("R50.9")], [line("96372", ["lt", "RT"], 1, ["A", "B"])]), TEST_SCOPE)
    assert c.diagnoses == frozenset({"M1711", "R509"}) and c.first_listed == "M1711"
    assert c.lines == [CanonicalLine(code="96372", modifiers=("LT", "RT"), units=1, pointers=frozenset({"M1711", "R509"}))]


def test_pointer_codes_numeric_and_unknown_letters():
    c = canonicalize(pkg([dx("M1711")], [line("96372", pointers=["M17.11", "1", "Z"])]), TEST_SCOPE)
    assert c.lines[0].pointers == frozenset({"M1711", "Z"})


def test_duplicate_lines_merge_units_and_union_pointers():
    c = canonicalize(pkg([dx("M1711"), dx("R509")], [line("J1100", ["JW"], 10, ["A"]), line("J1100", ["JW"], 5, ["B"]), line("J1100", [], 1)]), TEST_SCOPE)
    assert [(ln.code, ln.modifiers, ln.units, ln.pointers) for ln in c.lines] == [
        ("J1100", (), 1, frozenset()),
        ("J1100", ("JW",), 15, frozenset({"M1711", "R509"})),
    ]


def test_scope_strips_em_lines_excluded_and_off_module_modifiers():
    c = canonicalize(
        pkg([dx("M1711", True)], [line("99213", ["25"]), line("G2211"), line("96372", ["59", "25", "RT"]), line("90460"), line("J1100", ["JZ", "QW"])]),
        TEST_SCOPE,
    )
    assert [(ln.code, ln.modifiers) for ln in c.lines] == [("96372", ("RT",)), ("J1100", ("JZ",))]


def test_lines_that_differ_only_by_stripped_modifier_merge():
    c = canonicalize(pkg([dx("M1711")], [line("96372", ["59"], 1), line("96372", [], 1)]), TEST_SCOPE)
    assert c.lines == [CanonicalLine(code="96372", modifiers=(), units=2, pointers=frozenset())]


def test_first_listed_fallbacks_and_empty():
    assert canonicalize(pkg([dx("M1711"), dx("R509")], first_listed="r50.9"), TEST_SCOPE).first_listed == "R509"
    assert canonicalize(pkg([dx("M1711")]), TEST_SCOPE).first_listed is None
    e = canonicalize(pkg(), TEST_SCOPE)
    assert e.is_empty and e == Canonical(diagnoses=frozenset(), first_listed=None, lines=[])


def test_canonicalization_is_idempotent():
    for p in (
        pkg([dx("m17.11", True), dx("R50.9")], [line("96372", ["rt", "59"], 2, ["A"]), line("96372", ["RT"], 1, ["B"]), line("99213", ["25"])]),
        pkg(),
        pkg([dx("E119")], [line("J1100", ["JW"], 3, ["A"]), line("J1100", ["JW"], 4, ["A"])]),
    ):
        once = canonicalize(p, TEST_SCOPE)
        assert canonicalize(to_package_like(once), TEST_SCOPE) == once


def test_pydantic_models_are_accepted_as_input():
    from codeloop.schemas import CodingPackage, DiagnosisPred, LinePred

    package = CodingPackage(encounter_id="X", version="dev", run_id="r", diagnoses=[DiagnosisPred(code="m17.11", first_listed=True)], lines=[LinePred(code="96372", modifiers=["RT"], pointers=["M17.11"])])
    c = canonicalize(package, TEST_SCOPE)
    assert c.first_listed == "M1711" and c.lines[0].pointers == frozenset({"M1711"})


def test_ranges():
    assert parse_range("G2211") == ("G2211", "G2211")
    assert code_in_ranges("J1234", ["J0000-J9999"]) and not code_in_ranges("K1234", ["J0000-J9999"])
    assert code_in_ranges("99204", ["99202-99205"]) and not code_in_ranges("99206", ["99202-99205"])
    s = Scope.model_validate({"modules": {"m": {"on": True, "code_ranges": ["0001U-0010U"]}}})
    assert s.in_scope_line("0005U") and s.module_for_line("0005U") == "m" and s.module_for_line("99213") is None


def test_real_scope_yaml_loads_with_on_keys():
    from tests.synthetic import REAL_ROOT

    scope = Scope.load(REAL_ROOT / "config" / "scope.yaml")
    assert scope.modules["core_dx"].on is True and scope.modules["qw"].on is False
    assert scope.in_scope_line("73560") and not scope.in_scope_line("99213")
    assert not scope.allowed_modifier("25") and not scope.allowed_modifier("QW") and scope.allowed_modifier("RT")
