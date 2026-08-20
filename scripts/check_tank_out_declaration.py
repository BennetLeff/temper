#!/usr/bin/env python3
"""CI gate: `tank-out`'s insulation group must be DERIVED from a declared,
dated, digest-anchored BENCH MEASUREMENT of the voltage across T1's primary --
and while no such measurement exists, this gate fails closed.

WHAT IS AT STAKE
----------------
`tank-out` is a two-pad net (the litz coil's far terminal at R30 pad 2, and
T1's primary input at T1 pad 1) separated from `PWR_RTN` by exactly one thing:
a single turn of the CST3015-100ED primary (`elec/src/main.ato:823-824`). Its
classification decides whether this board has a component blocker at all:

  TANK  -> SELV<->TANK  -> >=20.0 mm, NOT DETERMINABLE. T1 stands off
           9.100 mm and fails by >=10.9 mm, and no commercially available
           current transformer clears it -- the category tops out at 9.2 mm.
  MAINS -> MAINS<->SELV -> 4.8 mm. T1 passes at 9.100 mm with 4.3 mm of
           margin, and every isolation component on the board is compliant.

WHAT THIS GATE ENFORCES
-----------------------
1. **The declaration resolves.** ``elec/tank_out_working_voltage.yaml`` parses,
   carries every required key, has no null in the `measurement:` block, is not
   STALE (its facts have not been edited since the verification digest that
   backs them), names a commit that RESOLVES in this repository, and names
   artifacts that exist.

2. **The measurement is physically self-consistent.** A winding drop with no
   operating current behind it is not a measurement of anything, so the
   operating condition is required. Probe bandwidth is required and checked
   against the switching frequency, because the failure mode this measurement
   is most exposed to is instrumental: insufficient bandwidth rolls off a
   square-edged 47 kHz waveform and UNDER-reports r.m.s., biasing the result
   toward the convenient answer.

3. **The probe was differential or isolated.** Declared explicitly, and false
   is a hard error rather than a warning. An earth-referenced probe on this
   mains-referenced floating bus does not produce a poor measurement; it
   produces a short to protective earth through the probe ground lead. A
   reading taken that way is not admissible evidence about anything.

4. **The consequence is derived, not declared.** The measured drop is composed
   against `PWR_RTN`'s declared 120.0 V r.m.s. to earth, the IEC 60335-1
   Table 17 row is selected from the composition, and the implied group for
   `tank-out` is printed. This gate NEVER edits `elec/insulation_manifest.yaml`
   and never reclassifies anything; group membership stays a deliberate human
   edit with its own digest and its own verification block.

5. **The two declarations must not silently disagree.** If
   ``elec/insulation_manifest.yaml`` is present, the group it currently assigns
   `tank-out` is compared against the group the measurement implies. A
   measurement supporting MAINS while the manifest still says TANK is reported
   as an UNCONSUMED RESULT and fails; a manifest saying MAINS with no
   measurement behind it is reported as UNSUPPORTED and fails. Both directions
   fail, because both are the same defect: a safety-relevant number and the
   evidence for it drifting apart.

WHY EXIT NON-ZERO ON SOMETHING NOBODY HAS DONE YET
---------------------------------------------------
Because the alternative is worse, and this repository has already paid for it
once. The 570.5 V r.m.s. figure that put `tank-out` in TANK is measured at
`tank.c_tank1-p2` -- a DIFFERENT net, with four pads, on the far side of the
coil. All 20 occurrences of that figure name that net. `tank-out` appears four
times in the same document and never carries a voltage. A number attached to
the wrong node passed unchallenged for months because nothing required the
node's own voltage to exist before the classification that depends on it did.

So: no measurement, no pass.

**Never make this gate pass by declaring a simulated value.** There IS a
simulation of this node (``simulation/harness/nets/tank_out_winding_voltage.cir``
and ``simulation/harness/run_tank_out_winding_voltage.py``). It is informative,
it is committed, and it is NOT admissible here. It found something the prior
analytical work missed -- that the drop is dominated by the primary's leakage
reactance, which no document in this repository bounds -- and that finding is
precisely why a measurement is needed rather than more arithmetic.

WHAT THIS GATE CANNOT DO
------------------------
No gate makes a measurement real. Everything it checks is a *claim*. It cannot
observe an oscilloscope, cannot tell a differential probe from an
earth-referenced one, and cannot tell a correct reading from one taken with the
wrong probe on a floating mains-referenced bus. The procedure at
``docs/hardware/BENCH-tank-out-winding-voltage.md`` is the safeguard there --
this gate is not. It prints this same paragraph on every run.

USAGE
-----
  uv run python scripts/check_tank_out_declaration.py
  uv run python scripts/check_tank_out_declaration.py --print-digest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: uv run python scripts/check_tank_out_declaration.py")
    raise

REPO_ROOT = Path(__file__).resolve().parent.parent
DECLARATION = REPO_ROOT / "elec" / "tank_out_working_voltage.yaml"
INSULATION_MANIFEST = REPO_ROOT / "elec" / "insulation_manifest.yaml"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DISAGREEMENT = 3
EXIT_UNRESOLVABLE = 4
EXIT_GATE_ERROR = 5
EXIT_NO_MEASUREMENT = 6

# --- Derivation inputs, every one of them cited -----------------------------

# `PWR_RTN`'s declared working voltage against earth. elec/insulation_manifest
# .yaml, MAINS group, on the IEC 60335-1 cl. 29.2 neutral-NOTE basis: no earth
# credit is taken for the neutral connection. A DECLARATION, never measured --
# which is why measurement.v_tank_out_to_earth_vrms is also required, so that
# this figure becomes falsifiable too.
PWR_RTN_TO_EARTH_VRMS = 120.0

# IEC 60335-1 Table 17 row ii covers >50-125 V. The composition
# sqrt(120^2 + v^2) stays inside it for any winding drop up to
# sqrt(125^2 - 120^2) = 35.0 V exactly. ARITHMETIC FROM THE ROW BOUNDARY, not
# a reconstructed standards value.
TABLE_17_ROW_II_CEILING_VRMS = 125.0
ROW_II_MAX_WINDING_DROP_VRMS = math.sqrt(
    TABLE_17_ROW_II_CEILING_VRMS**2 - PWR_RTN_TO_EARTH_VRMS**2
)  # == 35.0

# THIS PROJECT'S OWN falsification criterion, published in advance at
# docs/evidence/2026-08-19-t1-sense-node-relocation.md Sec 5: "If this exceeds
# ~1 V, Sec 3 is wrong and the TANK classification should stand." NOT a
# standards clause and not presented as one.
PROJECT_FALSIFICATION_THRESHOLD_VRMS = 1.0

# Bandwidth floor for the probe and scope. The tank waveform is a
# square-edged 47 kHz drive; resolving its r.m.s. faithfully needs harmonic
# content well above the fundamental. 20x the switching frequency is this
# gate's own declared engineering requirement (it is not a standards figure);
# the bench procedure explains the choice and its consequences.
BANDWIDTH_MULTIPLE_OF_FSW = 20.0

REQUIRED_MEASUREMENT_KEYS = [
    "v_tank_out_to_pwr_rtn_vrms",
    "v_tank_out_to_earth_vrms",
    "operating_power_w",
    "tank_current_arms",
    "f_switching_hz",
    "pan_description",
    "probe_model",
    "probe_is_differential_or_isolated",
    "probe_bandwidth_hz",
    "probe_attenuation_ratio",
    "scope_model",
    "scope_bandwidth_hz",
]

REQUIRED_VERIFICATION_KEYS = [
    "verified_on",
    "verified_by",
    "method",
    "measured_at_commit",
    "artifacts",
    "declared_state_sha256",
]

LIMITATION = """\
WHAT THIS GATE CANNOT DO: no gate makes a measurement real. Everything checked
above is a claim. This gate cannot observe an oscilloscope, cannot tell a
differential probe from an earth-referenced one, and cannot tell a correct
reading from one taken with the wrong probe on a floating mains-referenced bus
-- which is an equipment-destruction, arc and shock hazard, not merely a wrong
number. docs/hardware/BENCH-tank-out-winding-voltage.md is the safeguard there.
"""


def measurement_digest(measurement: dict) -> str:
    """Digest of the canonical form of the `measurement:` block.

    Canonical form is JSON with sorted keys and no insignificant whitespace, so
    comments, key order and YAML formatting are all free to change without
    invalidating a verification. This is a pure-Python analogue of
    ``temper_design_bundle.enclosure_facts_digest`` -- deliberately NOT a call
    into the compiled extension, so this gate has no build dependency and can
    run anywhere the measurement can be entered.
    """
    canonical = json.dumps(measurement, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def commit_resolves(sha: str) -> bool:
    """True if `sha` names an object that actually exists in this repository."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(sha or "")):
        return False
    try:
        done = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def tank_out_group_in_manifest() -> str | None:
    """Which insulation group `elec/insulation_manifest.yaml` puts tank-out in.

    Returns None if the manifest is not present in this working tree (it lives
    on a separate branch), which is reported but is not by itself a failure --
    the declaration and its gate must be able to land independently.
    """
    if not INSULATION_MANIFEST.exists():
        return None
    try:
        doc = yaml.safe_load(INSULATION_MANIFEST.read_text()) or {}
    except yaml.YAMLError:
        return None
    for name, group in (doc.get("groups") or {}).items():
        if "tank-out" in (group.get("nets") or []):
            return name
    return None


