---
date: 2026-07-29
topic: hv-footprint-copper-shorts
focus: Resolve two hand-built footprints (K1 relay Faston tabs, R30 litz tank-coil pads) with intra-component copper shorts on mains/HV-adjacent nets, using datasheet and standards evidence instead of guessing
origin: docs/evidence/2026-07-29-intra-component-shorts-root-cause.md, "What a human must do" -- Cause B, the two library footprints not resolved by the geometrically-forced ESP32-S3-WROOM-1 fix
status: both cases resolved to an evidence-grounded footprint fix; two items remain for a human (see Outstanding Questions)
actors: PCB footprint author (human), scripts/check_pad_orientation.py gate, kicad-cli DRC, board regeneration pipeline (write_placements_to_pcb)
---

# Requirements: K1 / R30 Intra-Component Copper Shorts -- Resolution

## Summary

Both remaining hand-built-footprint copper shorts from
`docs/evidence/2026-07-29-intra-component-shorts-root-cause.md` are now
resolved in the library files. **K1** (`Relay_SPST_Omron-G4A-E.kicad_mod`,
pads 13/14): the datasheet confirms these #250 Faston tabs carry zero PCB
copper on this variant, so the fix removes the copper (SMD pad moved to
`F.Fab`, same number/type/position, preserving netlist parity) rather than
narrowing a fictitious pad. **R30** (`LitzPad_15A.kicad_mod`, pads 1/2):
these are the two ends of the resonant tank coil itself (Sheetpath
`tank.inductor_conn`); the fix widens the pitch from 5.0mm to 13.0mm (8.0mm
pad diameter, unchanged, + 5.0mm creepage), where 5.0mm is this repo's own
IEC 60335-1 Table 16 basic-insulation creepage figure at 400V
(`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 5.1), 400V being the
project's own declared `v_tank_peak` design floor (`elec/src/modules.ato`).
Neither fix is total closure: K1's fix does not turn
`scripts/check_pad_orientation.py` green even on a regenerated board, for a
precise, discovered reason (its Check 2 is deliberately fail-closed on
zero-copper pads); R30's fix is a floor calibrated to the *declared* 400V,
not the *simulated worst-case* 867V the repo's own sweep already reports,
because the coil inductance that sets the real tank voltage is itself an
unresolved upstream design input. Both gaps are stated explicitly below,
not papered over.

---

## Problem Frame

`docs/evidence/2026-07-29-intra-component-shorts-root-cause.md` (Cause B)
identified three hand-built KiCad footprints whose pads overlap in their own
local frame -- a fabrication-blocking defect independent of the
placement/rotation bug (Cause A) that made up the bulk of that
investigation. One (`ESP32-S3-WROOM-1`) was fixed directly: its pad
width/height were transposed relative to the datasheet's own land pattern,
a geometrically forced correction with a single right answer. The other
two -- K1's relay contact tabs and R30's litz-wire tank pads -- were
explicitly left open, because both sit on mains/HV-adjacent nets
(`power_in.ntc-no`/`w1_2` for K1; `tank.c_tank1-p2`/`tank-out` for R30) and
a wrong clearance number on a mains-connected appliance is worse than an
open question. Guessing a corrected dimension without evidence was declined.

This document is that evidence-gathering pass, run without further
clarifying questions per the task's explicit instruction. It reads the
Omron G4A datasheet directly (not just the footprint's paraphrase of it),
derives the tank's operating voltage from the repo's own committed source
and simulation evidence, and applies the same IEC 60335-1/60664-1 basis the
project already uses elsewhere (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`,
`scripts/generate_kicad_dru.py`) rather than inventing a new standards
reading.

---

## Case 1 -- K1, `Relay_SPST_Omron-G4A-E.kicad_mod`

### Evidence

