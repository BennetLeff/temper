<!-- provenance: decision recorded 2026-08-16. Companion to
     docs/evidence/2026-08-16-ocp02-descope-implementation.md (the what-was-done record)
     and docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md (the full alternatives chain,
     on main, PR #1262). No board file, threshold, or safety constant is touched by this
     decision; it is a decision record + acceptance-criteria pointer. -->

# OCP-02 de-scope — formal decision record (DNF)

**Date:** 2026-08-16
**Status:** DECIDED — OCP-02 (secondary over-current protection, `SecondaryOCPComparator`)
is **de-scoped / do-not-fit (DNF)**. T2/C37/R65 stay in off-board staging.

## 1. The decision

OCP-02 is not fielded. The decision is **DNF (do not fit), not delete-from-schematic**:
the `SecondaryOCPComparator` circuit remains instantiated and wired in
`elec/src/modules.ato` (`ocp2.bus_in/out` splices into `DC_BUS_RTN`) so the interface
survives for the reinstatement paths in §5. The three parts — T2 (Coilcraft CST3015-100ED CT,
`safety.ocp2.ct`), C37 (0603 filter), R65 (4.12Ω burden, 1206) — remain staged off-board at
(100.0, 300.0) / (20.0, 272.12) / (44.0, 272.12), below the board outline's bottom edge
(y 254; the outline is x[8,172]×y[20,254] as of the 2026-08-16 left-edge enlargement PR — the
staging row is below y=254 regardless).

This decision implements the ranked-#1 recommendation of
`docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` §8 ("5 — do not populate
OCP-02"), re-confirmed by the 2026-08-16 spike
(`docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md` Part 2, on main, PR #1262) with
datasheet-verified isolation figures.

## 2. The evidence — why no alternative clears the 12.6mm PD3 bar

The governing bar is **12.6mm PD3 reinforced creepage** (IEC 60335-1 Table 17 row iv,
material group IIIa/IIIb, per the PD3 decision
`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`: the as-built board is
forced-air-vented with no cover/gasket/compartment, so PD2's 8.0mm is not earned).

| Sensing mechanism | Best achievable primary↔secondary creepage | vs 12.6mm | Verdict |
|---|---:|---:|---|
| CST3015 CT (T2, 1:100) — the designed part | **9.100mm** intrinsic (intra-footprint, placement-independent) | −3.500mm | fails in every placement (re-verified: 18 courtyard-legal positions exist on the current board, e.g. (132–136, 116–120), but the defect is the package, not the position) |
| Alternative CTs (Coilcraft CST1211/CS4xxx/SCS, TDK B78419A, LEM LPSR) | ≤9.1mm (LPSR 8.26mm) | ≤−3.5mm | closed — no better part exists |
| Hall ICs (Allegro ACS712/ACS724) | 4.0–4.2mm | −8.4mm | closed — ~3× short; the manufacturer's own layout note caps even a slotted part at 4.2mm |
| Shunt + isolated amplifier (TI AMC1301) | 8.5mm | −4.1mm | closed — same defect class, largest cost, tightest timing margin |
| Aperture/donut CT (ICE CT07-1000 class, Talema ASM) | buildable to ≥12.6mm by layout | pass by construction | **only technically-plausible long-term fix** — blocked on a verified third-party reinforced-insulation certificate (VDE/ENEC/CB/UL, IEC 60335-1/60664-1-scoped) that none of the checked parts has |

Every figure above is datasheet-verified in the spike doc; none is reconstructed or assumed.
**The evidence chain is closed: no sensing mechanism reachable today clears 12.6mm PD3.**

OCP-02 is **not IEC 60335-1 clause-mandated** — the repo-wide clause search finds nothing
requiring redundant over-current sensing; the internal `FUNCTIONAL_TEST_CRITERIA.md` §2.1
"Secondary OCP" line is a project acceptance bar with no external standard cited. Primary
protection is intact: OCP-01 hardware comparator (50.1A peak nominal, 45–55A acceptance,
<1µs, latched) + firmware software-OCP layer (40A peak, `firmware/config.yaml`
`OVER_CURRENT_THRESHOLD`).

## 3. The risk being accepted (stated, bounded)

De-scope loses the one sensing path that **specifically covers a shoot-through fault crossing
`DC_BUS_RTN`** — a conductor OCP-01's tank-return CT does not sense by construction.

- **What remains:** OCP-01 trips on the same fault's tank-side signature within <1µs at 50.1A;
  the firmware 40A-software-first layer adds a second response; the BOM §5.4 residual-risk class
  already accepts this category (see `docs/hardware/BOM.md` §5.4).
- **What this is:** a documented, bounded **redundancy reduction** within an already-accepted
  residual-risk class — **not** a new uncovered fault category.
- **Verified absence:** no firmware reference to OCP-02 exists anywhere (`firmware/` search:
  zero hits for `ocp2`/`OCP-02`/`OCP02` in `state_machine.c`, `state_handlers.c`, `safety.c`,
  `config.yaml`) — the trip was always a hardware comparator path (TLV3201 → `fault_or3.B1`),
  never a firmware read. De-scope removes nothing that exists.

## 4. Acceptance-criteria status

`docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 "Secondary OCP" (60A peak / 55–65A / <5µs) remains
as-written and **unmet — de-scoped pending owner re-scope**. The line is **not deleted and no
threshold is changed**: a labelled red beats a removed line. The row's status note (added
2026-08-16 by #1266, extended here) reads **"DE-SCOPED (DNF) — line retained as-written,
unmet"** with pointers to this decision doc and the implementation record. Re-scoping the line
(delete or mark deferred) is an owner decision, deliberately not taken by this record.
This is **not a certification blocker**: no IEC 60335-1 clause mandates a secondary OCP channel.

## 5. Reinstatement triggers (any one re-opens OCP-02)

| Trigger | Condition |
|---|---|
| **Aperture CT certified** | A verified third-party reinforced-insulation certificate (VDE/ENEC/CB/UL, IEC 60335-1/60664-1-scoped) for an ICE CT07/08/10-class or Talema ASM part — then build OCP-02 with it, for T1+T2 jointly (distinct scoped sourcing task) |
| **Slot credit confirmed** | Cert-lab Question A answers "yes, the closed end earns credit": T2 can be placed (18 courtyard-legal positions exist) with the T1-identical 28×8mm slot design — OCP-02 becomes fieldable with the existing CST3015 |
| **PD2 compartment built** | A real, inspected sealed compartment closes `check_pd2_compartment_evidence.py` → 8.0mm governs → CST3015's 9.1mm clears unslotted (+1.1mm) and the entire question set dissolves for these parts |

## 6. Relationship to other records

- **This record** = the decision (what, why, risk, triggers).
- `docs/evidence/2026-08-16-ocp02-descope-implementation.md` (on main, #1266) = the
  implementation verification (staging confirmed, firmware absence verified, BOM/STRATEGY/
  config/design-doc updates, DRC-ceiling unaffected — no board change, board hash verified
  unchanged).
- `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md` (on main, #1262) = the full
  alternatives chain and the recovered-text Question A narrowing that makes T2's reinstatement
  conditional on one lab answer instead of an open-ended search.
- `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` (on main, #1151) = the
  original ranked options (this decision implements option 5).

## Files

- This document: `docs/evidence/2026-08-16-ocp02-descope-decision.md`
- Pointer updated: `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 status note (now cites this decision
  doc alongside the implementation record)
- Verified already in place (from #1266, no change needed): `docs/hardware/BOM.md` §4.4 (DNF),
  `firmware/config.yaml` interlock comment, `docs/STRATEGY.md` gate table,
  `docs/hardware/OCP02_DESIGN.md` / `OCP02_DECISION_BRIEF.md` superseded notes.
