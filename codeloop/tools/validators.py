"""Code-set validators (spec §7.3)."""

from __future__ import annotations

from codeloop.tables import Tables

VALID_MODIFIERS: frozenset[str] = frozenset({"RT", "LT", "50", "59", "XE", "XS", "XP", "XU", "QW", "JW", "JZ", "25"})
BYPASS_MODIFIERS: frozenset[str] = frozenset({"59", "XE", "XS", "XP", "XU"})
X_MODIFIERS: frozenset[str] = frozenset({"XE", "XS", "XP", "XU"})


def is_valid_modifier(modifier: str) -> bool:
    return modifier.upper() in VALID_MODIFIERS


def line_code_exists(tables: Tables, code: str) -> bool:
    return tables.line_code_exists(code)


def bilateral_indicator(tables: Tables, code: str) -> str | None:
    return tables.bilateral_indicator(code)


def is_drug_code(code: str) -> bool:
    return code[:1] == "J" or code[:1] == "Q"