1. **The footprint's own claim, re-verified against the primary source, not
   just re-read.** The datasheet
   (`https://omronfs.omron.com/en_US/ecb/products/pdf/en-g4a.pdf`, Cat. No.
   J056-E1-09) was fetched and its pages 1-2 extracted (both rendered and
   `pdftotext -layout`, cross-checked against each other). Two corrections
   to the footprint's prior paraphrase, one factual, one that strengthens
   the conclusion:
   - The Model Number Legend's field 3 ("Terminal Shape") is **blank/None**
     for `G4A-1A-E`, meaning "#250 quick-connect/PCB coil terminals"; field
     4 ("E") is a **separate** "Special Function: For long endurance"
     designator. The footprint's prior text conflated these two fields
     (treated "E" as the terminal-shape marker). The underlying conclusion
     survives the correction.
   - Page 2's "Terminal Arrangement/Internal Connections" diagram for
     `G4A-1A-E` labels contact pins 3/4 (COM/NO -- our 13/14) **"Tab
     Terminal"** and coil pins 1/2 (our A1/A2) **"PCB Terminal"** -- two
     different categories in the datasheet's own words. The `G4A-1A-PE`
     variant's equivalent diagram shows all four pins undifferentiated
     (real PCB thru-hole for all four). This is direct, primary-source
     confirmation that the #250 Faston tabs on `G4A-1A-E` have **zero PCB
     copper connection** -- not an inference from the footprint's own prior
     prose.
2. **KiCad's own official library has a same-family counter-example, and it
   does not overturn the conclusion.** `Relay_SPST_Omron_G2RL-1A-E.kicad_mod`
   (Omron's G2RL series, `/Applications/KiCad/KiCad.app/.../Relay_THT.pretty/`)
   models its own "-E" contact pins as **real copper thru-hole pads** (two
   physical prongs per contact, `duplicate_pad_numbers_are_jumpers`). This
   is a different Omron series with a different physical terminal
   construction (a tab that passes *through* the PCB and is soldered,
   observed from its two-holes-per-pin layout) -- it does not contradict
   G4A's own diagram, which explicitly shows the tab protruding from the
   face of the relay body *opposite* the PCB coil pins, with no PCB land at
   all. Naming convention alone ("-E" suffix) is not a reliable cross-family
   signal; the per-part diagram is.
3. **No KiCad official-library precedent for a net-bearing, zero-copper
   pad.** A scripted search of every `.kicad_mod` in
   `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/`
   (script inline in this investigation, not committed) found **zero**
   non-NPTH pads with no declared copper layer, across the entire library.
   This is a real data point against the "no copper" pattern being
   idiomatic KiCad practice -- not disqualifying (KiCad's file format does
   not forbid it, see next item), but worth stating plainly rather than
   presenting the fix as a well-trodden pattern.
4. **Empirically verified valid in KiCad 10.0.4.** A scratch two-pad board
   (not committed) with one `smd` pad on `F.Cu` and one `smd` pad on
   `F.Fab` only, both carrying a net, was run through
   `kicad-cli pcb drc --format json`: **0 violations, 0 unconnected items**.
   A copper-less net-bearing SMD pad is valid, produces no DRC complaint,
   and is not treated as dangling.
5. **The repo's own netlist-parity tooling matches on pad `type`/`number`,
   never `layers`.** `scripts/resync_pcb_netlist.py:85`
   (`connectable_pads = [p for p in fp.pads if p.type in ("smd", "thru_hole")]`)
   and the identical logic in `gen_pcb_skeleton.py` filter by pad type for
   the positional-fallback net-assignment path K1's 13/14 already use (per
   the function's own docstring, which names `'A1'/'A2'/'13'/'14'` as the
   example). `scripts/check_copper_net_consistency.py`'s docstring
   independently confirms these exact pads are already excluded from its
   exact-match assertion and reported as SKIPPED, not verified. Changing
   `layers` from `"F.Cu"` to `"F.Fab"` therefore does not change how either
   script treats these pads.
