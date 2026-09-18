#!/usr/bin/env python3
"""v2: correct claim provenance after review of the v1 migration.

Why v2 exists
-------------
v1 assigned origins from `value_kind`: typical/minimum/maximum -> source. That is
unsound. `value_kind` describes the *value* (bounded, typical, assumed, measured);
it says nothing about whether the value was read from a document or computed. The
concrete error it produced: `bank-stored-energy` in AR-PROTCKT was labelled a
`measurement` while citing a computation and a netlist. It is a derivation.

v2 rules -- and note what is deliberately NOT a discriminator
-------------------------------------------------------------
  1. `derived_from`/`inputs` present              -> derivation
  2. `value_kind == assumed`                      -> assumption
  3. an explicit OVERRIDE (below)                 -> as stated
  4. otherwise                                    -> source

`value_kind` is used ONLY for rule 2, and only in the one direction that is safe:
a claim that asserts its own value is *assumed* is an assumption. It is never used
to infer that a value came from a document -- that is what rule 3's reviewed table
is for, because deciding it needs the claim's meaning, not its `value_kind`.

OVERRIDES are claims whose value is computed. Each names the ledger claims it
consumes, and where the computation needed an input claim the ledger lacked, that
input claim is added and sourced from a retained artifact.

Idempotent: applying it twice gives the same result.

Usage:  python3 2026-09-18-claim-origin-v2-provenance-fix.py [--check]
"""

from __future__ import annotations

import hashlib
import os
import json
import pathlib
import sys

CAMPAIGN = pathlib.Path(__file__).resolve().parents[1]

MERSEN_COND = "raw/sources/a70qs-conditions.json"

# Computed claims: id -> (origin, inputs, extra fields, added input claims).
# Each reason states the arithmetic, which is why the claim is a derivation.
_PRE_ARCING_CLAIM = {
    "id": "a70qs50-pre-arcing-i2t-max",
    "origin": "source",
    "inputs": [],
    "quantity": "fuse_pre_arcing_i2t_max_a2s",
    "part": "A70QS50-14F",
    "value_kind": "maximum",
    "bound_kind": "upper",
    "source_condition": (
        "Melting I2t (Max) = 0.28 x 10^3 A2s at the catalogue's rated condition "
        "(Mersen HS catalogue 2024, ratings table)"
    ),
    "fault_state": "not_applicable",
    "assertion": "illustrative",
    "evidence": [
        "raw/sources/mersen-hs-high-speed-fuses.pdf",
        "raw/sources/a70qs-conditions.json",
    ],
    "derived_from": None,
    "justification": (
        "Catalogue maximum pre-arcing I2t. Added in v2 so the action screen consumes a "
        "named input claim rather than an unnamed catalogue reference."
    ),
}

# Shared by the AR-BOUNDS attempt ledger and its canonical counterpart.
_FUSE_OVERRIDES = {
    "bank-esr-bank-max": {
        "origin": "derivation",
        "inputs": ["bank-esr-120hz-max"],
        "part_transformation": (
            "Four LGX2W561MELC50 in parallel; bank ESR = per-part ESR / 4."
        ),
        "condition_transformation": (
            "Declared as valid at 120 Hz ONLY: the four-in-parallel bank condition. The "
            "120 Hz maximum is not shown to bound the discharge waveform, which is why the "
            "claim is illustrative."
        ),
        "reason": "ESR/4 for four in parallel",
    },
    "fuse-resistance-hot": {
        "origin": "derivation",
        "inputs": ["fuse-watts-loss-rated"],
        "condition_transformation": (
            "R = P/I^2 evaluated at the catalogue's 50 A rated current. The state is the "
            "thermal-equilibrium (HOT) condition, which is what the watts-loss figure "
            "itself represents."
        ),
        "justification": (
            "R = P/I^2 = 11.6 W / (50 A)^2 = 4.64 mOhm, computed from the catalogue's "
            "watts-loss claim. A derivation, not a value read from the catalogue."
        ),
        "reason": "R = P/I^2",
    },
    "fuse-action-screen": {
        "origin": "derivation",
        "inputs": ["a70qs50-pre-arcing-i2t-max"],
        "condition_transformation": (
            "Screened at the 400 Vdc bus energy E = 179.2376 J: the resistance below which "
            "the available action E/R reaches the catalogue's pre-arcing I2t. The energy is "
            "an external input carried as evidence, not a property of the I2t claim."
        ),
        "justification": (
            "R <= E / 280 A2s = 0.64013 ohm, computed from the catalogue's pre-arcing I2t "
            "bound. A screen, not a melting result; the fault state differs from the "
            "catalogue claim's because the screen is evaluated for the failed-short case."
        ),
        "add": [_PRE_ARCING_CLAIM],
        "reason": "R = E / I2t",
    },
}

