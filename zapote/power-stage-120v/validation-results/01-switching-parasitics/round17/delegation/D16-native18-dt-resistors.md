# D-16: native-18, dead-time resistors R9/R17 → 49.9 kΩ (value-only revision)

**Read [README.md](README.md) first (ground rules, board facts).**
This brief **does** change design files, unlike D-1…D-15, under a recorded
owner decision. Stay strictly inside its scope.

## Decision being implemented

`zapote/power-stage-120v/DECISIONS.md`, entry **2026-10-03, dead-time
resistors R9/R17**: change R9 and R17 from **RC0603FR-0739KL (39 kΩ ±1 %)**
to **RT0603BRD0749K9L (49.9 kΩ ±0.1 %, ±25 ppm/°C)**, same 0603 footprint and
nets. Evidence: `01-switching-parasitics/FINDINGS.md` F7, `out-D12/` (part
selection and the 396.6–488.0 ns estimate).

## Precedent

Native-13 was a value/part-number-only revision of native-11 (D4/D5 → BAS116H,
R14/R6 → 100 Ω, R16/R8 → 1 kΩ): every pose, footprint and pad identical,
copper identical except KiCad's zone refill (≤ 0.10 mm²). Follow the same
process and evidence: read `native-13/verification/README.md` and
`native-17/verification/README.md` first, and use the existing tools
(`tools/build_source.py`, `tools/build_native.py`, `tools/check_copper_identity.py`,
`tools/check_native_parity.py`, `tools/jlc_dfm_check.py`, the DRC samples and
the saved-stackup gate) exactly as those revisions did.

## Task

1. **Source:** in `zapote/power-stage-120v/elec/src/` (the power stage's own
   source; **not** `elec/` at the repository root), change the dead-time
   resistor part (`R39kDt` in `parts.ato`, `r_dt.value = 39kohm` in
   `power_stage_120v.ato`) to the 49.9 kΩ RT0603BRD0749K9L part for both legs.
   Keep the 0603 footprint. Rename the part class sensibly and update every
   reference.
2. **Frozen artefacts:** regenerate `frozen/default.csv` / `frozen/default.net`
   (or add a native-18 frozen set, following how native-13 recorded its
   swap); show the diff is exactly R9/R17 value, MPN and description.
3. **Board:** produce `native-18/section.kicad_pcb` from native-17 with only
   the R9/R17 value/MPN fields changed; poses, footprints, pads, tracks and
   vias identical. Run the verification set native-13/17 ran and write
   `native-18/verification/README.md` in the same style.
4. **FEM check:** run
   `python3 validation-results/01-switching-parasitics/round17/scripts/leg_region_diff.py native-17/section.kicad_pcb native-18/section.kicad_pcb`
   and record its output: both legs must report `UNCHANGED` (no FEM rerun).
   If anything else reports changed, stop and report it.
5. **Records:** add native-18 to the native-revision history where native-13…17
   are listed; amend the DECISIONS.md entry's "implementation pending" to
   point at native-18 (do not otherwise change the decision text); do not
   claim any D4 placement-approval carry-over — that is the owner's call.

## Rules specific to this brief

- Change **only** the R9/R17 part/value and what is generated from it. No
  other part, pose, route or rule change. If the build tooling forces any
  other difference, stop and report it instead of accepting it.
- Never edit `pcb/temper.kicad_pcb` or `elec/` at the **repository root**.
- Do not build the Rust workspace or the native bridge unless the
  native-13/17 verification evidence shows it is required for the same gates;
  if so, say which gate and why.
- Not a fabrication or powered-operation release.

## Deliverable

PR against `codex/power-stage-120v-build` with the source change, frozen
artefacts, `native-18/` and its verification README, the `leg_region_diff.py`
output, and a one-line summary: what changed, what was verified identical,
and anything that needs the owner (placement-approval carry-over).

## Acceptance

Diffs show only the intended value/MPN change; copper identity and
`leg_region_diff.py` both report no copper change (zone refill within the
native-13 precedent); every gate native-17 passed still passes.
