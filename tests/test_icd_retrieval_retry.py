"""FIND-DX-0052: head-term retry candidates for a problem the mapper left uncoded."""

from __future__ import annotations

import sqlite3

from codeloop.tables import Tables
from codeloop.tables.build import BuildSources, build_sqlite
from codeloop.tools.icd_retrieval import IcdRetriever, head_term


def _tables() -> Tables:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    build_sqlite(
        conn,
        BuildSources(
            icd10cm=[
                ("E11", False, "Type 2 diabetes mellitus", "Type 2 diabetes mellitus"),
                ("E119", True, "Type 2 diabetes mellitus without complications", "Type 2 diabetes mellitus without complications"),
                ("E1165", True, "Type 2 diabetes mellitus with hyperglycemia", "Type 2 diabetes mellitus with hyperglycemia"),
                ("O24419", True, "Gestational DM in pregnancy, unspecified control", "Gestational diabetes mellitus in pregnancy, unspecified control"),
                ("I10", True, "Essential (primary) hypertension", "Essential (primary) hypertension"),
                ("R030", True, "Elevated BP reading, without dx of hypertension", "Elevated blood-pressure reading, without diagnosis of hypertension"),
                ("I50", False, "Heart failure", "Heart failure"),
                ("I509", True, "Heart failure, unspecified", "Heart failure, unspecified"),
            ],
            meta={"tables_yaml_sha256": "f" * 64, "parser_version": "1", "icd10cm.release": "FY2027"},
        ),
    )
    return Tables(conn)


def test_head_term_strips_qualifiers_and_parentheticals():
    assert head_term("Diabetes, currently under control") == "Diabetes"
    assert head_term("Hypertension (high blood pressure), well controlled") == "Hypertension"
    assert head_term("Diabetes with elevated blood glucose and hemoglobin A1c") == "Diabetes"
    assert head_term("Type 2 diabetes, stable with medication") == "Type 2 diabetes"
    assert head_term("Congestive heart failure") == "Congestive heart failure"


def test_retry_candidates_offer_the_condition_and_skip_what_was_offered():
    r = IcdRetriever(_tables())
    offered = {"O24419"}  # what a qualifier-laden first pass tends to retrieve
    retry = [c.code for c in r.retry_candidates("Diabetes, currently under control", offered)]
    assert "E119" in retry and not (set(retry) & offered)
    assert "I10" in [c.code for c in r.retry_candidates("Hypertension (high blood pressure), well controlled", {"R030"})]


def test_retry_candidates_empty_without_a_qualifier_to_strip():
    r = IcdRetriever(_tables())
    assert r.retry_candidates("Congestive heart failure", set()) == []
    assert r.retry_candidates("Hypertension", {"I10"}) == []


def test_first_pass_candidates_unchanged():
    r = IcdRetriever(_tables())
    codes = [c.code for c in r.candidates_for_problem("Type 2 diabetes, stable with medication", ["type 2"], "not_applicable", "active")]
    assert codes and len(codes) <= 18


def test_wide_candidates_reach_the_category_default():
    r = IcdRetriever(_tables())
    codes = [c.code for c in r.wide_candidates("Acute heart failure exacerbation", ["acute"], {"E119"})]
    assert "I509" in codes and "E119" not in codes
    assert [c.code for c in r.category_defaults("I50")] == ["I509"] and [c.code for c in r.category_defaults("I10")] == ["I10"]
