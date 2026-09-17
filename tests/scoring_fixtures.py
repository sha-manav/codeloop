"""Scope and package fixtures for scorer tests (synthetic, code numbers only)."""

from codeloop.scoring import Scope

TEST_SCOPE = Scope.model_validate(
    {
        "modules": {
            "core_dx": {"on": True},
            "core_lines": {"on": True, "code_ranges": ["96372-96372", "20600-20611", "12001-12007", "J0000-J9999", "90471-90474"]},
            "vaccine_admin": {"on": False, "code_ranges": ["90460-90461"]},
            "distinct_59x": {"on": False, "modifiers": ["59", "XE", "XS", "XP", "XU"]},
            "qw": {"on": False, "modifiers": ["QW"]},
            "jw_jz": {"on": True, "modifiers": ["JW", "JZ"]},
        },
        "exclusions": {"em_code_ranges": ["99202-99205", "99211-99215", "G2211"], "modifiers": ["25"]},
    }
)


def pkg(diagnoses=None, lines=None, first_listed=None):
    return {"diagnoses": diagnoses or [], "lines": lines or [], "first_listed": first_listed}


def dx(code, first=False):
    return {"code": code, "first_listed": first}


def line(code, modifiers=(), units=1, pointers=()):
    return {"code": code, "modifiers": list(modifiers), "units": units, "pointers": list(pointers)}
