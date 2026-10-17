#!/usr/bin/env python3
"""Rebuild the sourcing table from the retained catalog snapshot, not live stock."""

import csv
import json
from pathlib import Path

out = Path(__file__).resolve().parent
data = json.loads((out / "catalog-evidence.json").read_text())
ALIASES = {
    "alpha & omega semicon": "alpha & omega semiconductor",
    "murata electronics": "murata",
    "vishay intertech": "vishay",
    "mw(mean well enterprises)": "mean well",
    "cornell dubilier electronics": "cornell dubilier",
    "microchip tech": "microchip technology",
}


def manufacturer_name(value):
    return ALIASES.get(value.lower(), value.lower())


for selection in data["selected"]:
    candidate = selection["candidate"]
    if candidate and (
        candidate["model"] != selection["mpn"]
        or manufacturer_name(candidate["manufacturer"])
        != manufacturer_name(selection["expected_manufacturer"])
    ):
        raise ValueError(f"unapproved manufacturer/MPN match: {selection['mpn']}")
for detail in data["details"]:
    chosen = next(row for row in data["selected"] if row["mpn"] == detail["mpn"])
    actual = detail["result"]
    if (
        actual["model"] != chosen["mpn"]
        or actual["lcsc"] != chosen["candidate"]["lcsc"]
        or manufacturer_name(actual["manufacturer"])
        != manufacturer_name(chosen["expected_manufacturer"])
    ):
        raise ValueError(f"catalog detail identity differs: {detail['mpn']}")

selected = {x["mpn"]: x for x in data["selected"]}
details = {x["mpn"]: x["result"] for x in data["details"]}
rows = []
for b in data["bom"]:
    mpn = b["Manufacturer Part Number"]
    c = selected[mpn]["candidate"]
    d = details.get(mpn, {})
    row = {
        "designators": b["Designator"],
        "quantity": len(b["Designator"].split(",")),
        "mpn": mpn,
        "manufacturer": selected[mpn]["expected_manufacturer"],
        "board_footprint": b["Footprint"],
        "mount": b["Mount"],
        "candidate_lcsc": c["lcsc"] if c else "",
        "catalog_package": d.get("package", ""),
        "observed_stock": d.get("stock", ""),
        "stock_basis": "jlc_get_part snapshot, not order reservation" if c else "",
        "identity_status": "exact MPN + manufacturer-name match; assembly qualification pending"
        if c
        else "no exact manufacturer/MPN candidate in queried catalog",
        "url": d.get("lcsc_url", ""),
        "note": "",
    }
    if mpn == "IPW65R018CFD7":
        row["note"] = (
            "C3289047 is IPW65R018CFD7XKSA1; ordering-suffix equivalence needs manufacturer verification."
        )
    if mpn == "74650074":
        row["note"] = (
            "C5118857 is 74650074R; suffix/packaging equivalence needs manufacturer verification."
        )
    if mpn == "0430451612":
        row["note"] = (
            "Exact code C17616543 found; stock-bearing C491447 omits leading zero, equivalence not approved here."
        )
    if mpn == "0326020.MXP":
        row["note"] = (
            "Cartridge fuse only. PCB footprint represents clips; clip MPN/quantity/current rating and separate assembly entries remain unresolved."
        )
    if c and d.get("stock") == 0:
        row["note"] += (
            " Snapshot shows zero stock: procurement/consignment or hand-assembly decision required."
        )
    rows.append(row)
with (out / "candidate-matches.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