OVERRIDES: dict[str, dict[str, dict]] = {
    "AR-PROTCKT": {
        "bank-stored-energy": {
            "origin": "derivation",
            "inputs": ["bank-capacitance"],
            "value_kind": "typical",
            "condition_transformation": (
                "Evaluated at the 400 V bus setpoint: E = 0.5 * C * V^2. The voltage is a "
                "declared operating condition of the discharge, not a property of the "
                "capacitance claim."
            ),
            "justification": (
                "Computed as 0.5 * C * V^2 from the bank capacitance and the 400 V bus "
                "setpoint. A computation, not a measurement. (v1 mislabelled this a "
                "measurement from its value_kind.)"
            ),
            "add": [
                {
                    "id": "bank-capacitance",
                    "origin": "source",
                    "inputs": [],
                    "quantity": "bus_bank_capacitance_f",
                    "part": None,
                    "value_kind": "typical",
                    "bound_kind": "point",
                    "source_condition": "4 x 560 uF (U36-U39) + 470 nF (U40), parallel bank",
                    "fault_state": "not_applicable",
                    "assertion": "illustrative",
                    "evidence": ["raw/netlist_fault_loop.json"],
                    "derived_from": None,
                    "justification": (
                        "Bank capacitance read from the retained fault-loop netlist's "
                        "component evidence. Added in v2 so that the energy computation has "
                        "a named input instead of resting on an external document."
                    ),
                }
            ],
            "reason": "E = 0.5*C*V^2",
        },
    },
    "AR-BOUNDS": _FUSE_OVERRIDES,
    "arbounds": _FUSE_OVERRIDES,
    "AR-MERSEN": {
        "a70qs50-fuse-resistance-estimate": {
            "origin": "derivation",
            "inputs": ["a70qs50-watts-loss"],
            "condition_transformation": (
                "R = P/I^2 evaluated at the catalogue's 50 A rated current, from the "
                "watts-loss claim's condition."
            ),
            "justification": (
                "Computed from the catalogue's watts-loss figure and the 50 A rated current "
                "(R = P/I^2). A derivation, not an independently sourced value."
            ),
            "reason": "R = P/I^2",
        },
    },
}


# The as-stated fixtures are restored to the provenance they were originally
# stated with, so they keep recording the defect rather than being corrected.
RESET: dict[str, dict[str, dict]] = {
    "2026-09-18-arbounds-claims-withdrawn.json": {
        "bank-esr-bank-max": {"origin": "source", "inputs": []},
    },
}


def label_for(path: pathlib.Path) -> str:
    """Which OVERRIDES bucket a ledger belongs to.

    The as-stated (withdrawn) fixtures are deliberately NOT overridden: they must
    keep the provenance they were originally stated with, or they stop being a
    record of the defect.
    """
    if "withdrawn" in path.name:
        return ""
    if path.parent.name == "claims":
        return "arbounds" if "arbounds" in path.name else ""
    for part in path.parts:
        if part.startswith("AR-"):
            return part
    return ""


def ledger_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_evidence(base: pathlib.Path, relative: str) -> str:
    """Return an evidence path as written relative to the ledger's own directory.

    The attempt ledgers live beside their `raw/` tree, so `raw/sources/x.pdf`
    resolves directly. The canonical ledgers live in `claims/` and reference the
    attempt tree instead. Resolve against the real retained file either way
    rather than inventing a path.
    """
    if (base / relative).exists():
        return relative
    name = pathlib.Path(relative).name
    for candidate in sorted(CAMPAIGN.rglob(name)):
        return os.path.relpath(candidate, base)
    raise FileNotFoundError(f"no retained artifact for {relative}")


def main(argv: list[str]) -> int:
    check = "--check" in argv
    ledgers = sorted(CAMPAIGN.glob("runs/*/AR-*/attempt-001/claims.json")) + sorted(
        CAMPAIGN.glob("claims/*.json")
    )
    for path in ledgers:
        bucket = label_for(path)
        overrides = OVERRIDES.get(bucket, {})
        doc = json.loads(path.read_text())
        claims = doc["claims"]
        by_id = {c["id"]: c for c in claims}
        base = path.parent
        changed = False

        # 0. Restore as-stated fixtures to their original provenance.
        for claim_id, spec in RESET.get(path.name, {}).items():
            claim = by_id.get(claim_id)
            if claim is None:
                continue
            for field, value in spec.items():
                if claim.get(field) != value:
                    claim[field] = value
                    changed = True

        # 1. Regularise every claim's origin under the v2 rules.
        for claim in claims:
            if claim["id"] in overrides:
                spec = overrides[claim["id"]]
                origin, inputs = spec["origin"], spec["inputs"]
            elif claim.get("derived_from") or claim.get("inputs"):
                origin = "derivation"
                inputs = claim.get("inputs") or (
                    [claim["derived_from"]] if claim.get("derived_from") else []
                )
            elif claim.get("value_kind") == "assumed":
                origin, inputs = "assumption", []
            else:
                origin, inputs = "source", []
            if claim.get("origin") != origin or claim.get("inputs") != inputs:
                claim["origin"] = origin
                claim["inputs"] = inputs
                changed = True

        # 2. Apply any override extras, and add missing input claims.
        for claim_id, spec in overrides.items():
            claim = by_id.get(claim_id)
            if claim is None:
                continue
            for field, value in spec.items():
                if field in ("origin", "inputs", "add", "reason"):
                    continue
                if claim.get(field) != value:
                    claim[field] = value
                    changed = True
            for addition in spec.get("add", []):
                if addition["id"] in by_id:
                    continue
                entry = dict(addition)
                paths = entry.pop("evidence")
                entry["evidence"] = [
                    {"path": resolve_evidence(base, p), "sha256": ledger_sha(base / resolve_evidence(base, p))}
                    for p in paths
                ]
                claims.append(entry)
                by_id[entry["id"]] = entry
                changed = True

        if check:
            status = "would change" if changed else "unchanged"
        else:
            if changed:
                path.write_text(json.dumps(doc, indent=2) + "\n")
            status = "changed" if changed else "unchanged"
        counts: dict[str, int] = {}
        for claim in claims:
            counts[claim["origin"]] = counts.get(claim["origin"], 0) + 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  [{status}] {path.relative_to(CAMPAIGN)}  ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
