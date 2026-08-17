---
module: pcb
tags: [netclass, hv, creepage, kicad-pro, classification, drc]
problem_type: bug
date: 2026-08-16
---

# HV netclass assignment fix — 8 nets unassigned in kicad_pro (2026-08-16)

**Status**: merged into `fix/classification-and-fab-rules` (commits
e7b47b424, 31b2d275e), base `origin/main` @ 593d9ab24.

## Defect shape

`elec/domain_manifest.yaml` declares 27 nets under the `HV` domain (the
hand-reviewed SSOT for domain membership). 19 of them had entries in
`pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` — the mapping
`kicad-cli`'s DRC actually reads — and 8 did not:

| net | correct class | why |
|---|---|---|
| `discharge.k_dis1-no` | HighVoltageSignal | same contact bank as already-declared `k_dis1-nc` |
| `discharge.k_dis2-no` | HighVoltageSignal | same contact bank as already-declared `k_dis2-nc` |
| `discharge.r_dis1a-p2` | HighVoltageSignal | half-bus-1 bleed string mid-node, both ends HV |
| `discharge.r_dis2a-p2` | HighVoltageSignal | half-bus-2 bleed string mid-node, both ends HV |
| `discharge.r_snub1-p2` | HighVoltageSignal | K2 NC-COM snubber mid-node, both ends HV |
| `discharge.r_snub2-p2` | HighVoltageSignal | K3 NC-COM snubber mid-node, both ends HV |
| `hb-gnd` | HighVoltage | compiled name of `hb.dc_bus.hv_minus` = DC_BUS_RTN analogue |
| `input` | HighVoltageSignal | UCC21550 LS driver output pre-rg_on, analogue of `hb.power_loop.q_high-g` |

Unassigned nets fall through to KiCad's `Default` class (0.2mm clearance,
0.0mm creepage) — invisible to every HV↔LV clearance/creepage rule. The
8 nets were also absent from `TEMPER_NET_ASSIGNMENTS`
(`packages/temper-placer/src/temper_placer/core/design_rules.py`), the
Python-side classification SSOT, so `scripts/check_hv_netclass_coverage.py`
(PROPERTY 1 + 3) was red on `main` with exactly these 8 nets.

## Measured DRC effect (the surprising half)

The naive expectation — "fixing classification makes the false 12.6mm
creepage charges disappear" — is only half the story. Measured on
`origin/main` @ 593d9ab24 (kicad-cli 10.0.5, custom DRU regenerated from
`scripts/generate_kicad_dru.py`):

| | before fix | after fix | delta |
|---|---|---|---|
| creepage errors mentioning the 8 nets | 34 | 53 | — |
| creepage, total (one sample) | 295 | 314 | +19 |

Breakdown of the +19:

* **34 false charges cleared**: pairs between two HV nets (e.g. `hb-gnd`
  vs `+15V_LS`, `discharge.k_dis2-no` vs `DC_BUS_RTN`) that DRC read as
  HV↔Default-LV and charged 12.6mm against. Same-domain after the fix, no
  rule fires.
* **53 real violations surfaced**: pairs between the 8 nets and genuine
  LV neighbours (`+3V3`, `RTD_SDI`, `SHUTDOWN_N`, `GND`, ...) that were
  invisible before because Default-LV ↔ LV pairs trip nothing. These are
  REAL HV↔LV crossings (U6's `hb-gnd`/`input` pins 0.5-8mm from SELV
  copper) that the misclassification was masking — an instance of the
  handoff's "instruments that under-report" mechanism (mechanism 4).

So the fix does NOT reduce the DRC creepage count — it makes the count
honest. 295 → ~314 is the true number with correct classification. This
is the "already-investigated, attributed, deliberate change" category of
ceiling rise; the ceiling update in `power_pcb_dataset/drc_ceiling.json`
carries a `Ceiling-Approval:` trailer and 120-sample measured-live
provenance (see the `_march` entry).

## What was changed

1. `packages/temper-placer/src/temper_placer/core/design_rules.py`:
   8 entries added to `TEMPER_NET_ASSIGNMENTS` (classes above, with
   per-net wire-tracing comments citing the manifest).
2. `pcb/temper.kicad_pro`: same 8 entries appended to
   `net_settings.netclass_assignments` (107 total now).

`scripts/sync_kicad_netclass_assignments.py --write` could not be used:
it refuses to run at all because the pre-existing PWR_RTN protection now
"resolves to a declared kicad_pro netclass" (HighVoltage) — a human
decision per its own docstring, unrelated to this change. The kicad_pro
edit was made by hand in the sync script's exact output format.

## Verification

`scripts/check_hv_netclass_coverage.py`: PROPERTY 1 (unclassified HV
nets) 8 → 0; PROPERTY 3b (unassigned in kicad_pro) 8 → 0; PROPERTY 3c
(wrong safety category) 0. The gate's only remaining failures are the two
pre-existing SELV-domain gaps (`s1`, `safety.ocp2-line`) — documented,
out of this task's scope.

Note: adding these assignments does NOT touch `pcb/temper.kicad_pcb` (the
board file) — its content hash is unchanged, so the DRC ceiling's input
hash remains valid.

## Follow-ups

* The 2 SELV-domain nets (`s1`, `safety.ocp2-line`) remain unassigned in
  kicad_pro (PROPERTY 4 red). Their manifest entries trace them as the
  SELV twin of `hb-gnd` (T2's secondary, feeds the TLV3201 comparator);
  they need LV-class assignments in a separate change.
* `scripts/sync_kicad_netclass_assignments.py` remains blocked on the
  PWR_RTN/CGND protection — an owner decision (order-of-magnitude blast
  radius, documented in its module docstring).