6. **The fix does not resolve HOW these nets physically reach the rest of
   the board, and that is explicitly out of scope here.**
   `elec/src/modules.ato:738-739` connects `bypass_relay.COM`/`.NO` to
   `cmc.W1_2`/`d1.A`, and the board (`pcb/temper.kicad_pcb`) carries other
   footprints (L1 pad 4, RT1 pads 1/2, U1 pad 2, U2 pad 1) on the same two
   nets, with **zero routed copper segments/vias on either net today**
   (grepped directly). Whether the design intends these to be routed via
   PCB copper reaching some other landing feature, or wired externally
   (hand-soldered spade + jumper, common practice for a mains bypass-relay
   leg like this one, and consistent with choosing the "E" quick-connect
   variant over "PE") is not decided by this change.

### Fix implemented

`pcb/libs/temper.pretty/Relay_SPST_Omron-G4A-E.kicad_mod`: pads 13/14
changed from `smd rect (layers "F.Cu")` to `smd rect (layers "F.Fab")`.
Number, type, size (6.35 x 1.2mm), and position unchanged. `descr` updated
with the corrected Model Number Legend reading, the "Tab Terminal"/"PCB
Terminal" diagram citation, and the open item above.

### Verification, and a genuine gate-behavior finding

`uv run python scripts/check_pad_orientation.py pcb/temper.kicad_pcb` is
unchanged by this fix, as expected: the board carries embedded footprint
copies and `pcb/` is read-only here, so a library-only change cannot move
it (still reports K1 pads 13/14 as overlapping, because the *board's*
embedded copy still has `F.Cu`).

To test what happens once the board **is** regenerated, a scratch copy of
`pcb/temper.kicad_pcb` (not committed, not under `pcb/`) had K1's and R30's
embedded pad blocks hand-patched to match the fixed libraries, and the gate
was re-run against that copy. Result: **R30 clears** (overlap count 57 ->
56, R30 no longer listed) -- see Case 2. **K1 does not clear.** The reason
is precise, not a residual defect: `scripts/check_pad_orientation.py:243-246`
--

```python
if not la or not lb:
    # A pad with no declared copper layer cannot be proven separate;
    # treat it as sharing (fail-closed) rather than silently skipping.
    return True
```

Check 2 is deliberately fail-closed: a pad pair where either pad has zero
declared copper layers is treated as *unproven-separate*, i.e. conservatively
flagged, not skipped. This is a reasonable general design for a gate built
to catch *accidental* copper loss (the fail-closed comment predates this
investigation and is calibrated for exactly that failure mode), but it
means **no zero-copper pad pair can ever pass Check 2 by construction**,
regardless of whether the missing copper is a bug or, as here, a verified
electrical fact. This was not previously documented anywhere in the repo;
it is a genuine, precise finding of this investigation, not a hedge.

A pad-width shrink (keep `F.Cu`, narrow the pad) was considered as an
alternative that *would* clear the gate -- it is the remedy
`2026-07-29-intra-component-shorts-root-cause.md` originally suggested.
It was not implemented, because it would reintroduce the exact
misrepresentation the datasheet evidence rules out (a fictitious PCB land
where none exists), and any shrink width has no dimensional source to cite
-- it would be sized purely to satisfy the checker, which is the
"loosen to pass" pattern this project's own conventions warn against.
**This trade-off is left for a human to weigh explicitly** (see
Outstanding Questions): accept that this specific, understood pair will
keep failing Check 2 even after board regeneration (with a documented
reason), or add a Check-2-equivalent allowlist mechanism (Check 1 already
has one; Check 2 does not), or accept the pad-shrink alternative despite
its unsourced dimension.

---

## Case 2 -- R30, `LitzPad_15A.kicad_mod`

### Evidence

