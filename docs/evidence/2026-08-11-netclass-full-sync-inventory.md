<!-- provenance: commit=28de4543d4ccb44141eac0282e05c22e3df29926 dirty=UNKNOWN -->
# Full netclass_assignments sync: inventory, classification, and DRC-impact triage

**Date:** 2026-08-11
**Branch:** `fix/netclass-assignments-full-sync`
**Board:** `pcb/temper.kicad_pcb` untouched — sha256
`6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`, matching
`power_pcb_dataset/drc_ceiling.json`'s recorded `provenance.inputs[0].sha256`
exactly (verified fresh against `origin/main` at commit `4fca73177`).
**Status:** UPDATED 2026-08-11 (same day) once kicad-cli 10.0.5 was restored
(a persistent install at `/home/bennet/.local/opt/kicad-10.0.5`, distinct
from the wiped `/tmp` install this section originally referenced). The
130-sample live measurement is complete and landed in the same PR
(`power_pcb_dataset/drc_ceiling.json`'s `2026-08-11-netclass-full-sync`
`_march` entry) — §6 below records the result against the structural
prediction §2 made before measuring. This document's §2–§4 (the diff, the
per-entry classification, and the `PWR_RTN` protection) were written and
verified before the measurement ran and are unchanged by it.

## 1. Method

`scripts/sync_kicad_netclass_assignments.py --check` computes, for every
`(net, class)` pair in `TEMPER_NET_ASSIGNMENTS`
(`packages/temper-placer/src/temper_placer/core/design_rules.py`, the
Python-side SSOT) whose `class` is a netclass `pcb/temper.kicad_pro`'s
`net_settings.classes` actually declares, whether `net_settings.
netclass_assignments` already agrees. `PWR_RTN`/`CGND` are excluded by a
hard-coded `PROTECTED_NETS` set (defense in depth — see §4).

This reproduces exactly PR #1023's own hand-audit (`ac_l`/`ac_n`,
`SW_NODE`, `+170V_BUS`, already fixed) plus everything that commit's own
message flagged and deliberately left out: **20 missing entries, 3
mismatched entries**, of 51 nets this sync is authorized to touch.

## 2. Full diff

### 2a. Missing entirely from `netclass_assignments`

