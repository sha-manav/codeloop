import sqlite3

from codeloop.tables import parsers
from codeloop.tables.build import BuildSources, build_sqlite
from codeloop.tables.config import load_tables_config, save_tables_config
from codeloop.tables.store import Tables
from tests.synthetic import REAL_ROOT


def _w(tmp_path, name, text, encoding="utf-8"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def test_parse_icd_order_and_index(tmp_path):
    order = _w(tmp_path, "order.txt",
        "00001 M17     0 Osteoarthritis of knee                                        Osteoarthritis of knee\n"
        "00002 M1710   1 Unilateral primary osteoarthritis, unspecified knee           Unilateral primary osteoarthritis, unspecified knee\n"
        "00003 M1711   1 Unilateral primary osteoarthritis, right knee                 Unilateral primary osteoarthritis, right knee\n"
        "00004 M1712   1 Unilateral primary osteoarthritis, left knee                  Unilateral primary osteoarthritis, left knee\n"
        "garbage line\n")
    rows = list(parsers.parse_icd10cm_order(order))
    assert rows[0] == ("M17", False, "Osteoarthritis of knee", "Osteoarthritis of knee") and rows[2][0] == "M1711" and rows[2][1]
    xml = _w(tmp_path, "index.xml",
        "<ICD10CM.index><mainTerm><title>Osteoarthritis</title><code>M19.90</code>"
        "<term level=\"1\"><title>knee<nemod>(primary)</nemod></title><code>M17.9</code>"
        "<term level=\"2\"><title>unilateral</title><code>M17.10</code></term></term></mainTerm>"
        "<mainTerm><title>Abdominalgia</title><see>Pain, abdominal</see></mainTerm></ICD10CM.index>")
    idx = list(parsers.parse_icd10cm_index(xml))
    assert ("Osteoarthritis", "M1990") in idx and ("Osteoarthritis, knee (primary), unilateral", "M1710") in idx and len(idx) == 3


def test_parse_hcpcs_with_layout(tmp_path):
    layout = _w(tmp_path, "layout.txt",
        "  1.   Healthcare Common Procedure Coding System Code\n                                 5      1      5    CHAR\n"
        "  4.   HCPCS Modifier Code\n                                 2      4      5    CHAR\n"
        "  7.   HCPCS Long Description\n                                80     12     91    CHAR\n"
        "  8.   HCPCS Short Description\n                                28     92    119    CHAR\n")
    lay = parsers.parse_hcpcs_layout(layout)
    assert lay["HCPCS Long Description"] == (12, 91)
    line1 = "J1100" + "00100" + "7" + "Injection, dexamethasone sodium phosphate, 1 mg".ljust(80) + "Dexamethasone sodium phos".ljust(28) + " " * 200
    line2 = "   RT" + "00200" + "7" + "Right side".ljust(80) + "Right side".ljust(28) + " " * 200
    data = _w(tmp_path, "hcpcs.txt", line1 + "\n" + line2 + "\n")
    rows = list(parsers.parse_hcpcs(data, lay))
    assert rows[0][0] == "J1100" and rows[0][2].startswith("Injection, dexamethasone") and rows[0][3] == "Dexamethasone sodium phos"
    assert rows[1][0] == "" and rows[1][1] == "RT"


def test_parse_ptp_mue_rvu_asp_cvx(tmp_path):
    ptp = _w(tmp_path, "ptp.txt", "CPT only copyright\t\t\t\t\t\t\nColumn 1\tColumn 2\t*\tEffective\tDeletion\tModifier\tRationale\n"
             "73560\t73562\t\t20200101\t*\t1\tMore extensive procedure\n73564\t73560\t*\t19960101\t20191231\t0\tMutually exclusive\n")
    rows = list(parsers.parse_ncci_ptp(ptp))
    assert rows == [("73560", "73562", "20200101", "*", 1, "More extensive procedure"), ("73564", "73560", "19960101", "20191231", 0, "Mutually exclusive")]
    mue = _w(tmp_path, "mue.csv", '"CPT copyright banner"\n\nHCPCS/CPT Code,Practitioner Services MUE Values,MUE Adjudication Indicator,MUE Rationale\n73560,2,"2 Date of Service Edit: Policy",Anatomic\n', encoding="cp1252")
    assert list(parsers.parse_ncci_mue(mue)) == [("73560", 2, "2 Date of Service Edit: Policy", "Anatomic")]
    rvu = _w(tmp_path, "rvu.csv",
        ",,banner,,,,,,,,,,,,,,,,,,,,,,,,,,,,,\n"
        ",,,STATUS,MEDICARE,WORK,NON-FAC,NA,FACILITY,NA,MP,NON-FACILITY,FACILITY,PCTC,GLOB,PRE,INTRA,POST,MULT,BILAT,ASST,CO-,TEAM,PRIC,ENDO,CONV,DIAGNOSTIC,CALCULATION,FAMILY,PAYMENT,PAYMENT,PAYMENT\n"
        "HCPCS,MOD,DESCRIPTION,CODE,PAYMENT,RVU,PE RVU,INDICATOR,PE RVU,INDICATOR,RVU,TOTAL,TOTAL,IND,DAYS,OP,OP,OP,PROC,SURG,SURG,SURG,SURG,IND,BASE,FACTOR,PROCEDURES,FLAG,INDICATOR,AMOUNT,AMOUNT,AMOUNT\n"
        "73560,,SECRET CPT TEXT,A,,0.17,0.62,,0.62,,0.01,0.80,0.80,1,XXX,0,0,0,0,1,0,0,0,0,,33.4,88,0,99,0,0,0\n"
        "73560,26,SECRET CPT TEXT,A,,0.17,0.06,,0.06,,0.01,0.24,0.24,1,XXX,0,0,0,0,1,0,0,0,0,,33.4,88,0,99,0,0,0\n", encoding="cp1252")
    rows = list(parsers.parse_mpfs_rvu(rvu))
    assert rows[0] == ("73560", "", "A", "XXX", "1") and rows[1][1] == "26" and all("SECRET" not in x for r in rows for x in r)
    asp = _w(tmp_path, "asp.csv", "July 2026 ASP NDC - HCPCS Crosswalk,,,,,,,,,\n,,,,,,,,,\n_2026_CODE,Short Description,LABELER NAME,NDC,Drug Name,HCPCS dosage,PKG SIZE,PKG QTY,BILLUNITS,BILLUNITSPKG\n"
             "J1100,Dexamethasone sodium phos,Fresenius,63323-0165-01,Dexamethasone Sodium Phosphate,1 MG,1,1,4,4\n", encoding="cp1252")
    rows = list(parsers.parse_asp_crosswalk(asp))
    assert rows[0][0] == "J1100" and rows[0][3] == "Dexamethasone Sodium Phosphate" and rows[0][7] == 4.0 and "Short" not in str(rows)
    cvx = _w(tmp_path, "cvx.txt", "﻿140       |Influenza, seasonal, injectable, preservative free|Influenza, seasonal, injectable, preservative free||Active|False|2010/05/28\n")
    assert list(parsers.parse_cvx(cvx)) == [("140", "Influenza, seasonal, injectable, preservative free", "Influenza, seasonal, injectable, preservative free", "Active", False)]


def synthetic_tables() -> Tables:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    build_sqlite(conn, BuildSources(
        icd10cm=[("M17", False, "Osteoarthritis of knee", "Osteoarthritis of knee"),
                 ("M1710", True, "Unilateral primary OA, unspecified knee", "Unilateral primary osteoarthritis, unspecified knee"),
                 ("M1711", True, "Unilateral primary OA, right knee", "Unilateral primary osteoarthritis, right knee"),
                 ("M1712", True, "Unilateral primary OA, left knee", "Unilateral primary osteoarthritis, left knee"),
                 ("R509", True, "Fever, unspecified", "Fever, unspecified"),
                 ("S9230XA", True, "Fracture of unspecified metatarsal bone(s), unspecified foot, initial encounter for closed fracture", "Fracture of unspecified metatarsal bone(s), unspecified foot, initial encounter for closed fracture"),
                 ("Z8601", True, "Personal history of colon polyps", "Personal history of colonic polyps")],
        icd10cm_index=[("Fracture, Lisfranc", "S9230"), ("Osteoarthritis, knee, unilateral", "M1710")],
        hcpcs=[("J1100", "", "Injection, dexamethasone sodium phosphate, 1 mg", "Dexamethasone", "", ""), ("", "RT", "Right side", "Right side", "", "")],
        ptp=[("73560", "73562", "20200101", "*", 1, "More extensive procedure"), ("73564", "73560", "19960101", "20191231", 0, "old"),
             ("96372", "99213", "20200101", "*", 0, "Standards of medical/surgical practice")],
        mue=[("73560", 2, "2 Date of Service Edit: Policy", "Anatomic"), ("J1100", 40, "3", "")],
        rvu=[("73560", "", "A", "XXX", "1"), ("73562", "", "A", "XXX", "1"), ("73564", "", "A", "XXX", "1"), ("96372", "", "A", "XXX", "0"), ("99213", "", "A", "XXX", "9"), ("20610", "", "A", "000", "1"), ("71046", "", "A", "XXX", "0")],
        asp=[("J1100", "63323-0165-01", "Fresenius", "Dexamethasone Sodium Phosphate", "1 MG", 1.0, 1.0, 4.0, 4.0)],
        cvx=[("140", "Influenza, seasonal, injectable, preservative free", "Influenza, seasonal, injectable, preservative free", "Active", False)],
        meta={"tables_yaml_sha256": "f" * 64, "parser_version": "1", "icd10cm.release": "FY2027"},
    ))
    return Tables(conn)


def test_store_queries():
    t = synthetic_tables()
    assert t.icd_exists("M1711") and t.icd_valid("M1711") and not t.icd_valid("M17") and not t.icd_exists("M1799")
    hits = t.icd_search("right knee osteoarthritis", k=5)
    assert hits and hits[0].code in ("M1711", "M1710", "M1712", "M17")
    assert any(h.code == "M1711" for h in hits) and all(h.valid for h in t.icd_search("knee osteoarthritis", valid_only=True))
    assert [h.code for h in t.icd_search("Lisfranc fracture", k=3)][:1] == ["S9230XA"] or any(h.code.startswith("S9230") for h in t.icd_search("Lisfranc", k=3))
    assert t.icd_search("") == [] and t.icd_search("of the") == []
    assert [c for c, _ in t.icd_laterality_variants("M1711")] == ["M1710", "M1711", "M1712"]
    assert t.line_code_exists("73560") and t.line_code_exists("J1100") and not t.line_code_exists("99999")
    assert t.hcpcs_modifier_known("RT") and not t.hcpcs_modifier_known("ZZ")
    assert t.bilateral_indicator("73560") == "1" and t.bilateral_indicator("96372") == "0" and t.bilateral_indicator("00000") is None
    assert t.ptp_edit("73560", "73562", "20261001") == (1, "More extensive procedure")
    assert t.ptp_edit("73564", "73560", "20261001") is None  # deleted 2019
    assert t.ptp_edit("73564", "73560", "20180101") == (0, "old")
    assert t.ptp_edit("73562", "73560", "20261001") is None  # ordered pair
    assert t.mue("73560") == (2, "2 Date of Service Edit: Policy") and t.mue("00000") is None
    assert t.drug_lookup("dexamethasone")[0]["hcpcs"] == "J1100" and t.cvx_lookup("influenza")[0]["cvx"] == "140"
    assert t.version.startswith("tables.yaml:ffffffffffffffff") and t.release("icd10cm") == "FY2027"
    assert t.count("ptp") == 3


def test_tables_config_roundtrip(tmp_path):
    cfg = load_tables_config(REAL_ROOT / "config" / "tables.yaml")
    assert "icd10cm" in cfg.tables and cfg.tables["icd10cm"].release == "FY2027" and len(cfg.source_sha256) == 64
    out = tmp_path / "tables.yaml"
    cfg.tables["cvx"].files[0].sha256 = "a" * 64
    save_tables_config(out, cfg)
    again = load_tables_config(out)
    assert again.tables["cvx"].files[0].sha256 == "a" * 64 and again.tables["hcpcs"].files[0].members[1] == "HCPC2026_recordlayout.txt"
