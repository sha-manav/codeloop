"""Parsers for the pinned external tables. Each yields plain tuples; descriptors under AMA copyright
(CPT text in the MPFS, MUE and ASP files) are never read into memory beyond the row being skipped."""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

_CODE5 = re.compile(r"^[0-9A-Z]{5}$")
_ICD = re.compile(r"^[A-Z][0-9][0-9A-Z]{1,5}$")


def _cell(row: list[str], cols: dict[str, int], name: str, fallback: int | None = None) -> str:
    i = cols.get(name, fallback)
    return row[i].strip() if i is not None and i < len(row) else ""


# ---------------------------------------------------------------- ICD-10-CM order file (fixed width)
def parse_icd10cm_order(path: Path) -> Iterator[tuple[str, bool, str, str]]:
    """(code without dot, valid_for_submission, short, long).

    Layout: order(1-5) code(7-13) flag(15) short(17-76) long(78-)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if len(line) < 16:
                continue
            code = line[6:13].strip().upper()
            if not _ICD.match(code):
                continue
            valid = line[14] == "1"
            short = line[16:76].strip()
            long = line[77:].strip()
            yield code, valid, short, long or short


# ---------------------------------------------------------------- ICD-10-CM index XML
def _text(el: ET.Element) -> str:
    parts = [el.text or ""]
    for child in el:
        if child.tag in ("nemod",):
            parts.append(" " + (child.text or "") + " ")
        parts.append(child.tail or "")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def parse_icd10cm_index(path: Path) -> Iterator[tuple[str, str]]:
    """(term path, code without dot) for every indexed term that carries a code."""

    def walk(term: ET.Element, prefix: list[str]) -> Iterator[tuple[str, str]]:
        title_el = term.find("title")
        title = _text(title_el) if title_el is not None else ""
        path = [*prefix, title] if title else list(prefix)
        for code_el in term.findall("code"):
            code = (code_el.text or "").strip().upper().replace(".", "")
            if code and _ICD.match(code.rstrip("-")):
                yield ", ".join(path), code.rstrip("-")
        for sub in term.findall("term"):
            yield from walk(sub, path)

    for _event, el in ET.iterparse(str(path), events=("end",)):
        if el.tag == "mainTerm":
            yield from walk(el, [])
            el.clear()


# ---------------------------------------------------------------- HCPCS Level II (fixed width)
def parse_hcpcs_layout(layout_path: Path) -> dict[str, tuple[int, int]]:
    """Field name -> (begin, end) 1-based inclusive positions from the CMS record layout file."""
    fields: dict[str, tuple[int, int]] = {}
    pending: str | None = None
    with open(layout_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"^\s+\d+\.\s+(.+?)\s*$", line)
            if m:
                pending = m.group(1)
                continue
            m = re.match(r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+(CHAR|NUM|DATE|GRP)\s*$", line)
            if m and pending:
                fields[pending] = (int(m.group(2)), int(m.group(3)))
                pending = None
    return fields


def parse_hcpcs(path: Path, layout: dict[str, tuple[int, int]]) -> Iterator[tuple[str, str, str, str, str, str]]:
    """(code, modifier, long, short, termination_date, action_code). Modifier records have a blank code."""

    def field(line: str, name: str, default: tuple[int, int]) -> str:
        b, e = layout.get(name, default)
        return line[b - 1 : e].strip()

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if len(line) < 12:
                continue
            b, e = layout.get("Healthcare Common Procedure Coding System Code", (1, 5))
            raw_code = line[b - 1 : e]
            code = raw_code.strip()
            modifier = field(line, "HCPCS Modifier Code", (4, 5))
            long = field(line, "HCPCS Long Description", (12, 91))
            short = field(line, "HCPCS Short Description", (92, 119))
            term = field(line, "HCPCS Termination Date", (285, 292))
            action = field(line, "HCPCS Action Code", (293, 293))
            if _CODE5.match(code):
                yield code, "", long, short, term, action
            elif raw_code[:3].strip() == "" and len(modifier) == 2:
                yield "", modifier, long, short, term, action


# ---------------------------------------------------------------- NCCI PTP (tab-separated text)
def parse_ncci_ptp(path: Path) -> Iterator[tuple[str, str, str, str, int, str]]:
    """(column1, column2, effective YYYYMMDD, deletion YYYYMMDD or '*', modifier indicator, rationale)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 6 or not (_CODE5.match(parts[0]) and _CODE5.match(parts[1])):
                continue
            try:
                indicator = int(parts[5].strip())
            except ValueError:
                continue
            deletion = parts[4].strip() or "*"
            rationale = parts[6].strip() if len(parts) > 6 else ""
            yield parts[0], parts[1], parts[3].strip(), deletion, indicator, rationale