def derive(v_drop: float) -> tuple[str, str, list[str]]:
    """Derive the consequence of a measured winding drop.

    Returns (verdict, implied_group, explanation_lines). This function decides
    NOTHING about the manifest; it reports what the number implies.
    """
    composed = math.hypot(PWR_RTN_TO_EARTH_VRMS, v_drop)
    lines = [
        f"  measured drop across T1 primary : {v_drop:.4f} V r.m.s.",
        f"  PWR_RTN to earth (DECLARED)     : {PWR_RTN_TO_EARTH_VRMS:.1f} V r.m.s.",
        f"  composed, sqrt(120^2 + v^2)     : {composed:.4f} V r.m.s.",
    ]

    if composed <= TABLE_17_ROW_II_CEILING_VRMS:
        lines.append("  IEC 60335-1 Table 17 row        : ii (>50-125 V)")
    else:
        lines.append(
            f"  IEC 60335-1 Table 17 row        : ABOVE ii -- composition "
            f"{composed:.2f} V exceeds the {TABLE_17_ROW_II_CEILING_VRMS:.0f} V boundary"
        )

    if v_drop <= PROJECT_FALSIFICATION_THRESHOLD_VRMS:
        lines.append(
            f"  vs the project's own <{PROJECT_FALSIFICATION_THRESHOLD_VRMS:.1f} V "
            f"prediction  : HOLDS "
            f"({PROJECT_FALSIFICATION_THRESHOLD_VRMS / max(v_drop, 1e-12):.0f}x inside)"
        )
        return (
            "SUPPORTS_MAINS",
            "MAINS",
            lines
            + [
                "",
                "  => The measurement supports moving `tank-out` into the MAINS",
                "     group, making T1's crossing MAINS<->SELV at 4.8 mm required",
                "     against 9.100 mm standing off. That move is a SEPARATE,",
                "     deliberate edit to elec/insulation_manifest.yaml with its own",
                "     verification block and digest. This gate does not make it.",
            ],
        )

    if v_drop <= ROW_II_MAX_WINDING_DROP_VRMS:
        return (
            "CONTESTED",
            "UNDECIDED",
            lines
            + [
                "",
                f"  => CONTESTED. The drop exceeds this project's own published",
                f"     falsification threshold of "
                f"{PROJECT_FALSIFICATION_THRESHOLD_VRMS:.1f} V, so the argument in",
                "     docs/evidence/2026-08-19-t1-sense-node-relocation.md Sec 3 is",
                "     falsified as stated -- but the Table 17 row does not move,",
                f"     because the composition stays inside row ii for any drop up",
                f"     to {ROW_II_MAX_WINDING_DROP_VRMS:.1f} V.",
                "     A human must reconcile this. A script must not pick the",
                "     convenient branch.",
            ],
        )

    return (
        "CONFIRMS_TANK",
        "TANK",
        lines
        + [
            "",
            f"  => The drop exceeds {ROW_II_MAX_WINDING_DROP_VRMS:.1f} V, so the",
            "     composition leaves Table 17 row ii. The TANK classification",
            "     STANDS, and T1 is a real blocker: 9.100 mm standing off against",
            "     >=20.0 mm required, with no commercially available current",
            "     transformer clearing it (the category tops out at 9.2 mm).",
        ],
    )


