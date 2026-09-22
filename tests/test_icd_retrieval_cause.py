"""FIND-DX-0039: the documented cause of a symptom, and candidates for it."""

from __future__ import annotations

from codeloop.tools.icd_retrieval import IcdRetriever, cause_term, is_definitive_code, is_symptom_code
from tests.test_icd_retrieval_retry import _tables


def test_cause_term_finds_a_named_cause_and_ignores_time_and_direction_phrases():
    assert cause_term("Nasal congestion attributed to seasonal allergies") == "seasonal allergies"
    assert cause_term("Nasal congestion from allergies") == "allergies"
    assert cause_term("Right foot pain due to Lisfranc fracture") == "Lisfranc fracture"
    assert cause_term("Grade 3/6 systolic ejection murmur, unchanged from prior exam") is None
    assert cause_term("Back pain, shifted from right to left side") is None
    assert cause_term("Left arm pain from elbow up to the neck") is None
    assert cause_term("Right knee pain") is None


def test_symptom_and_definitive_code_classes():
    assert is_symptom_code("R0981") and is_symptom_code("M25561") and is_symptom_code("M79671")
    assert not is_symptom_code("J309") and not is_symptom_code("S8391XA")
    assert is_definitive_code("J309") and is_definitive_code("S8391XA") and is_definitive_code("E119")
    assert not is_definitive_code("R0981") and not is_definitive_code("Z961") and not is_definitive_code("W010XXA")


def test_cause_candidates_offer_definitive_codes_only():
    r = IcdRetriever(_tables())
    codes = [c.code for c in r.cause_candidates("hypertension")]
    assert "I10" in codes and "R030" not in codes