| Net | SSOT class | Real board net? | Covered by `netclass_patterns` today? | Expected DRC impact of adding it |
|---|---|---|---|---|
| `DC_BUS_RTN` | HighVoltage | yes | **yes** — `DC_BUS*` matches | none (already correctly classified via glob) |
| `sclk` | FinePitch | yes | no | **new** — falls through to Default today |
| `sdi` | FinePitch | yes | no | **new** |
| `sdo` | FinePitch | yes | no | **new** |
| `cs_n` | FinePitch | yes | no | **new** |
| `bias` | FinePitch | yes | no | **new** |
| `refin_n` | FinePitch | yes | no | **new** |
| `vbias` | FinePitch | yes | no | **new** |
| `RTD_SCK` | FinePitch | yes | no | **new** |
| `RTD_SDI` | FinePitch | yes | no | **new** |
| `RTD_CS_N` | FinePitch | yes | no | **new** |
| `RTD_SDO` | FinePitch | yes | no | **new** |
| `RTD_DRDY` | FinePitch | yes | no | **new** |
| `RTD_HW_FAULT` | FinePitch | yes | no | **new** |
| `GATE_HS` | GateDriveHV | yes | **yes** — `GATE_*` matches (confirmed independently by `scripts/generate_kicad_dru.py`'s own RULE 6a/6b comment, "GAP CLOSED (2026-08-11)") | none (already correctly classified via glob) |
| `GATE_LS` | GateDriveHV | yes | **yes** — `GATE_*` matches | none |
| `PWM_HS` | GateDriveSELV | yes | **yes** — `PWM_*` matches | none |
| `PWM_LS` | GateDriveSELV | yes | **yes** — `PWM_*` matches | none |
| `vcc` | Power | yes | no | **new** |
| `V_BUS_SENSE` | Power | yes | no | **new** |

### 2b. Present but mismatched

| Net | Current class | SSOT class | Real board net? | Covered by `netclass_patterns`? | Expected DRC impact |
|---|---|---|---|---|---|
| `PWM_H` | FinePitch | GateDriveSELV | **no** (dead alias — real net is `PWM_H`'s successor `PWM_HS`; `PWM_H`/`PWM_L` have 0 occurrences in `pcb/temper.kicad_pcb`) | yes, `PWM_*` (moot, net doesn't exist) | **none** — no such net on the board |
| `PWM_L` | FinePitch | GateDriveSELV | no (same as above, dead alias of `PWM_LS`) | yes (moot) | none |
| `+3V3` | FinePitch | Power | **yes** | no | **real** — currently held to FinePitch's 0.1mm clearance/0.127mm trace instead of Power's 0.25mm/0.5mm; a real reclassification of a live 3.3V rail |

**15 of the 20 missing entries, and 1 of the 3 mismatched entries (`+3V3`),
are expected to change what kicad-cli's DRC actually measures** — these are
the nets that fall through to `Default` (or an incorrect explicit class)
today with zero creepage/clearance protection at their real netclass's
figures. The other **5 missing entries** (`DC_BUS_RTN`, `GATE_HS`,
`GATE_LS`, `PWM_HS`, `PWM_LS`) and **2 mismatched entries** (`PWM_H`,
`PWM_L`) are not expected to move any DRC number — the first five are
already correctly classified via `netclass_patterns` glob matches (verified
by `fnmatch.fnmatchcase` against the real JSON, and independently
corroborated by `scripts/generate_kicad_dru.py`'s own RULE 6a/6b comment
and `docs/hardware/OCP02_QUANTIFIED_TRADEOFF.md` §3.2's directly-checked
`DC_BUS*` pattern match), and the last two name a net absent from the
compiled board entirely. All are still worth fixing: explicit-over-implicit
is strictly more robust than relying on a glob pattern nobody has asserted
is permanent (see `docs/solutions/best-practices/rename-orphans-derived-keys-2026-07-28.md`
for exactly this class of silent breakage when a pattern or explicit table
drifts from the net it was written for), and `PWM_H`/`PWM_L` matching the
SSOT keeps the historical-alias entries from lying about their own class if
a future schematic revision ever reintroduces that name.

## 3. Is `pcb/temper.kicad_pro` stale, or is `TEMPER_NET_ASSIGNMENTS` wrong?

**Every one of the 23 entries above is `kicad_pro` being stale, not the
Python SSOT being wrong.** Checked individually, not assumed:

- The 13 FinePitch SPI/RTD nets (`sclk`/`sdi`/`sdo`/`cs_n`/`bias`/
  `refin_n`/`vbias`/`RTD_SCK`/`RTD_SDI`/`RTD_CS_N`/`RTD_SDO`/`RTD_DRDY`/
  `RTD_HW_FAULT`) match `TEMPER_NET_ASSIGNMENTS`'s own comment ("FinePitch
  - U8 SSOP-20 (0.635mm) + RTD SPI peripherals") and are real board nets
  under exactly those names; `kicad_pro` instead carries a set of
  differently-named, zero-occurrence dead aliases (`SPI_CLK`, `SPI_MOSI`,
  `SPI_MISO`, `SPI_CS_TEMP`, `SPI_SCK`, `RTD_CS`) from an earlier
  schematic revision, none of which are the current net names.
- `vcc`/`V_BUS_SENSE` match the "Power - DC supply rails" comment
  grouping and are real board nets; `kicad_pro` again only has
  differently-named dead aliases (`VCC*` pattern, `V_SENSE`).
- `GATE_HS`/`GATE_LS`/`PWM_HS`/`PWM_LS`/`DC_BUS_RTN` are real board nets
  matching the R4 GateDrive-split comment and the existing `DC_BUS+`/
  `DC_BUS-` sibling entries; `kicad_pro` simply never had explicit rows
  for them (patterns cover them today, incidentally).
- `PWM_H`/`PWM_L` -> GateDriveSELV matches the same R4 split comment,
  which explicitly lists `PWM_H`/`PWM_L` as historical-alias names for the
  same signal class as `PWM_HS`/`PWM_LS`.
- `+3V3` -> Power matches the explicit `"+3V3": "Power"` row under the
  "Power - DC supply rails" comment, and the adjacent `"+3.3V": "Power"`
  entry already sitting correctly in `kicad_pro` right above it — `+3V3`
  (no dot) is almost certainly a copy/paste-drifted duplicate of that
  same rail that picked up the wrong class.

No net's SSOT classification looked suspicious, contradicted an
elec/domain_manifest.yaml domain, or lacked a design-rationale comment. All
23 corrections are additive/corrective sync toward already-justified SSOT
entries.

## 4. `PWR_RTN`/`CGND` verified untouched, structurally

`scripts/check_hv_netclass_coverage.py`'s docstring reserves `PWR_RTN` (and
its dead alias `CGND`) as an explicit, open, human-decision reclassification
with an order-of-magnitude larger blast radius than every net this sync
touches combined. Verified two ways, not just asserted:

