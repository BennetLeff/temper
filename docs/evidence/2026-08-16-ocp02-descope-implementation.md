<!-- provenance: commit=7b424488fc70f86b3be0630b9b213e38313df4a2 (origin/main at fork point,
     dirty=false throughout). Own git worktree (/tmp/opencode/agent-ocp-certlab, branch
     chore/ocp02-descope-and-certlab-send), never the main checkout, never
     .claude/worktrees/agent-a374c69e35366ad12. pcb/temper.kicad_pcb sha256=
     ddb96f9e03abdcbb0aa40523b45c07413bc694309417628907780e3d19527ef2, read-only and unchanged
     (verified before and after; git status --porcelain clean apart from this task's own files).
     No footprint, DRU threshold, or enforced safety constant was edited. No standards value is
     invented or reconstructed: every figure below is quoted from evidence already on main
     (cited by exact document). -->

# OCP-02 de-scope — implementation record (de-scope accepted; T2/C37/R65 stay in staging, DNF)

**Date:** 2026-08-16
**Decision implemented:** de-scope OCP-02 (secondary over-current protection), per the
recommendation in `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md` Part 2 (on main, PR
#1262) and this repo's prior ranked-#1 option (`docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md`
§8: "5 — do not populate OCP-02").

**Implementation route: option (c) of the task's decision tree — leave T2/C37/R65 in staging.**
They are already staged off-board (below the board outline, see §2.1); de-scope therefore changes
**no board file, no footprint, no copper**. This document records the decision, the verification
that nothing in the live system referenced OCP-02, and the documentation updates that make the
de-scope explicit instead of accidental (BOM, firmware config comment, gate table, acceptance
criteria status, design/brief superseded notes).

---

## 1. Why de-scope is correct (summary of the evidence — full chain in the spike doc)

The spike (`2026-08-16-cert-lab-and-ocp02-spike.md`, on main) established, with datasheet-verified
figures, that **no alternative sensing mechanism can reach the 12.6 mm PD3 reinforced-creepage bar**
that governs this as-built, forced-air-vented, compartment-less board (PD3 decision:
`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`, on main):

| Mechanism | Best achievable primary↔secondary creepage | vs 12.6 mm | Verdict |
|---|---:|---:|---|
| Current state: CST3015 CT (T2, 1:100) | 9.100 mm intrinsic | −3.500 mm | fails in every placement (intra-footprint, placement-independent) |
| Alternative CT parts (Coilcraft CST1211/CS4xxx/SCS, TDK B78419A, LEM LPSR) | ≤ 9.1 mm (LPSR 8.26 mm) | ≤ −3.5 mm | closed — no better part exists |
| Hall ICs (Allegro ACS712/ACS724) | 4.0–4.2 mm | −8.4 mm | closed — ~3× short; manufacturer's own layout note caps even a slotted part at 4.2 mm |
| Shunt + isolated amplifier (TI AMC1301) | 8.5 mm | −4.1 mm | closed — same defect class, largest cost, tightest timing margin |
| Aperture/donut CT (ICE CT07-1000 class, Talema ASM) | buildable to ≥12.6 mm by layout | pass by construction | **only technically-plausible long-term fix — blocked on a verified third-party reinforced-insulation certificate (VDE/ENEC/CB/UL, IEC 60335-1/60664-1-scoped) that none of the checked parts has** |

OCP-02 is **not IEC 60335-1 clause-mandated** (the spike's repo-wide clause search finds nothing
requiring redundant overcurrent sensing; the internal `FUNCTIONAL_TEST_CRITERIA.md` "Secondary OCP"
line is a project acceptance bar with no external standard cited). Primary protection is intact:
OCP-01 hardware comparator (50.1 A peak nominal, 45–55 A acceptance, <1 µs, latched) plus the
firmware software-OCP layer (40 A peak, `firmware/config.yaml` `OVER_CURRENT_THRESHOLD`).

**Stated, bounded cost of de-scope** (unchanged from the spike): loses the one sensing path that
specifically covers a shoot-through fault crossing `DC_BUS_RTN` — a conductor OCP-01's tank-return
CT does not sense by construction. This is a documented redundancy reduction within the residual-risk
class BOM §5.4 already accepts, not a new uncovered fault category.

## 2. What was verified before implementing

### 2.1 The parts are already in staging (off-board) — no board edit needed

`pcb/temper.kicad_pcb` board outline: single simple rectangle, **x [20, 172] × y [20, 254]**
(measured directly from the file's `Edge.Cuts` `gr_poly`). The three OCP-02 parts sit below the
bottom edge, exactly where the spike recorded them:

| Ref | Footprint | Position (mm) | Off-board? |
|---|---|---|---|
| T2 | `temper:CST3015` (Coilcraft CST3015-100ED CT, `safety.ocp2.ct`) | (100.0, 300.0) | yes — y 300 > 254 |
| C37 | `Capacitor_SMD:C_0603_1608Metric` | (20.0, 272.12) | yes — y 272.12 > 254 |
| R65 | `Resistor_SMD:R_1206_3216Metric` (burden 4.12 Ω) | (44.0, 272.12) | yes — y 272.12 > 254 |

Identified by footprint/value/nets (per the operating rules, not by refdes alone — though on `main`
these refdeses are unambiguous: T2 = the OCP-02 CT, C37/R65 = its filter/burden). Board sha256
unchanged before and after (`ddb96f9e…`, see provenance header). **No DRC re-measurement is
required**: `pcb/temper.kicad_pcb` was not touched, so `power_pcb_dataset/drc_ceiling.json`'s
content-hash provenance remains valid.

### 2.2 Firmware: no OCP-02 reference exists anywhere — nothing to remove

Exhaustive search of `firmware/` (`*.c`, `*.h`, `*.yaml`, `*.py`) for `ocp2` / `OCP-02` / `OCP02`:

- **`firmware/main/state_machine.c`, `firmware/main/state_handlers.c`,
  `firmware/components/safety/safety.c`**: zero references. No OCP-02 fault state, no fault enum
  member, no interlock path.
- **`firmware/config.yaml`**: no OCP-02 interlock entry. The only OCP-related interlocks are
  `OVER_CURRENT_THRESHOLD` (40 A software layer, OCP-01), `IGBT_SHORT_CURRENT_THRESHOLD` (50 A) and
  `FAULT_STATE_MAX_TEMP_C` (125 °C) — all OCP-01 / thermal.
- The only `ocp` symbol in `firmware/main/ui.c` / `hal_led.h` is `HAL_LED_OCP`, the OCP-01 fault LED
  pattern — unaffected.

Rationale, matching the design: OCP-02's trip was always a **hardware comparator path**
(TLV3201 → `fault_or3.B1`), never a firmware read — the ESP32 only sees `I_SENSE` (OCP-01's CT
path). There was therefore never a firmware-side OCP-02 path to de-scope. This is a verified
absence, not an assumed one.

### 2.3 The schematic (`elec/src/modules.ato`) is left unchanged, deliberately

`SecondaryOCPComparator` (Option A, second CT) remains instantiated and wired in
`elec/src/modules.ato` (`ocp2 = new SecondaryOCPComparator`, `ocp2.bus_in/out` splices into
`DC_BUS_RTN`) with its own unplaced-status note. **De-scope here means DNF (do not fit), not
delete-from-schematic**: the part's only legitimate replacement (aperture CT, for T1+T2 jointly)
would re-use this exact interface, and the spike's trigger conditions (§4) define when it returns.
Removing the OCP-02 circuit from the atopile source would also force a netlist/board resync that
this task's operating rules do not authorize. The BOM documents the DNF status so the schematic's
live-but-unpopulated state cannot drift silently.

## 3. What this task changed (all documentation)

| File | Change |
|---|---|
| `docs/hardware/BOM.md` §4.4 | Rewritten: records the 2026-08-07 Option-A (second CT) redesign that superseded the shunt/INA240 design the old text described, names T2/C37/R65 as the staged parts, and marks them **DNF (de-scoped 2026-08-16)** with the evidence pointer. No part rows added (they are intentionally not costed/orderable). |
| `firmware/config.yaml` | Comment added at the head of the `interlocks:` block documenting the OCP-02 hardware de-scope and why **no** firmware interlock is (or was) emitted for it — so a future reader does not "helpfully" add one. No YAML data changed; `config.h` regeneration is byte-identical. |
| `docs/STRATEGY.md` Protection gate table | OCP-02 row marked **DE-SCOPED 2026-08-16** with the evidence pointer (kept in the table, status changed — the gate history stays intact). |
| `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 | Status note under the Secondary OCP row: acceptance line remains as-written but is **de-scoped pending owner re-scope**; the row is not deleted and no threshold is changed (a labelled red beats a removed line). |
| `docs/hardware/OCP02_DESIGN.md` | Superseded-by header note: describes the original shunt+INA240 design, replaced 2026-08-07 by Option A (second CT); subsystem de-scoped 2026-08-16. |
| `docs/hardware/OCP02_DECISION_BRIEF.md` | Superseded-by header note: the brief's "build it" recommendation (2026-08-07) was implemented then de-scoped on 2026-08-16 for the creepage-bar reason the brief could not have known (PD3 enforcement + the Hall/AMC1301 isolation figures). |
| This document | The decision record: what, why, risk, acceptance status, trigger conditions. |

Not changed, and why:

- `pcb/temper.kicad_pcb` — parts already off-board; board untouched (hash verified).
- `elec/src/*.ato` — DNF semantics; interface preserved for the aperture-CT reinstatement path (§4).
- `power_pcb_dataset/drc_ceiling.json` — no board change, no re-measurement.
- `docs/STRATEGY.md` historical gate-audit tables (e.g. §"All seven protection gates examined",
  2026-07-27-era) — historical records, left as written; the live gate table (§3 Protection) is the
  one updated.
- `docs/hardware/OCP02_QUANTIFIED_TRADEOFF.md` — historical Option-A-vs-B analysis; superseded by
  the de-scope decision, referenced by the brief's note.

## 4. Risk and acceptance status (the "what is the risk" record)

1. **Shoot-through on `DC_BUS_RTN` becomes sensed only indirectly.** OCP-01's tank CT sees the
   resonant loop current, not the bus-return conductor. Mitigation (unchanged from the spike):
   the hardware OCP-01 comparator trips on the same fault's tank-side signature within <1 µs at
   50.1 A; the firmware software-OCP layer adds a 40 A-peak software-first response; BOM §5.4
   already accepts this residual class. Documented, bounded redundancy reduction — not a new
   uncovered fault category.
2. **Internal acceptance line stays red.** `FUNCTIONAL_TEST_CRITERIA.md` §2.1 "Secondary OCP"
   (60 A peak / 55–65 A / <5 µs) remains as-written and **unmet**. Status: de-scoped pending an
   owner re-scope of the criterion (either delete the line or mark it deferred — an owner call,
   not this task's). It is **not** a certification blocker: no IEC 60335-1 clause mandates a
   secondary OCP channel.
3. **Staging rot.** T2/C37/R65 parked off-board at (100, 300) / (20, 272.12) / (44, 272.12) could
   drift from the schematic if someone edits `safety.ocp2.*`. Mitigation: this document, the spike,
   the BOM §4.4 DNF note, and the schematic's own BOARD FOLLOW-ON note all name the staging
   explicitly. The `config.yaml` comment additionally prevents a phantom firmware interlock.
4. **No regression risk to the live board**: OCP-02 has no placed copper, no BOM row, no firmware
   path. De-scope changes nothing physical; it makes the decision explicit.

**Acceptance-line status, in one line:** OCP-02 (Secondary OCP, 55–65 A / <5 µs) is
**de-scoped / not fielded**; the criterion line stays red pending owner re-scope; no external
standard requires it.

## 5. Trigger conditions that would reinstate OCP-02 (from the spike, unchanged)

| Would change the recommendation | Condition |
|---|---|
| Aperture CT becomes fieldable | A verified third-party reinforced-insulation certificate (VDE/ENEC/CB/UL, IEC 60335-1/60664-1-scoped) for an ICE CT07/08/10-class or Talema ASM part — then build OCP-02 with it, for T1+T2 jointly (distinct scoped sourcing task) |
| Slot credit confirmed | Cert-lab Question A answers "yes, the closed end earns credit": T2 can be placed (18 courtyard-legal positions exist) with the T1-identical 28×8 mm slot design — OCP-02 becomes fieldable with the existing CST3015 |
| PD2 compartment lands | A real, inspected sealed compartment closes `check_pd2_compartment_evidence.py` → 8.0 mm governs → CST3015's 9.1 mm clears unslotted (+1.1 mm) and the entire question set dissolves for these parts |

## 6. Named follow-ups (out of this task's scope)

- `docs/STRATEGY.md` still carries several historical OCP-02 status lines written before the
  2026-08-07 Option-A implementation ("no implementing circuit", "blocked on sensing domain").
  They are historical records and were left as written; only the live gate table was updated. A
  future STRATEGY.md refresh should reconcile them.
- The aperture-CT sourcing gap (verified reinforced-insulation certificate) is the standing
  long-term fix for T1+T2 jointly — a distinct, scoped task.

## Files

- This document: `docs/evidence/2026-08-16-ocp02-descope-implementation.md`
- Decision authority: `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md` (main, PR #1262);
  `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` (main, PR #1151);
  `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` (main).
- Touched by this task: `docs/hardware/BOM.md`, `firmware/config.yaml`, `docs/STRATEGY.md`,
  `docs/FUNCTIONAL_TEST_CRITERIA.md`, `docs/hardware/OCP02_DESIGN.md`,
  `docs/hardware/OCP02_DECISION_BRIEF.md`.
- Verified read-only: `pcb/temper.kicad_pcb` (sha256 in provenance header), `elec/src/modules.ato`,
  `firmware/main/*.c`, `firmware/components/safety/*.c`, `firmware/config.yaml` (data section),
  `power_pcb_dataset/drc_ceiling.json`.