def run() -> int:
    print("=" * 78)
    print("tank-out working-voltage declaration")
    print("=" * 78)
    try:
        shown = DECLARATION.relative_to(REPO_ROOT)
    except ValueError:
        shown = DECLARATION
    print(f"declaration: {shown}")
    print()

    if not DECLARATION.exists():
        print(f"GATE ERROR: {DECLARATION} does not exist.")
        return EXIT_GATE_ERROR

    try:
        doc = yaml.safe_load(DECLARATION.read_text()) or {}
    except yaml.YAMLError as exc:
        print(f"GATE ERROR: {DECLARATION.name} does not parse: {exc}")
        return EXIT_GATE_ERROR

    measurement = doc.get("measurement")
    verification = doc.get("verification")
    if not isinstance(measurement, dict) or not isinstance(verification, dict):
        print("GATE ERROR: `measurement:` and `verification:` must both be mappings.")
        return EXIT_GATE_ERROR

    missing = [k for k in REQUIRED_MEASUREMENT_KEYS if k not in measurement]
    if missing:
        print(f"GATE ERROR: `measurement:` is missing required keys: {missing}")
        print("A missing key is rejected exactly as a null one. Do not delete a")
        print("field to make this gate pass.")
        return EXIT_GATE_ERROR

    nulls = [k for k in REQUIRED_MEASUREMENT_KEYS if measurement.get(k) is None]
    manifest_group = tank_out_group_in_manifest()

    # ---- The expected, fail-closed state --------------------------------
    if nulls:
        print("NO MEASUREMENT DECLARED.")
        print()
        print(f"  {len(nulls)} of {len(REQUIRED_MEASUREMENT_KEYS)} required facts are null:")
        for k in nulls:
            print(f"    - {k}")
        print()
        print("  `tank-out`'s insulation group is therefore not supported by any")
        print("  measurement of `tank-out`. elec/insulation_manifest.yaml keeps it")
        print("  TANK, the SELV<->TANK requirement stays IndeterminateWithFloor at")
        print("  20.0 mm, and check_insulation_pairings.py keeps exiting 6.")
        print()
        if manifest_group is not None:
            print(f"  insulation_manifest.yaml currently assigns tank-out: {manifest_group}")
            if manifest_group != "TANK":
                print("  UNSUPPORTED: the manifest has moved tank-out out of TANK with")
                print("  no measurement behind it. Restore it or take the measurement.")
                print()
                print(LIMITATION)
                return EXIT_DISAGREEMENT
        else:
            print("  (elec/insulation_manifest.yaml is not present in this working")
            print("   tree -- it lives on feat/per-pairing-creepage-derivation. The")
            print("   cross-check is skipped, not passed.)")
        print()
        print("  A SIMULATION IS NOT A MEASUREMENT. Do not fill these fields from")
        print("  simulation/harness/run_tank_out_winding_voltage.py. See")
        print("  docs/hardware/BENCH-tank-out-winding-voltage.md to take the real one.")
        print()
        print(LIMITATION)
        return EXIT_NO_MEASUREMENT

    # ---- A measurement is declared: validate it -------------------------
    v_missing = [k for k in REQUIRED_VERIFICATION_KEYS if verification.get(k) in (None, "", [])]
    if v_missing:
        print(f"UNRESOLVABLE: `verification:` is incomplete: {v_missing}")
        print(LIMITATION)
        return EXIT_UNRESOLVABLE

    if not measurement["probe_is_differential_or_isolated"]:
        print("UNRESOLVABLE: probe_is_differential_or_isolated is false.")
        print()
        print("  An earth-referenced probe on this mains-referenced floating bus")
        print("  does not produce a poor measurement -- it shorts the bus to")
        print("  protective earth through the probe ground lead. A reading taken")
        print("  that way is not admissible evidence about anything, and this gate")
        print("  will not derive a safety classification from it.")
        print(LIMITATION)
        return EXIT_UNRESOLVABLE

    f_sw = float(measurement["f_switching_hz"])
    need_bw = BANDWIDTH_MULTIPLE_OF_FSW * f_sw
    for label, key in (("probe", "probe_bandwidth_hz"), ("scope", "scope_bandwidth_hz")):
        bw = float(measurement[key])
        if bw < need_bw:
            print(f"UNRESOLVABLE: {label} bandwidth {bw / 1e6:.3f} MHz is below the")
            print(f"  {BANDWIDTH_MULTIPLE_OF_FSW:.0f}x f_sw floor of {need_bw / 1e6:.3f} MHz.")
            print("  Insufficient bandwidth rolls off a square-edged waveform and")
            print("  UNDER-reports r.m.s. -- it biases this measurement toward the")
            print("  convenient answer, so it is a hard error, not a warning.")
            print(LIMITATION)
            return EXIT_UNRESOLVABLE

    if float(measurement["tank_current_arms"]) <= 0:
        print("UNRESOLVABLE: tank_current_arms must be positive. A winding drop with")
        print("  no operating current behind it is not a measurement of anything.")
        print(LIMITATION)
        return EXIT_UNRESOLVABLE

    declared_digest = str(verification["declared_state_sha256"])
    actual_digest = measurement_digest(measurement)
    if declared_digest != actual_digest:
        print("STALE: the `measurement:` facts have changed since the verification")
        print("that backs them.")
        print(f"  declared: {declared_digest}")
        print(f"  actual:   {actual_digest}")
        print()
        print("Re-verify the measurement, then recompute:")
        print("  uv run python scripts/check_tank_out_declaration.py --print-digest")
        print(LIMITATION)
        return EXIT_UNRESOLVABLE

    sha = str(verification["measured_at_commit"])
    if not commit_resolves(sha):
        print(f"UNRESOLVABLE: measured_at_commit {sha!r} does not resolve to a commit")
        print("  in this repository. It must RESOLVE, not merely look like a SHA.")
        print(LIMITATION)
        return EXIT_UNRESOLVABLE

    bad_artifacts = [
        a for a in (verification["artifacts"] or []) if not (REPO_ROOT / a).exists()
    ]
    if bad_artifacts:
        print(f"UNRESOLVABLE: declared artifacts do not exist: {bad_artifacts}")
        print(LIMITATION)
        return EXIT_UNRESOLVABLE

    # ---- Derive the consequence -----------------------------------------
    v_drop = float(measurement["v_tank_out_to_pwr_rtn_vrms"])
    verdict, implied_group, lines = derive(v_drop)

    print(f"MEASUREMENT DECLARED, verified {verification['verified_on']}")
    print(f"  by      : {verification['verified_by']}")
    print(f"  at      : {sha}")
    print(f"  probe   : {measurement['probe_model']} "
          f"({float(measurement['probe_bandwidth_hz']) / 1e6:.1f} MHz)")
    print(f"  scope   : {measurement['scope_model']} "
          f"({float(measurement['scope_bandwidth_hz']) / 1e6:.1f} MHz)")
    print(f"  running : {measurement['operating_power_w']} W, "
          f"{measurement['tank_current_arms']} A rms, {f_sw / 1e3:.1f} kHz, "
          f"pan: {measurement['pan_description']}")
    print()
    print("DERIVED CONSEQUENCE")
    for line in lines:
        print(line)
    print()
    print(f"  measured against earth (separate reading): "
          f"{float(measurement['v_tank_out_to_earth_vrms']):.3f} V r.m.s.")
    print()

    # ---- Cross-check against the classification --------------------------
    print("CROSS-CHECK AGAINST elec/insulation_manifest.yaml")
    if manifest_group is None:
        print("  Manifest not present in this working tree (it lives on")
        print("  feat/per-pairing-creepage-derivation). Cross-check SKIPPED, not")
        print("  passed. This gate cannot confirm the classification consumed this")
        print("  result.")
        print()
        print(LIMITATION)
        return EXIT_DISAGREEMENT

    print(f"  manifest assigns tank-out : {manifest_group}")
    print(f"  measurement implies       : {implied_group}")
    if verdict == "CONTESTED":
        print()
        print("  CONTESTED -- see above. A human must reconcile.")
        print(LIMITATION)
        return EXIT_DISAGREEMENT
    if manifest_group != implied_group:
        print()
        print("  UNCONSUMED RESULT: the measurement and the classification")
        print("  disagree. Move the net in elec/insulation_manifest.yaml (a")
        print("  deliberate edit, with its own verification block and digest), or")
        print("  explain in that manifest's `basis` why the measurement does not")
        print("  govern. Do not silence this gate.")
        print(LIMITATION)
        return EXIT_DISAGREEMENT

    print()
    print("  Consistent. The classification is supported by a measurement of the")
    print("  net it classifies.")
    print()
    print(LIMITATION)
    return EXIT_OK