1. **Structural**: both map, via `TEMPER_NET_ASSIGNMENTS`, to the `"GND"`
   class, and `pcb/temper.kicad_pro`'s `net_settings.classes` declares no
   `"GND"` (or `"Ground"`) netclass at all today — `compute_target_assignments`
   never includes a net whose class isn't declared, so `PWR_RTN`/`CGND`
   cannot be reached even without a special case.
2. **Defense in depth**: `sync_kicad_netclass_assignments.py`'s
   `PROTECTED_NETS = frozenset({"PWR_RTN", "CGND"})` refuses to run at all
   (exit 5) if `GND` (or whatever `TEMPER_NET_ASSIGNMENTS["PWR_RTN"]`
   currently resolves to) is ever declared as a real `kicad_pro` netclass in
   the future — `scripts/tests/test_sync_kicad_netclass_assignments.py::
   TestCLI::test_protected_net_refused_even_if_gnd_class_declared` pins
   this against regression with a synthetic `kicad_pro` that *does*
   declare `GND`.

## 5. What §2–§4 do not do (true as originally written; superseded by §6 below)

§2–§4 above were written before kicad-cli was available in this session and
are a structural prediction (glob-pattern match vs. true
fall-through-to-Default), not a measured one — kept verbatim as the
falsifiable hypothesis §6 checks, per the standing instruction to report
whether the measurement confirms it rather than silently overwrite the
prediction with the answer.

## 6. Measured result (130 samples, kicad-cli 10.0.5, `--all-track-errors`), checked against §2's prediction

**Method, in order:**

1. **Baseline control** — 15 samples on the OLD (pre-full-sync, post-#1023)
   `kicad_pro` against the current, unchanged board. Reproduced the
   committed record exactly: `clearance` 372/372 (deterministic), `creepage`
   within the recorded 182–184 band. Confirms no drift and confirms the
   newly-restored kicad-cli install (a different path/prefix than every
   prior session's) measures this board identically to the committed
   baseline for every error category.
2. **Isolation control** — 15 samples with *only* the 5 glob-covered
   entries added (`DC_BUS_RTN`/`GATE_HS`/`GATE_LS`/`PWM_HS`/`PWM_LS`),
   nothing else. `clearance` 372/372 and `creepage` within 182–184 —
   **byte-identical to the baseline control.** This is the direct,
   empirical (not merely structural) answer to "do the glob-covered
   entries move anything": **they do not.**
3. **Fully-synced board** — 130 samples (all 23 corrections applied, DRU
   regenerated from `scripts/generate_kicad_dru.py` first). `clearance` is
   fully deterministic at 386/386 (**+14** over the control). `creepage` is
   **unchanged**: `{182: 5, 183: 43, 184: 82}` over 130 samples — the same
   182–184 band, because none of the 16 real corrections (the FinePitch/
   Power reclassifications) are HV-domain nets, so the HV↔LV creepage rules
   (`scripts/generate_kicad_dru.py`, keyed on `ACMains`/`HighVoltage`/
   `HighVoltageIsolated`/`GateDriveHV` netclass names) never fire for them.
   All 10 other error categories are byte-identical to the prior record.

**Verdict against the §2 prediction: confirmed, and sharper than predicted.**
§2 predicted 16 corrections would move "real DRC numbers" without
predicting *which* category — the measurement shows the entire effect
lands in a single category (`clearance`, +14), not spread across multiple
rule types, and `creepage` is provably untouched. The 5 glob-covered
entries and the 2 dead-alias corrections (`PWM_H`/`PWM_L`) are confirmed,
empirically, to move nothing — not merely argued from the fact that their
effective classification was structurally unchanged.

`error_ceiling` 1252 → 1266 (+14, entirely the `clearance` delta).
`warning_ceiling` is **not** updated by this measurement: the restored
kicad-cli install has no `kicad-footprints` package (verified — zero
`.pretty` directories under the install prefix), which makes
`lib_footprint_issues`/`lib_footprint_mismatch` unreliable in this
environment for both the old and new board content identically (an
environment artifact, not a measured delta). The other 7 warning
categories reproduced the committed values exactly across all three runs
above, corroborating zero warning impact from this sync — but the two
footprint-library-dependent categories are left exactly as committed
rather than replaced with a number this environment cannot be trusted to
produce.

Landed in `power_pcb_dataset/drc_ceiling.json`'s `2026-08-11-netclass-full-sync`
`_march` entry, with a fresh `measured-live` provenance record
(`sample_count: 130`, input hash matching `pcb/temper.kicad_pcb`'s current
content) and a `Ceiling-Approval:` trailer on the landing commit. Verified
against `scripts/check_drc_ceiling_approval.py --base-ref origin/main`:
PASS.