1. **What R30 actually is.** `pcb/temper.kicad_pcb:4762`:
   `(property "Sheetpath" "tank.inductor_conn")`. This matches
   `elec/src/modules.ato`'s `ResonantTank.inductor_conn = new Resistor
   # Placeholder for Litz interface` (a placeholder component type kept for
   schematic-tool convenience, footprint swapped to the real litz-wire
   terminal pattern). R30's two pads are **the two ends of the tank coil
   itself** -- pad 1 net `tank.c_tank1-p2` (directly the same node as tank
   capacitor `c_tank1`'s pin 2), pad 2 net `tank-out`. In a series resonant
   tank, the voltage across the inductor is the same order of magnitude as
   the voltage across the tank capacitor (equal at resonance, opposite
   phase) -- these two pads carry the tank's full differential swing
   directly between them, not just individually elevated potentials.
2. **What voltage the tank nodes reach, from the repo's own committed
   source and simulation, not a guess:**
   - `elec/src/modules.ato:494`: `v_tank_peak: voltage = 400V`, an asserted
     design floor (`main.ato`/`modules.ato:495-496`:
     `assert c_tank1.voltage_rating >= v_tank_peak * 1.43` and the same for
     `c_tank2`, both rated 1600V, so the floor is satisfied with margin).
     This is the single most authoritative committed figure -- it is what
     the design already asserts against elsewhere.
   - `docs/evidence/2026-07-27-inductance-range-sweep.md` Sec 2.3.5:
     simulated peak tank-capacitor voltage is **128-867V** across the L
     range (50-250 uH) the repo still treats as plausible.
   - `docs/hardware/TANK_COIL_SPECIFICATION.md` (2026-07-26): **"L cannot
     be specified from the current model"** -- the coil inductance that
     would pin down which end of that 128-867V range is real remains an
     open design input, blocked on an uncalibrated pan-coupling model, not
     resolved by this brainstorm.
   - Net effect: 400V is the declared floor and the number the project's
     own margin assertions are built on; up to 867V is a real, already-
     simulated worst case that cannot currently be ruled out. Both are
     cited below; neither is invented.
3. **The applicable standards basis, using what this project already
   uses.** `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 5.1 ("Creepage
   Table (Along Surface), Based on IEC 60335-1 Table 16, Pollution Degree
   2, Material Group IIIb") gives, at 400V working voltage: **Basic 5.0mm,
   Reinforced 10.0mm**. R30's two pads are both the *same* tank circuit (not
   a mains-to-SELV or HV-to-earth boundary) -- the Basic/functional column
   applies, matching how `scripts/generate_kicad_dru.py`'s own "HV internal
   same footprint" Rule 5 treats same-domain internal spacing as a
   materially lower bar than the reinforced mains<->SELV figures elsewhere
   in the same file (that rule's own comment: "needs 2.0mm for 400V" PD2,
   "0.8mm for 400V" PD1-with-coating -- both clearance, not creepage, and
   both specifically calibrated as a compromise for TO-247's *manufacturer-
   fixed* 5.45mm pin pitch). R30 is a from-scratch custom footprint with no
   manufacturer-fixed pitch, so there is no equivalent physical excuse to
   accept less than the fully compliant Basic/PD2 figure the way TO-247
   legitimately can. Creepage (5.0mm) rather than clearance (2.5mm, Sec 4.1
   Table F.2 at 400V Basic) is the binding figure because both pads are
   exposed copper on the same board surface -- the same reasoning
   `docs/evidence/2026-07-28-isolation-keepout.md` already applied for the
   mains<->SELV barrier ("creepage is always >= clearance for the same
   voltage/pollution class, and a PCB keepout enforces surface distance
   directly").
   **Inherited caveat, stated plainly:** `HIGH_VOLTAGE_CLEARANCE_SPEC.md`
   itself is a project-internal reconstruction, not the primary IEC text --
   `docs/evidence/2026-07-28-isolation-keepout.md`'s own UNVERIFIED section
   flags that IEC 60335-1 Table 16 / IEC 60664-1's tables are paywalled and
   the repo's figures are "reconstructed from secondary/industry sources."
   This citation is the best available within the repo's own established
   basis, not a primary-standard guarantee.
4. **A previously-undocumented net-classification gap, found while checking
   which class governs these nets.** `create_temper_design_rules()
   .get_rules_for_net()` was run directly against all four nets involved in
   this document's two cases: `power_in.ntc-no`, `w1_2`, `tank.c_tank1-p2`,
   `tank-out` **all resolve to `"Default"`**, not `ACMains` or
   `HighVoltage`. Neither `TEMPER_NET_ASSIGNMENTS`
   (`packages/temper-placer/src/temper_placer/core/design_rules.py:421-466`)
   nor either copy of `HV_NET_PATTERNS`/`HV_PIN_PATTERNS`
   (`core/net_classification.py`, `router_v6/net_classification.py`) contain
   any pattern matching "tank", "ntc", or "w1"/"cmc". This means none of
   this project's automated clearance/creepage tooling
   (`netclass_rules.yaml`, `generate_kicad_dru.py`) currently protects
   either K1's mains-inrush contacts or R30's tank nodes at all -- both
   fall through to the unrelated-signal-trace default (0.15mm). This is a
   real, adjacent finding, not the subject of this brainstorm's footprint
   fix, but material enough to flag as a follow-up (see Outstanding
   Questions) since it explains why no pre-computed authoritative clearance
   number already existed for either case.
5. **The 5.0mm pitch has no derivation in repo history.** `git log --follow
   -p` on `LitzPad_15A.kicad_mod` shows the file introduced already at its
   final (defective) 8.0mm-pad/5.0mm-pitch geometry in every commit that
   touches it; no commit message, comment, or linked doc explains where
   5.0mm came from. This matches the footprint's own `descr`, unchanged by
   this investigation: "generic high-current PTH pad spec; low confidence
   -- no part-specific datasheet exists." **Stated plainly: it is
   unsourced**, exactly as the footprint already said, and this
   investigation found nothing to contradict that.

### Fix implemented

`pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`: pad 2 moved from `(at 5.0 0)`
to `(at 13.0 0)`. Pad 1 position, both pads' diameter (8.0mm), drill
(3.0mm), and layers unchanged. New pitch = 8.0mm (existing pad diameter,
not re-sourced by this change) + 5.0mm (IEC 60335-1 Table 16 Basic/PD2
creepage at the declared 400V `v_tank_peak` floor). `descr` updated with
the citation, the derivation, and the two residual-uncertainty flags below.

### What this fix does and does not resolve

**Resolves:** the unconditional defect (3.0mm of copper overlap,
independent of any voltage question) is gone, and the new 5.0mm gap is
grounded in a real citation, not an arbitrary "just clear the checker"
number. `check_pad_orientation.py`'s Check 2 (which only requires a
positive, non-touching gap, not a specific clearance value) confirms this
on the scratch-patched board: overlap count 57 -> 56, R30 no longer listed.

**Does not resolve:**
- **The 400V-vs-867V question.** This fix is a floor calibrated to the
  *declared* v_tank_peak (400V). If the coil inductance is finalized at a
  value inside the simulated range that pushes real working voltage above
  400V, 13.0mm/5.0mm is insufficient and must be re-derived at the higher
  voltage -- `HIGH_VOLTAGE_CLEARANCE_SPEC.md`'s own table stops at 400V for
  creepage (600V for clearance), so a >400V case needs a fresh standard
  lookup, not an extrapolation of this table's rows.
- **The 8.0mm pad diameter.** Left unchanged deliberately (not re-derived,
  not newly invented) -- it remains exactly as unsourced as the footprint's
  own `descr` already said. A real 15A litz-wire termination lug could
  plausibly need a different diameter; this fix does not source one.

---

## Requirements

**Footprint correctness (implemented)**
- R1. `Relay_SPST_Omron-G4A-E.kicad_mod` pads 13/14 carry no copper layer
  (`F.Fab` only), matching the datasheet's confirmed "Tab Terminal" (zero
  PCB land) classification for the G4A-1A-E variant.
- R2. The same pads retain their existing pad number (`13`/`14`), pad type
  (`smd`), size, and position, so netlist/pin-count parity and
  courtyard/placement-clearance behavior are unchanged.
- R3. `LitzPad_15A.kicad_mod` pads 1/2 are separated by a creepage gap of at
  least 5.0mm (13.0mm pitch on unchanged 8.0mm-diameter pads), eliminating
  the 3.0mm copper overlap unconditionally.
- R4. Both footprints' `descr` fields document the fix's citation basis,
  derivation, and residual open items in enough detail that a future reader
  does not have to re-derive this investigation from scratch.

**Verification (implemented)**
- R5. `scripts/check_pad_orientation.py`, run against a scratch copy of
  `pcb/temper.kicad_pcb` with K1's and R30's embedded pads hand-patched to
  match the fixed libraries, shows R30's pair no longer reported (57 -> 56
  overlaps) and K1's pair still reported, with the exact code-level reason
  documented (Case 1, "Verification" above) rather than left unexplained.
- R6. `scripts/validate_footprints.py` on both affected `.pretty`
  directories reports 0 errors and no *new* warnings versus the pre-fix
  baseline.

**Not implemented here -- follow-up work**
- R7. Board regeneration: `pcb/temper.kicad_pcb` must be rebuilt through
  `write_placements_to_pcb` (or `resync_pcb_netlist.py`) so the fixed
  library geometry actually lands in the board's embedded footprint copies,
  and `scripts/check_pad_orientation.py` wired into CI once it exits 0 (or
  its K1 finding is explicitly allowlisted/accepted per the Case 1 gate
  trade-off).
- R8. Net classification: `power_in.ntc-no`, `w1_2`, `tank.c_tank1-p2`,
  `tank-out` (and any other tank/mains-inrush nets sharing their naming
  pattern) should be added to `TEMPER_NET_ASSIGNMENTS` and/or
  `HV_NET_PATTERNS`/`HV_PIN_PATTERNS` so the project's existing
  clearance/creepage tooling actually covers them, instead of silently
  falling through to the unrelated `Default` signal-trace class.
- R9. K1's contact-net routing intent (external wire jumper vs. some
  PCB-copper-reaching path to L1/RT1/U1/U2) needs an explicit design
  decision, documented, before the relay's contact nets can be considered
  "done" from a fabrication standpoint.
- R10. Tank working voltage: the coil inductance blocker in
  `docs/hardware/TANK_COIL_SPECIFICATION.md` needs to close (calibrated pan
  model or analytical derivation from fixed geometry) before R30's 13.0mm
  pitch can be confirmed sufficient rather than provisional.

---

## Success Criteria

- A human reviewing this document can trace every dimension in both fixes
  to a citation (datasheet page, repo doc, or standard table) or an
  explicit "unchanged/unsourced, flagged" statement -- never an invented
  number presented as sourced.
- `scripts/check_pad_orientation.py`'s residual K1 finding, once the board
  is regenerated, is understood by whoever sees it as an intentional,
  documented gate-design trade-off, not mistaken for a new regression.
- Planning (or a human) can pick up R7-R10 without re-deriving the evidence
  in this document.

---

## Scope Boundaries

- `pcb/temper.kicad_pcb` was not modified (read-only per task instruction);
  all verification beyond the direct (unchanged) gate run used scratch
  copies outside `pcb/`, never committed.
- No routing-topology decision was made for K1's contact nets (R9) -- that
  is a human/electrical design call, not a footprint-geometry question.
- No attempt was made to source a corrected 8.0mm pad diameter for R30 --
  only the pitch (the unconditionally-defective dimension) was corrected.
- The net-classification gap (R8) is reported but not fixed here -- fixing
  it touches shared safety-constant SSOT code
  (`packages/temper-placer/src/temper_placer/core/design_rules.py`) used
  well beyond these two footprints, and deserves its own review rather than
  a drive-by edit inside a footprint-focused brainstorm.
- `scripts/check_pad_orientation.py` was not modified. Adding a Check-2
  allowlist (one option raised for K1) is left as an explicit open decision
  for a human, not decided unilaterally here.

---

## Key Decisions

- **K1: remove copper rather than shrink it.** Chosen over the
  gate-passing alternative (narrow the F.Cu pad) because the datasheet
  directly confirms zero PCB copper exists on the real part; shrinking
  would keep a fictitious land and require an unsourced width. Trade-off
  (the gate keeps flagging this pair even post-regeneration) is accepted
  and documented rather than hidden.
- **R30: creepage-basic at the declared 400V floor, not the simulated
  867V worst case.** Chosen because 400V is the one figure the project's
  own source (`elec/src/modules.ato`) actually commits to and asserts
  margin against today; 867V is a real but explicitly L-contingent
  simulation result from a still-open design question. Using 400V now,
  flagged as a floor requiring re-check once L is fixed, was judged more
  honest than either ignoring the 867V evidence or fabricating a number for
  a voltage that isn't settled.
- **Pad diameters left untouched in both footprints.** Neither fix invents
  a new, unsourced size dimension -- only the specific defective spacing
  each case turned on (K1's zero gap; R30's -3.0mm overlap) was corrected.

---

## Dependencies / Assumptions

1. **Assumption:** 400V (`v_tank_peak`) is the correct governing voltage
   for R30's creepage requirement, matching the project's own current
   design-floor assertion.
   **Falsifier:** the coil inductance is finalized (closing
   `docs/hardware/TANK_COIL_SPECIFICATION.md`'s open blocker) at a value
   that produces a real working voltage above 400V -- the simulated range
   already on record is 128-867V. If falsified, 13.0mm/5.0mm must be
   re-derived at the higher voltage before fabrication.
2. **Assumption:** R30's two pads are same-domain (Basic/functional
   insulation category), not a mains<->SELV or HV<->earth boundary crossing
   (which would require the Reinforced column, 10.0mm creepage at 400V).
   **Falsifier:** either net is shown to also carry exposure risk to a
   user-accessible/SELV domain (e.g. if `tank-out` or
   `tank.c_tank1-p2` is found, on closer circuit inspection, to be
   galvanically connected to an earth- or user-accessible node under some
   fault condition) -- not found in this investigation, but not
   exhaustively ruled out either.
3. **Assumption:** the 8.0mm pad diameter on R30 is adequate for a 15A litz
   termination lug. **Falsifier:** a real manufacturer spec or physical
   sample for the intended litz wire termination shows a different required
   diameter -- this was never sourced, by this investigation or the
   footprint's own prior `descr`, and remains open.
4. **Assumption:** K1's contact nets (`power_in.ntc-no`, `w1_2`) are
   correctly treated as mains-adjacent for future net-classification work
   (R8), even though today they resolve to `Default`.
   **Falsifier:** electrical review determines the relay-open worst-case
   voltage across these contacts is bounded well below mains level (e.g. if
   the NTC's fault modes are shown not to expose full line voltage here) --
   would lower the required clearance/creepage for K1 specifically, though
   it would not change the copper-representation finding (Case 1 stands
   regardless of voltage, since the tabs have zero PCB copper at any
   voltage).

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R7][User decision] Should `scripts/check_pad_orientation.py`
  gain a Check-2 allowlist mechanism (mirroring Check 1's existing
  `ALLOWLIST`) for K1's now-verified-zero-copper pad pair, or should the
  gate's fail-closed finding on this pair be accepted permanently as
  documented, expected, non-actionable output? This decides whether R7's
  "wire into CI" step needs new gate code first.
- [Affects R9][User decision] How do nets `power_in.ntc-no`/`w1_2`
  physically reach K1's Faston tabs -- external wire jumper (spade
  connector + point-to-point wire to L1/RT1/U1/U2) or some other path? This
  is an electrical/mechanical design decision, not something derivable from
  the footprint alone.

### Deferred to Planning

- [Affects R10][Needs research] Close `docs/hardware/TANK_COIL_SPECIFICATION.md`'s
  blocker (calibrate the pan-coupling model or derive L analytically from
  fixed coil geometry) so R30's governing voltage -- and therefore its
  final required pitch -- can move from "400V floor, provisional" to
  "confirmed."
- [Affects R8][Technical] Extend `TEMPER_NET_ASSIGNMENTS` and/or
  `HV_NET_PATTERNS`/`HV_PIN_PATTERNS` to cover tank and mains-inrush net
  naming patterns, then re-run `netclass_rules.yaml`/
  `generate_kicad_dru.py`-derived DRC across the whole board to see what
  else was silently falling through to `Default`.
- [Affects R3][Needs research] Source a real diameter for R30's litz-wire
  termination lug from a manufacturer spec or physical sample, replacing
  the still-unsourced 8.0mm.