def print_digest() -> int:
    if not DECLARATION.exists():
        print(f"GATE ERROR: {DECLARATION} does not exist.")
        return EXIT_GATE_ERROR
    doc = yaml.safe_load(DECLARATION.read_text()) or {}
    measurement = doc.get("measurement")
    if not isinstance(measurement, dict):
        print("GATE ERROR: `measurement:` must be a mapping.")
        return EXIT_GATE_ERROR
    nulls = [k for k in REQUIRED_MEASUREMENT_KEYS if measurement.get(k) is None]
    digest = measurement_digest(measurement)
    print("Canonical digest of the `measurement:` block as it stands:")
    print()
    print(f"  declared_state_sha256: \"{digest}\"")
    print()
    if nulls:
        print(f"WARNING: {len(nulls)} required fact(s) are still null "
              f"({', '.join(nulls[:3])}{'...' if len(nulls) > 3 else ''}).")
        print("Digesting the empty declaration does NOT make it a measurement, and")
        print("pasting this digest in will not make the gate pass -- the null check")
        print("runs first, by design.")
        print()
    print("Paste the digest into verification.declared_state_sha256 ONLY as the")
    print("last step of recording a measurement you actually took.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--print-digest",
        action="store_true",
        help="print the canonical declared_state_sha256 for the facts as they stand",
    )
    args = ap.parse_args(argv)
    if args.print_digest:
        return print_digest()
    return run()


if __name__ == "__main__":
    sys.exit(main())
