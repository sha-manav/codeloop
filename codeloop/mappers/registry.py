"""Which service categories have a mapper, and which scope module each mapper writes lines for."""

from __future__ import annotations

from codeloop.mappers import imaging

CATEGORY_MODULE: dict[str, str] = {c: imaging.MODULE for c in imaging.CATEGORIES}


def mappable_categories(scope) -> set[str]:
    return {
        c
        for c, m in CATEGORY_MODULE.items()
        if m in scope.modules and scope.modules[m].on and scope.modules[m].code_ranges
    }
