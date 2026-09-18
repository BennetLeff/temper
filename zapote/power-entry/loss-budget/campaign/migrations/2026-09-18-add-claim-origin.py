#!/usr/bin/env python3
"""Add an explicit `origin` to every claim in the campaign's committed ledgers.

Why this exists
---------------
`zapote-claims` now requires every claim to declare where its value came from
(source / assumption / measurement / derivation), and requires a derivation to
name its inputs. Before that, a claim that performed a derivation while
declaring no parent was compared against nothing and evaded every comparison
rule. See `zapote/packages/zapote-erc/src/evidence_claims.rs`.

How origins are assigned -- derived from what each claim already declares, never
invented:

  1. `derived_from` is set                       -> derivation, inputs = [derived_from]
  2. else `value_kind` is `measured`             -> measurement
  3. else `value_kind` is typical/minimum/maximum -> source
  4. else                                        -> assumption

`value_kind` is the discriminator because it is the claim's OWN existing
declaration of where its number came from: the worker already recorded, per
claim, whether the value was read bounded from a document (typical/minimum/
maximum) or is a model/assumption (`assumed`). Rule 3 is therefore not a guess
about meaning; it reads a field the claim already carries.

Known imprecision, deliberately not papered over: a claim whose value is a
*computation over* source documents but whose `value_kind` is a maximum (e.g. an
action screen built from a catalogue I2t and a computed E/R) is labelled `source`
by rule 3, not `derivation`. Refining those to derivations with named inputs is
follow-up work, and the checker cannot detect the difference in any case -- see
the residual-gap note in `evidence_claims.rs`. Rule 4 is the weakest honest
label: a claim with no bounded or sourced value establishes nothing.

Idempotent: a claim that already declares an origin is left alone.

Usage:  python3 2026-09-18-add-claim-origin.py [--check]
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

CAMPAIGN = pathlib.Path(__file__).resolve().parents[1]

LEDGERS = sorted(CAMPAIGN.glob("runs/*/AR-*/attempt-001/claims.json")) + sorted(
    CAMPAIGN.glob("claims/*.json")
)


def classify(claim: dict) -> tuple[str, list[str]]:
    parent = claim.get("derived_from")
    if parent:
        return "derivation", [parent]
    kind = claim.get("value_kind")
    if kind == "measured":
        return "measurement", []
    if kind in ("typical", "minimum", "maximum"):
        return "source", []
    return "assumption", []


def reorder(claim: dict, origin: str, inputs: list[str]) -> dict:
    """Rebuild the claim with origin/inputs immediately after id."""
    out: dict = {}
    for key, value in claim.items():
        out[key] = value
        if key == "id":
            out["origin"] = origin
            out["inputs"] = inputs
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    rows = []
    for path in LEDGERS:
        raw = path.read_text()
        doc = json.loads(raw)
        claims = doc.get("claims", doc if isinstance(doc, list) else [])
        if not isinstance(claims, list):
            continue
        counts: dict[str, int] = {}
        changed = False
        new_claims = []
        for claim in claims:
            if "origin" in claim and claim["origin"] is not None:
                origin, inputs = claim["origin"], claim.get("inputs", [])
            else:
                origin, inputs = classify(claim)
                changed = True
            counts[origin] = counts.get(origin, 0) + 1
            new_claims.append(reorder(claim, origin, inputs))
        rows.append((path, counts, changed, hashlib.sha256(raw.encode()).hexdigest()[:16]))
        if changed and not check:
            if isinstance(doc, dict):
                doc["claims"] = new_claims
                out = doc
            else:
                out = new_claims
            path.write_text(json.dumps(out, indent=2) + "\n")

    for path, counts, changed, digest in rows:
        tag = "would change" if (changed and check) else ("changed" if changed else "unchanged")
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  [{tag}] {path.relative_to(CAMPAIGN)}  ({summary})  pre={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
