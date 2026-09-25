---
title: Rev38 HOT-receiver PFC power entry — archived
date: 2026-09-25
status: archived (superseded)
superseded_by: docs/adr/2026-09-25-front-end-architecture-brief.md, zapote/power-stage-120v
---

# Rev38 power entry: archived

## Where it is

| Item | Location |
| --- | --- |
| Rev38 branch, including its previously untracked sources and small evidence | tag `archive/rev38-power-entry-2026-09-25` (commit `a1ede3f2b`) |
| Standalone-boards / coil-intake branch | tag `archive/zapote-coil-intake-2026-09-25` (commit `687480b0a`) |
| 689 large simulation traces (29.0 GB), not in git | listed with SHA-256 in `zapote/power-entry/archive/rev38-untracked-bulk-manifest.json` inside the Rev38 tag. Local copy only; move it to an archive location before removing `worktrees/power-entry` |

Neither branch is merged. Everything below is reachable from the tags.

## What it was

Over roughly 331 commits (about 2026-09-09 to 09-25), Rev38 built:
- a mains inlet → UCC28180 boost PFC → 4 × 560 µF / 450 V bank (179 J at 400 V)
- an AVR64DA32 "HOT receiver" with a durable-session authorization protocol
- retained hardware session and RUN latches
- F2 bank-fuse detection
- a protected AUX supply chain

The source compiled to 296 parts, 73 % of them protection, authorization or auxiliary supply.
It had a 2,722-line Rust pin audit (147 mutation tests), a behavioral model, receiver firmware,
an ESP adapter, and a 295-footprint placement diagnostic. The inverter and coil were explicitly
out of scope.

## Why it was superseded

- **The premise was never re-examined.** PFC was adopted (`zapote/power-entry/PFC-ARCHITECTURE.md`) to replace a voltage doubler that drew 23–27 A RMS. The standard 120 V alternative, a small film bus with no PFC, which also meets 15 A, was never evaluated.
- **Most of the complexity guarded the bank.** Bank discharge, F2 containment, inrush, and a restart protocol so stale commands couldn't re-energize it. At 0.1 J on a film bus, those hazards disappear.
- **Its last open blocker stalled.** Driver default-off stayed unresolved through its final ~23 commits of candidate screens. Each was rejected for an unpublished vendor limit.
- **Certification burden:** safety relied on firmware and a protocol, which is Annex R / Class B territory. The replacement puts every limit on a hardware path, with non-electronic thermal cutoffs.

Full comparison: the ADR and `docs/hardware/power-section-120v/`.

## Salvaged, or scheduled for salvage

| Piece | Destination |
| --- | --- |
| `harness-lab/circuit_export.py` (per-instance part identity) | `zapote/power-stage-120v/tools/` (landed with the new unit) |
| Exact-pin Rust audit and mutation-test method; hashed build receipts | `zapote/power-stage-120v/audit.rs`, `build-receipt.json` |
| Zapote Rust crates, the five standalone boards (RTD, current-sense, thermal-sense, interlock, gate-drive) with fabrication packages, GBJ2510 package thermal model, inverter measurement framework | Landed, pruned of PFC-only modules. A differential check against the archive tag shows all 370 findings of the five kept units identical |
| Generic cooker firmware: RTD sample age, NTC guard, control-progress epoch, board I/O hooks, diagnostic lockout | Later firmware PR |
| F1 inlet/fuse coordination; insulation-basis method; SELV port contract | To be rewritten for the 20 A fuse and ~200 V bus as the native board proceeds |

Archived with the prune (not on `main`):
- the voltage-sense unit (390 V bank interface; replaced by the power stage's AMC1311)
- `zapote-thermal` cooker envelope (Rev38 product: PFC heat, `pfc_run_allowed`)
- GBJ cooling-options study
- bridge neck/joint FEM and shunt models
- Rev38 board-identity CLI mode
- the doubler simulation
- the frozen RTD debug executable

## Lessons carried forward

1. **Re-examine the architecture before hardening it.** Ask whether the hazard can be removed before designing protection for it.
2. **Stop by de-energizing.** Protective paths should fail safe when they lose power or open (energize-to-run), not rely on an actively held shunt.
3. **Set an attainable evidence standard.** Proofs rest on specified maxima; typical-only parameters need ≥ 10× margin plus a named bench test. Demanding guaranteed limits for every leakage current made every circuit unprovable.
4. **Atopile 0.2.69's netlist `libsource` part is footprint-aliased.** Take identity from the resolved export or the CSV BOM.
5. **MEAN WELL IRM-05 and IRM-20 have opposite pin 1** (AC/N vs AC/L). Never share one definition.