# ---------------------------------------------------------------- NCCI MUE (csv, cp1252, banner rows)
def parse_ncci_mue(path: Path) -> Iterator[tuple[str, int, str, str]]:
    """(code, mue_value, adjudication indicator, rationale)."""
    with open(path, encoding="cp1252", errors="replace", newline="") as fh:
        header: list[str] | None = None
        for row in csv.reader(fh):
            if not row:
                continue
            if header is None:
                if any("MUE" in c for c in row) and any("Code" in c for c in row):
                    header = [c.strip() for c in row]
                continue
            code = row[0].strip().upper()
            if not _CODE5.match(code):
                continue
            value_i = next((i for i, c in enumerate(header) if "Value" in c), 1)
            mai_i = next((i for i, c in enumerate(header) if "Adjudication" in c), 2)
            rat_i = next((i for i, c in enumerate(header) if "Rationale" in c), 3)
            try:
                value = int(float(row[value_i]))
            except (ValueError, IndexError):
                continue
            mai = row[mai_i].strip() if mai_i < len(row) else ""
            rationale = row[rat_i].strip() if rat_i < len(row) else ""
            yield code, value, mai, rationale


# ---------------------------------------------------------------- MPFS RVU (csv with two-line header)
def parse_mpfs_rvu(path: Path) -> Iterator[tuple[str, str, str, str, str]]:
    """(code, modifier, status, global days, bilateral indicator). The DESCRIPTION column is skipped."""
    with open(path, encoding="cp1252", errors="replace", newline="") as fh:
        upper: list[str] = []
        cols: dict[str, int] | None = None
        for row in csv.reader(fh):
            if cols is None:
                if row[:3] == ["HCPCS", "MOD", "DESCRIPTION"]:
                    names = [
                        f"{(upper[i] if i < len(upper) else '').strip()} {c.strip()}".strip() for i, c in enumerate(row)
                    ]
                    cols = {n: i for i, n in enumerate(names)}
                else:
                    upper = row
                continue
            code = row[0].strip().upper()
            if not _CODE5.match(code):
                continue
            yield (
                code,
                row[1].strip(),
                _cell(row, cols, "STATUS CODE", 3),
                _cell(row, cols, "GLOB DAYS", 14),
                _cell(row, cols, "BILAT SURG", 19),
            )


# ---------------------------------------------------------------- ASP NDC-HCPCS crosswalk (csv, banner rows)
def parse_asp_crosswalk(
    path: Path,
) -> Iterator[tuple[str, str, str, str, str, float | None, float | None, float | None, float | None]]:
    """(hcpcs, ndc, labeler, drug_name, dosage, pkg_size, pkg_qty, billunits, billunits_pkg).

    Short descriptions are skipped (they carry CPT text for vaccine product codes)."""

    def num(v: str) -> float | None:
        try:
            return float(v)
        except ValueError:
            return None

    with open(path, encoding="cp1252", errors="replace", newline="") as fh:
        header: dict[str, int] | None = None
        for row in csv.reader(fh):
            if not row:
                continue
            if header is None:
                if any(c.strip().upper() == "NDC" for c in row):
                    header = {c.strip().upper(): i for i, c in enumerate(row)}
                continue
            code = row[0].strip().upper()
            if not _CODE5.match(code):
                continue
            yield (
                code,
                _cell(row, header, "NDC"),
                _cell(row, header, "LABELER NAME"),
                _cell(row, header, "DRUG NAME"),
                _cell(row, header, "HCPCS DOSAGE"),
                num(_cell(row, header, "PKG SIZE")),
                num(_cell(row, header, "PKG QTY")),
                num(_cell(row, header, "BILLUNITS")),
                num(_cell(row, header, "BILLUNITSPKG")),
            )


# ---------------------------------------------------------------- CDC CVX (pipe-delimited)
def parse_cvx(path: Path) -> Iterator[tuple[str, str, str, str, bool]]:
    """(cvx, short, full, status, nonvaccine)."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            parts = [p.strip() for p in line.rstrip("\r\n").split("|")]
            if len(parts) < 5 or not parts[0]:
                continue
            yield parts[0], parts[1], parts[2], parts[4], parts[5].lower() == "true" if len(parts) > 5 else False
