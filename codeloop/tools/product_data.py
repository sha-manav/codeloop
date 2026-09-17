"""Product-data tool (spec §7.2): drug HCPCS/NDC/units via the ASP crosswalk; vaccines via CVX."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codeloop.schemas.package import DataGap
from codeloop.tables import Tables

_NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu)", re.I)


@dataclass
class ProductResolution:
    kind: str
    hcpcs: str | None = None
    ndc: str | None = None
    product_name: str = ""
    cvx: str | None = None
    hcpcs_dosage: str | None = None
    billing_units: int | None = None
    arithmetic: str = ""
    candidates: list[str] = field(default_factory=list)


def _dose_amount(dose: str | None) -> tuple[float, str] | None:
    if not dose:
        return None
    m = _NUM.search(dose)
    if not m:
        return None
    return float(m.group(1)), m.group(2).lower()


def resolve_product(
    tables: Tables, name: str, dose: str | None, route: str | None, kind: str, *, field_ref: str
) -> ProductResolution | DataGap:
    if kind == "vaccine":
        rows = tables.cvx_lookup(name)
        actives = [r for r in rows if str(r["status"]).lower() == "active"] or rows
        if len(actives) == 1:
            return ProductResolution(kind="vaccine", cvx=actives[0]["cvx"], product_name=actives[0]["short"])
        if not actives:
            return DataGap(field_ref=field_ref, missing=f"vaccine product not resolvable from name {name!r}")
        return DataGap(field_ref=field_ref, missing=f"vaccine product ambiguous: {len(actives)} CVX matches")
    rows = tables.drug_lookup(name)
    if not rows:
        return DataGap(field_ref=field_ref, missing=f"NDC/HCPCS not resolvable from product name {name!r}")
    codes = sorted({r["hcpcs"] for r in rows})
    if len(codes) != 1:
        return DataGap(field_ref=field_ref, missing=f"product {name!r} maps to several HCPCS codes {codes}")
    hcpcs = codes[0]
    dosage = rows[0]["dosage"]
    amount = _dose_amount(dose)
    unit_amount = _dose_amount(dosage)
    units = None
    arithmetic = ""
    if amount and unit_amount and amount[1] == unit_amount[1] and unit_amount[0] > 0:
        raw = amount[0] / unit_amount[0]
        units = max(1, int(-(-raw // 1)))  # ceiling
        arithmetic = (
            f"{amount[0]:g} {amount[1]} / {unit_amount[0]:g} {unit_amount[1]} per unit = {raw:g} -> {units} unit(s)"
        )
    elif dose:
        return DataGap(field_ref=field_ref, missing=f"cannot convert dose {dose!r} to HCPCS dosage {dosage!r}")
    return ProductResolution(
        kind="drug",
        hcpcs=hcpcs,
        ndc=rows[0]["ndc"],
        product_name=rows[0]["drug_name"],
        hcpcs_dosage=dosage,
        billing_units=units,
        arithmetic=arithmetic,
        candidates=[r["ndc"] for r in rows],
    )
